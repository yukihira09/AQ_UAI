"""M4 egress policy, adapter and network behaviour, without a database.

Every network test talks to a fake provider on 127.0.0.1 started by the test itself.
External destinations are simulated with the module seams (resolver, socket opener,
TLS trust store); no request ever leaves the machine and nothing is billed.
"""

import datetime
import ipaddress
import json
import logging
import socket
import ssl
import threading
import time
from uuid import uuid4

import httpcore
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pydantic import SecretStr

from aq_uai_api.mdl import egress, testing
from aq_uai_api.mdl.adapters import adapter_for
from aq_uai_api.mdl.adapters.openai_compatible import PATH_SUFFIX, probe_body

SECRET = "sk-m4-unit-canary-31c9"
PUBLIC = ipaddress.ip_address("93.184.216.34")
PUBLIC_2 = ipaddress.ip_address("93.184.216.35")
HOST = "api.vendor-a.test"
OK_BODY = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}}]}


def loopback_policy(port):
    """What an operator would configure for one local model server (M5: port-scoped)."""
    return egress.EgressPolicy.from_setting(f"127.0.0.1/32:{port}")


REAL_TLS_CONTEXT = egress.tls_context
FAST = egress.Timeouts(connect=1.0, read=1.0, write=1.0, total=2.0)


# --------------------------------------------------------------------- fake provider


def http_response(status=200, body=b"", headers=()):
    reason = {200: "OK", 302: "Found", 401: "Unauthorized", 503: "Unavailable"}.get(status, "X")
    lines = [f"HTTP/1.1 {status} {reason}", f"Content-Length: {len(body)}", "Connection: close"]
    lines += [f"{name}: {value}" for name, value in headers]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def json_reply(document=OK_BODY, status=200):
    body = json.dumps(document).encode()
    return lambda connection, request: connection.sendall(
        http_response(status, body, [("Content-Type", "application/json")])
    )


class FakeProvider:
    """Raw HTTP/1.1 server on loopback. Records each request and the TLS SNI it saw."""

    def __init__(self, respond=None, tls: ssl.SSLContext | None = None):
        self.respond = respond or json_reply()
        self.requests: list[dict] = []
        self.connections = 0
        self.sni: list[str | None] = []
        self.tls = tls
        if tls is not None:
            tls.sni_callback = lambda sslobj, name, ctx: self.sni.append(name)
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.stopped = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._serve, args=(connection,), daemon=True).start()

    def _serve(self, connection):
        try:
            if self.tls is not None:
                connection = self.tls.wrap_socket(connection, server_side=True)
            connection.settimeout(5)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                data += chunk
            head, _, body = data.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            headers = {}
            for line in lines[1:]:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
            while len(body) < int(headers.get("content-length", 0)):
                body += connection.recv(4096)
            request = {"line": lines[0], "headers": headers, "body": body}
            self.requests.append(request)
            self.respond(connection, request)
        except (OSError, ssl.SSLError):
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def close(self):
        self.stopped.set()
        self.listener.close()


@pytest.fixture
def provider():
    servers = []

    def start(respond=None, tls=None):
        server = FakeProvider(respond, tls)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def internal_post(
    server, policy=None, timeouts=FAST, headers=(), max_bytes=None, sends_credential=False
):
    policy = policy or loopback_policy(server.port)
    kwargs = {"timeouts": timeouts, "sends_credential": sends_credential}
    if max_bytes is not None:
        kwargs["max_bytes"] = max_bytes
    return egress.post(
        policy, "INTERNAL", f"http://127.0.0.1:{server.port}/v1", PATH_SUFFIX,
        list(headers), b"{}", **kwargs,
    )


# ----------------------------------------------------------------- TLS test material


def _certificate(subject_name, issuer_name, public_key, signing_key, *, ca, san=None):
    now = datetime.datetime.now(datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_name)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if san:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False
        )
    return builder.sign(signing_key, hashes.SHA256())


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    """A private CA plus server certificates for the right and a wrong host name."""
    folder = tmp_path_factory.mktemp("pki")
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = _certificate("M4 Test CA", "M4 Test CA", ca_key.public_key(), ca_key, ca=True)
    ca_pem = ca.public_bytes(serialization.Encoding.PEM).decode()

    def server_context(name):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = _certificate(name, "M4 Test CA", key.public_key(), ca_key, ca=False, san=name)
        cert_path, key_path = folder / f"{name}.crt", folder / f"{name}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        return context

    return {"ca": ca_pem, "server_context": server_context}


class ExternalWorld:
    """Simulated DNS and routing: public addresses are mapped to loopback servers."""

    def __init__(self, monkeypatch, pki, answers):
        self.answers = list(answers)
        self.resolved: list[str] = []
        self.opened: list[ipaddress.IPv4Address] = []
        self.routes: dict = {}
        monkeypatch.setattr(egress, "resolve", self.resolve)
        monkeypatch.setattr(egress, "open_connection", self.open)

        def trusted(extra_ca_file=None):
            context = REAL_TLS_CONTEXT(extra_ca_file)  # production settings plus the test CA
            context.load_verify_locations(cadata=pki["ca"])
            return context

        monkeypatch.setattr(egress, "tls_context", trusted)

    def resolve(self, host, port, timeout):
        self.resolved.append(host)
        answer = self.answers[min(len(self.resolved), len(self.answers)) - 1]
        return [ipaddress.ip_address(item) for item in answer]

    def open(self, address, port, timeout):
        self.opened.append(address)
        if address not in self.routes:
            raise httpcore.ConnectError("unreachable")
        return httpcore.SyncBackend().connect_tcp("127.0.0.1", self.routes[address], timeout=timeout)


def external_post(headers=(), timeouts=FAST, host=HOST):
    return egress.post(
        egress.EgressPolicy(), "EXTERNAL", f"https://{host}/v1", PATH_SUFFIX,
        list(headers), b"{}", timeouts=timeouts,
    )


# ------------------------------------------------------------------- address policy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.0.1", "172.31.255.255",
        "192.168.1.1", "169.254.169.254", "169.254.0.1", "100.64.0.1", "100.100.100.200",
        "0.0.0.0", "0.1.2.3", "224.0.0.1", "239.255.255.250", "255.255.255.255", "240.0.0.1",
        "198.18.0.1", "192.0.2.1", "198.51.100.1", "203.0.113.1", "192.0.0.8", "192.88.99.1",
        "::", "::1", "fe80::1", "fc00::1", "fd00:ec2::254", "fec0::1", "ff02::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:8.8.8.8", "::127.0.0.1",
        "64:ff9b::7f00:1", "64:ff9b:1::1", "2002:7f00:1::1", "2001::1", "2001:db8::1",
        "100::1", "3fff::1",
    ],
)
def test_external_destinations_must_be_public(address):
    target = egress.parse_target(f"https://{HOST}/v1")
    with pytest.raises(egress.EgressBlocked):
        egress.EgressPolicy().check_addresses("EXTERNAL", target, [ipaddress.ip_address(address)])


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed_for_external(address):
    target = egress.parse_target(f"https://{HOST}/v1")
    egress.EgressPolicy().check_addresses("EXTERNAL", target, [ipaddress.ip_address(address)])


def test_one_bad_address_blocks_the_whole_answer():
    target = egress.parse_target(f"https://{HOST}/v1")
    policy = egress.EgressPolicy()
    with pytest.raises(egress.EgressBlocked):
        policy.check_addresses("EXTERNAL", target, [PUBLIC, ipaddress.ip_address("10.0.0.1")])
    with pytest.raises(egress.EgressBlocked):
        policy.check_addresses("EXTERNAL", target, [])
    with pytest.raises(egress.EgressBlocked):
        policy.check_addresses("UNKNOWN", target, [PUBLIC])


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://[::ffff:127.0.0.1]/v1",
        "https://8.8.8.8/v1",  # external providers use host names, not IP literals
        "https://2130706433/v1",  # decimal 127.0.0.1
        "https://0177.0.0.1/v1",  # octal
        "https://0x7f.0.0.1/v1",  # hex
        "https://0x7f000001/v1",
        "https://127.1/v1",  # short form
        "https://localhost/v1",
        "https://api.localhost/v1",
        "https://db/v1",  # single label: a local service name
        "http://api.vendor-a.test/v1",  # https only
        "https://api.vendor-a.test:8443/v1",  # port 443 only
        "https://user:pw@api.vendor-a.test/v1",
        "https://api.vendor-a.test/v1?key=x",
        "https://api.vendor-a.test/v1#x",
        "https://exämple.test/v1",  # Unicode host names are not converted
        "https://１２７．０．０．１/v1",  # full-width digits that IDNA would turn into an IP
        "https://api.vendor-a.test%2F@evil.test/v1",
        "https://[fe80::1%25eth0]/v1",
        "https://-bad-.test/v1",
        "https://api..test/v1",
        "https://api.vendor-a.test/v1 x",
        "ftp://api.vendor-a.test/v1",
        "https:///v1",
    ],
)
def test_external_endpoint_static_rules(endpoint):
    with pytest.raises(egress.EgressBlocked):
        target = egress.parse_target(endpoint)
        egress.EgressPolicy().check_target("EXTERNAL", target)


def test_external_trailing_dot_and_case_are_canonical():
    target = egress.parse_target("https://API.Vendor-A.test./v1/", "/chat/completions")
    egress.EgressPolicy().check_target("EXTERNAL", target)
    assert (target.host, target.port, target.path) == (HOST, 443, "/v1/chat/completions")
    assert target.authority == HOST


# --------------------------------------------------------------- internal allowlist


@pytest.mark.parametrize(
    "raw",
    [
        "169.254.0.0/16:80",  # metadata range: always blocked
        "169.254.169.254:80",
        "0.0.0.0/0:80",  # over-broad
        "10.0.0.0/7:80",
        "[::/0]:80",
        "[fe80::/64]:80",
        "10.0.0.1/8:80",  # host bits set: a typo, refused
        "bad_host!:80",
        "2130706433:80",  # numeric "host name"
        "0x7f.1:80",
        "ollama/8:80",
        "exämple:80",
        # M5: every entry needs exactly one valid port.
        "ollama",
        "10.0.0.0/8",
        "ollama:",
        "ollama:0",
        "ollama:65536",
        "ollama:011434",
        "ollama:80:81",
        "fd12::5:80",  # IPv6 must be bracketed
        "[fd12::5]",
        "[ollama]:80",
        "ollama:11434,10.0.0.0/8",  # one bad entry invalidates the whole list
    ],
)
def test_invalid_allowlists_fail_closed(raw):
    with pytest.raises(egress.InvalidAllowlist):
        egress.InternalAllowlist.parse(raw)
    policy = egress.EgressPolicy.from_setting(raw)
    assert not policy.allowlist_valid and policy.allowlist.empty
    with pytest.raises(egress.EgressBlocked):
        policy.check_target("INTERNAL", egress.parse_target("http://10.0.0.1:11434/v1"))


def test_allowlist_parsing():
    allowlist = egress.InternalAllowlist.parse(
        " Ollama.:11434 , 10.20.0.0/16:8000,,127.0.0.1:8080 ,[fd12::/64]:8000, ollama:8080"
    )
    assert allowlist.hosts == {("ollama", 11434), ("ollama", 8080)}
    assert [(str(net), port) for net, port in allowlist.networks] == [
        ("10.20.0.0/16", 8000), ("127.0.0.1/32", 8080), ("fd12::/64", 8000),
    ]
    assert len(allowlist) == 5 and egress.InternalAllowlist.parse("").empty


def check_internal(setting, endpoint, addresses):
    policy = egress.EgressPolicy.from_setting(setting)
    target = egress.parse_target(endpoint)
    policy.check_target("INTERNAL", target)
    policy.check_addresses("INTERNAL", target, [ipaddress.ip_address(a) for a in addresses])


@pytest.mark.parametrize(
    ("setting", "endpoint", "addresses"),
    [
        ("ollama:11434", "http://ollama:11434/v1", ["172.18.0.5"]),
        ("ollama:11434", "http://OLLAMA.:11434/v1", ["172.18.0.5"]),
        ("ollama:80", "http://ollama/v1", ["172.18.0.5"]),  # default port
        ("ollama:443", "https://ollama/v1", ["172.18.0.5"]),
        ("10.0.0.0/8:8000", "http://gpu-box:8000/v1", ["10.1.2.3"]),
        ("10.0.0.0/8:8000", "http://10.1.2.3:8000/v1", ["10.1.2.3"]),
        ("127.0.0.1/32:8080", "http://127.0.0.1:8080/v1", ["127.0.0.1"]),
        ("127.0.0.1:8080", "http://localhost:8080/v1", ["127.0.0.1"]),
        ("[fd12::/64]:8000", "http://[fd12::5]:8000/v1", ["fd12::5"]),
        ("10.0.0.0/8:8000", "http://gpu-box:8000/v1", ["::ffff:10.1.2.3"]),
    ],
)
def test_internal_destinations_on_the_allowlist(setting, endpoint, addresses):
    check_internal(setting, endpoint, addresses)


@pytest.mark.parametrize(
    ("setting", "endpoint", "addresses"),
    [
        ("", "http://ollama:11434/v1", ["172.18.0.5"]),  # no allowlist: nothing internal
        ("ollama:11434", "http://db:5432/v1", ["172.18.0.2"]),  # not listed
        ("ollama:11434", "http://ollama:5432/v1", ["172.18.0.5"]),  # M5: listed host, other port
        ("ollama:11434", "http://ollama/v1", ["172.18.0.5"]),  # default port 80 not listed
        ("10.0.0.0/8:8000", "http://10.1.2.3:5432/v1", ["10.1.2.3"]),  # CIDR, other port
        ("10.0.0.0/8:8000", "http://gpu-box:22/v1", ["10.1.2.3"]),
        ("ollama:11434", "http://ollama:11434/v1", ["169.254.169.254"]),  # blocklist wins
        ("ollama:11434", "http://ollama:11434/v1", ["127.0.0.1"]),  # loopback needs a CIDR
        ("ollama:11434", "http://ollama:11434/v1", ["0.0.0.0"]),
        ("ollama:11434", "http://ollama:11434/v1", ["::ffff:169.254.169.254"]),
        ("ollama:11434", "http://ollama:11434/v1", ["224.0.0.1"]),
        ("10.0.0.0/8:8000", "http://gpu-box:8000/v1", ["10.1.2.3", "192.168.1.1"]),
        ("10.0.0.0/8:8000", "http://192.168.1.1:8000/v1", ["192.168.1.1"]),
        ("10.0.0.0/8:8000", "http://0x0a.1.2.3:8000/v1", ["10.1.2.3"]),
        ("127.0.0.1/32:8000", "http://127.0.0.2:8000/v1", ["127.0.0.2"]),
    ],
)
def test_internal_destinations_off_the_allowlist(setting, endpoint, addresses):
    with pytest.raises(egress.EgressBlocked):
        check_internal(setting, endpoint, addresses)


def test_external_providers_ignore_the_internal_allowlist():
    policy = egress.EgressPolicy.from_setting("127.0.0.1/32:443,ollama:443")
    target = egress.parse_target(f"https://{HOST}/v1")
    with pytest.raises(egress.EgressBlocked):
        policy.check_addresses("EXTERNAL", target, [ipaddress.ip_address("127.0.0.1")])


# ------------------------------------------------------------- network: internal http


def test_internal_round_trip_sends_exact_headers_and_body(provider):
    server = provider()
    request = adapter_for("OPENAI_COMPATIBLE").build("m-1", "BEARER", None, SecretStr(SECRET))
    result = egress.post(
        loopback_policy(server.port), "INTERNAL", f"http://127.0.0.1:{server.port}/v1", request.suffix,
        request.headers, request.body, timeouts=FAST,
    )
    assert result.status == 200 and json.loads(result.body) == OK_BODY
    seen = server.requests[0]
    assert seen["line"] == "POST /v1/chat/completions HTTP/1.1"
    assert seen["headers"]["authorization"] == f"Bearer {SECRET}"
    assert seen["headers"]["host"] == f"127.0.0.1:{server.port}"
    assert seen["headers"]["accept-encoding"] == "identity"
    assert seen["body"] == probe_body("m-1")
    assert SECRET not in repr(request)


def test_internal_blocked_without_allowlist_makes_no_connection(provider):
    server = provider()
    for policy in (
        egress.EgressPolicy(),
        egress.EgressPolicy.from_setting("10.0.0.0/8:80"),
        loopback_policy(server.port + 1 if server.port < 65535 else 1),  # M5: wrong port
    ):
        with pytest.raises(egress.EgressBlocked):
            internal_post(server, policy=policy)
    assert server.connections == 0


def test_redirects_are_reported_and_never_followed(provider):
    inner = provider()
    outer = provider(
        lambda c, r: c.sendall(
            http_response(302, headers=[("Location", f"http://127.0.0.1:{inner.port}/x")])
        )
    )
    result = internal_post(outer)
    assert result.status == 302 and result.body == b""
    assert adapter_for("OPENAI_COMPATIBLE").classify(result).error_code == "REDIRECT_REFUSED"
    assert inner.connections == 0


def test_no_retries_on_server_errors(provider):
    server = provider(json_reply({"error": "busy"}, status=503))
    assert internal_post(server).status == 503
    time.sleep(0.1)
    assert server.connections == 1 and len(server.requests) == 1


def test_oversize_responses_are_cut_off(provider):
    declared = provider(lambda c, r: c.sendall(http_response(200, b"x" * 70_000)))
    with pytest.raises(egress.ResponseTooLarge):
        internal_post(declared)

    def chunked(connection, request):
        connection.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
        for _ in range(100):
            connection.sendall(b"400\r\n" + b"x" * 1024 + b"\r\n")
        connection.sendall(b"0\r\n\r\n")

    with pytest.raises(egress.ResponseTooLarge):
        internal_post(provider(chunked))
    small = provider(lambda c, r: c.sendall(http_response(200, b"y" * 100)))
    assert internal_post(small, max_bytes=100).body == b"y" * 100


def test_encoded_bodies_are_not_decoded(provider):
    server = provider(
        lambda c, r: c.sendall(http_response(200, b"\x1f\x8b", [("Content-Encoding", "gzip")]))
    )
    result = internal_post(server)
    assert result.body == b""
    assert adapter_for("OPENAI_COMPATIBLE").classify(result).error_code == "BAD_RESPONSE"


def test_slow_response_times_out(provider):
    server = provider(lambda c, r: (time.sleep(3), c.sendall(http_response(200))))
    started = time.monotonic()
    with pytest.raises(httpcore.ReadTimeout):
        internal_post(server, timeouts=egress.Timeouts(connect=1, read=0.5, write=1, total=5))
    assert time.monotonic() - started < 2


def test_slow_drip_is_bounded_by_the_total_deadline(provider):
    def drip(connection, request):
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
        for _ in range(100):
            time.sleep(0.2)
            connection.sendall(b"x")

    started = time.monotonic()
    with pytest.raises((egress.EgressTimeout, httpcore.ReadTimeout)):
        internal_post(provider(drip), timeouts=egress.Timeouts(connect=1, read=1, write=1, total=1.5))
    assert time.monotonic() - started < 2.5


def test_proxy_environment_is_ignored(provider, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    server = provider()
    assert internal_post(server).status == 200 and len(server.requests) == 1


def test_secret_never_reaches_logs(provider, caplog):
    caplog.set_level(logging.DEBUG)
    server = provider()
    request = adapter_for("OPENAI_COMPATIBLE").build("m", "HEADER_KEY", "X-Api-Key", SecretStr(SECRET))
    egress.post(
        loopback_policy(server.port), "INTERNAL", f"http://127.0.0.1:{server.port}/v1", request.suffix,
        request.headers, request.body, timeouts=FAST,
    )
    assert server.requests[0]["headers"]["x-api-key"] == SECRET
    assert "authorization" not in server.requests[0]["headers"]
    assert SECRET not in caplog.text


# ---------------------------------------------- network: external, pinning and TLS


def test_external_tls_uses_host_name_for_sni_and_verification(provider, pki, monkeypatch):
    server = provider(tls=pki["server_context"](HOST))
    world = ExternalWorld(monkeypatch, pki, [[str(PUBLIC)]])
    world.routes[PUBLIC] = server.port
    result = external_post([(b"Authorization", f"Bearer {SECRET}".encode())])
    assert result.status == 200
    assert server.sni == [HOST] and server.requests[0]["headers"]["host"] == HOST
    assert world.opened == [PUBLIC]


def test_certificate_for_another_name_fails(provider, pki, monkeypatch):
    server = provider(tls=pki["server_context"]("other.test"))
    world = ExternalWorld(monkeypatch, pki, [[str(PUBLIC)]])
    world.routes[PUBLIC] = server.port
    with pytest.raises(httpcore.ConnectError) as caught:
        external_post()
    assert testing._tls_failure(caught.value)
    assert server.requests == []


def test_untrusted_certificate_fails_with_the_default_trust_store(provider, pki, monkeypatch):
    server = provider(tls=pki["server_context"](HOST))
    world = ExternalWorld(monkeypatch, pki, [[str(PUBLIC)]])
    world.routes[PUBLIC] = server.port
    monkeypatch.setattr(egress, "tls_context", REAL_TLS_CONTEXT)
    with pytest.raises(httpcore.ConnectError) as caught:
        external_post()
    assert testing._tls_failure(caught.value)


def test_dns_rebinding_is_closed_by_resolving_once_and_pinning(provider, pki, monkeypatch):
    """Public on the first answer, loopback on any later one: we never ask twice."""
    server = provider(tls=pki["server_context"](HOST))
    world = ExternalWorld(monkeypatch, pki, [[str(PUBLIC)], ["127.0.0.1"]])
    world.routes[PUBLIC] = server.port
    assert external_post().status == 200
    assert world.resolved == [HOST] and world.opened == [PUBLIC]


@pytest.mark.parametrize(
    "answer", [["127.0.0.1"], [str(PUBLIC), "10.0.0.1"], ["169.254.169.254"], ["::ffff:127.0.0.1"]]
)
def test_private_answers_are_refused_before_connecting(pki, monkeypatch, answer):
    world = ExternalWorld(monkeypatch, pki, [answer])
    with pytest.raises(egress.EgressBlocked):
        external_post()
    assert world.opened == []


def test_each_validated_address_is_tried_once_without_retries(provider, pki, monkeypatch):
    server = provider(tls=pki["server_context"](HOST))
    world = ExternalWorld(monkeypatch, pki, [[str(PUBLIC), str(PUBLIC_2)]])
    world.routes[PUBLIC_2] = server.port  # the first address is unreachable
    assert external_post().status == 200
    assert world.opened == [PUBLIC, PUBLIC_2] and world.resolved == [HOST]
    world.opened.clear()
    world.routes.clear()
    with pytest.raises(httpcore.ConnectError):
        external_post()
    assert world.opened == [PUBLIC, PUBLIC_2]


def test_pinned_backend_refuses_other_destinations():
    target = egress.parse_target(f"https://{HOST}/v1")
    backend = egress._PinnedBackend(
        egress.EgressPolicy(), "EXTERNAL", target, egress._Deadline(5),
        lambda *a: pytest.fail("must not resolve"), lambda *a: pytest.fail("must not connect"),
    )
    for host, port in (("evil.test", 443), (HOST, 80)):
        with pytest.raises(egress.EgressBlocked):
            backend.connect_tcp(host, port)
    with pytest.raises(egress.EgressBlocked):
        backend.connect_unix_socket("/var/run/postgresql/.s.PGSQL.5432")


def test_peer_address_is_checked_after_connecting(provider, monkeypatch):
    server = provider()
    stream = egress.open_connection(ipaddress.ip_address("127.0.0.1"), server.port, 1.0)
    stream.close()
    real = httpcore.SyncBackend.connect_tcp

    def hijacked(self, host, port, timeout=None, **kwargs):
        # Simulates a socket layer that lands somewhere other than the validated address.
        return real(self, "127.0.0.1", server.port, timeout=timeout)

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", hijacked)
    with pytest.raises(egress.EgressBlocked):
        egress.open_connection(ipaddress.ip_address("127.0.0.2"), server.port, 1.0)


def test_resolver_deadline(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: time.sleep(2))
    started = time.monotonic()
    with pytest.raises(egress.EgressTimeout):
        egress.resolve("slow.test", 443, 0.3)
    assert time.monotonic() - started < 1

    def failing(*a, **k):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", failing)
    with pytest.raises(egress.ResolutionFailed):
        egress.resolve("missing.test", 443, 1)


# --------------------------------------------------------------------------- adapter


def test_adapter_builds_one_fixed_request_without_generation_settings():
    adapter = adapter_for("OPENAI_COMPATIBLE")
    bearer = adapter.build("gpt-x", "BEARER", None, SecretStr(SECRET))
    keyed = adapter.build("gpt-x", "HEADER_KEY", "X-Api-Key", SecretStr(SECRET))
    none = adapter.build("gpt-x", "NONE", None, None)
    assert dict(bearer.headers)[b"Authorization"] == f"Bearer {SECRET}".encode()
    assert dict(keyed.headers)[b"X-Api-Key"] == SECRET.encode()
    assert b"Authorization" not in dict(none.headers)
    body = json.loads(none.body)
    assert body == {
        "model": "gpt-x",
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "max_tokens": 16,
        "stream": False,
    }
    assert "temperature" not in none.body.decode() and none.suffix == "/chat/completions"
    with pytest.raises(ValueError):
        adapter.build("gpt-x", "BEARER", None, None)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, json.dumps(OK_BODY), ("PASSED", None, 2)),
        (201, json.dumps(OK_BODY), ("PASSED", None, 2)),
        (200, "not json", ("FAILED", "BAD_RESPONSE", 2)),
        (200, "[]", ("FAILED", "BAD_RESPONSE", 2)),
        (200, '{"choices": []}', ("FAILED", "BAD_RESPONSE", 2)),
        (200, '{"choices": [{"text": "x"}]}', ("FAILED", "BAD_RESPONSE", 2)),
        (200, '{"error": {"message": "x"}, "choices": [{"message": {}}]}', ("FAILED", "BAD_RESPONSE", 2)),
        (200, "\xff", ("FAILED", "BAD_RESPONSE", 2)),
        (200, "[" * 100_000, ("FAILED", "BAD_RESPONSE", 2)),
        (301, "", ("FAILED", "REDIRECT_REFUSED", 3)),
        (401, "", ("FAILED", "AUTH_FAILED", 4)),
        (403, "", ("FAILED", "AUTH_FAILED", 4)),
        (404, "", ("FAILED", "MODEL_NOT_FOUND", 4)),
        (400, "", ("FAILED", "REQUEST_REJECTED", 4)),
        (429, "", ("FAILED", "RATE_LIMITED", 4)),
        (500, "", ("FAILED", "PROVIDER_ERROR", 5)),
        (503, "", ("FAILED", "PROVIDER_ERROR", 5)),
    ],
)
def test_adapter_classification(status, body, expected):
    outcome = adapter_for("OPENAI_COMPATIBLE").classify(
        egress.HttpResult(status, body.encode("latin-1"), "application/json")
    )
    assert (outcome.status, outcome.error_code, outcome.http_status_class) == expected


# ------------------------------------------------- outcome mapping in the service


def prepared(endpoint, provider_type="INTERNAL", policy=None, scheme="NONE"):
    policy = policy or loopback_policy(egress.parse_target(endpoint).port)
    return testing._Prepared(
        test_id=uuid4(), model_id=uuid4(), provider_id=uuid4(), provider_type=provider_type,
        endpoint=endpoint, api_style="OPENAI_COMPATIBLE", auth_scheme=scheme,
        auth_header_name=None, technical_id="m", connection_version=1,
        credential_version=None, secret=None, policy=policy,
    )


def test_exchange_maps_every_failure_to_a_fixed_code(provider, monkeypatch):
    ok = provider()
    assert testing._exchange(prepared(f"http://127.0.0.1:{ok.port}/v1"))[0].status == "PASSED"
    blocked = testing._exchange(prepared(f"http://127.0.0.1:{ok.port}/v1", policy=egress.EgressPolicy()))
    assert blocked[0].error_code == "ENDPOINT_BLOCKED"
    closed = socket.create_server(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    assert testing._exchange(prepared(f"http://127.0.0.1:{port}/v1"))[0].error_code == "NETWORK_ERROR"
    garbage = provider(lambda c, r: c.sendall(b"NOT HTTP AT ALL\r\n\r\n"))
    outcome = testing._exchange(prepared(f"http://127.0.0.1:{garbage.port}/v1"))[0]
    assert outcome.error_code == "BAD_RESPONSE"
    monkeypatch.setattr(egress, "TOTAL_TIMEOUT", 0.5)
    monkeypatch.setattr(egress.post, "__kwdefaults__", {"timeouts": FAST, "max_bytes": 10})
    big = provider(lambda c, r: c.sendall(http_response(200, b"x" * 100)))
    assert testing._exchange(prepared(f"http://127.0.0.1:{big.port}/v1"))[0].error_code == (
        "RESPONSE_TOO_LARGE"
    )
    slow = provider(lambda c, r: (time.sleep(3), c.sendall(http_response(200))))
    outcome, latency = testing._exchange(prepared(f"http://127.0.0.1:{slow.port}/v1"))
    assert outcome.error_code == "TIMEOUT" and 900 <= latency < 2500

    def explode(*args, **kwargs):
        raise RuntimeError(f"Illegal header value {SECRET}")

    monkeypatch.setattr(egress, "post", explode)
    outcome, _ = testing._exchange(prepared("http://127.0.0.1:1/v1"))
    assert outcome.error_code == "TEST_ERROR"  # the message (with a secret) is dropped


def test_app_silences_httpcore_debug_traces(provider, caplog):
    """httpcore traces include provider response headers; the app keeps them out."""
    from aq_uai_api.main import create_app

    create_app()
    caplog.set_level(logging.DEBUG)
    server = provider(
        lambda c, r: c.sendall(http_response(200, b"{}", [("X-Provider-Text", "leaky-header")]))
    )
    internal_post(server)
    assert not [record for record in caplog.records if record.name.startswith("httpcore")]
    assert "leaky-header" not in caplog.text


def test_host_header_authority_forms():
    assert egress.parse_target("http://[FD12::5]:8000/v1").authority == "[fd12::5]:8000"
    assert egress.parse_target("http://ollama:80/v1").authority == "ollama"
    assert egress.parse_target("https://api.vendor-a.test:443").path == "/"


# ------------------------------------------------------------ M5 review additions


def test_credentials_are_never_sent_without_tls(provider):
    server = provider()
    with pytest.raises(egress.EgressBlocked):
        internal_post(server, headers=[(b"Authorization", b"Bearer x")], sends_credential=True)
    assert server.connections == 0
    assert internal_post(server).status == 200  # no credential: plain http stays allowed


def test_internal_https_trusts_the_operator_ca_file(provider, pki, tmp_path):
    server = provider(tls=pki["server_context"]("models.internal"))
    ca_file = tmp_path / "internal-ca.pem"
    ca_file.write_text(pki["ca"])
    endpoint = f"https://models.internal:{server.port}/v1"

    def post(policy):
        return egress.post(
            policy, "INTERNAL", endpoint, PATH_SUFFIX, [(b"Authorization", b"Bearer x")], b"{}",
            sends_credential=True, timeouts=FAST,
        )

    setting = f"127.0.0.1/32:{server.port}"
    original = egress.resolve
    egress.resolve = lambda host, port, timeout: [ipaddress.ip_address("127.0.0.1")]
    try:
        with pytest.raises(httpcore.ConnectError) as caught:  # system store only
            post(egress.EgressPolicy.from_setting(setting))
        assert testing._tls_failure(caught.value)
        assert post(egress.EgressPolicy.from_setting(setting, str(ca_file))).status == 200
        assert server.sni[-1] == "models.internal"
        with pytest.raises(egress.TrustStoreUnavailable):
            post(egress.EgressPolicy.from_setting(setting, str(tmp_path / "missing.pem")))
    finally:
        egress.resolve = original
    # The internal CA is never trusted for external providers.
    assert egress.EgressPolicy.from_setting("", str(ca_file)).internal_ca_file == str(ca_file)


def test_abandoned_lookup_threads_are_bounded(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: release.wait(5) and [])
    monkeypatch.setattr(egress, "_LOOKUPS", threading.BoundedSemaphore(2))
    for _ in range(2):
        with pytest.raises(egress.EgressTimeout):
            egress.resolve("slow.test", 443, 0.05)
    started = time.monotonic()
    with pytest.raises(egress.EgressTimeout):  # no third thread is started
        egress.resolve("slow.test", 443, 5)
    assert time.monotonic() - started < 0.5
    release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not egress._LOOKUPS.acquire(blocking=False):
        time.sleep(0.01)
    egress._LOOKUPS.release()


def test_v2_style_sends_max_completion_tokens():
    request = adapter_for("OPENAI_COMPATIBLE_V2").build("o-model", "NONE", None, None)
    body = json.loads(request.body)
    assert body["max_completion_tokens"] == 16 and "max_tokens" not in body
    assert request.body == probe_body("o-model", "max_completion_tokens")
    assert "max_tokens" in json.loads(adapter_for("OPENAI_COMPATIBLE").build("m", "NONE", None, None).body)
