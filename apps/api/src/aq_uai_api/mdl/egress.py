"""SSRF-resistant egress for the MDL connection test (M4).

What: the only way MDL code sends a request to an administrator-supplied endpoint.
It enforces the network policy of the architecture (section 6) at three points:

1. **Static policy** on the URL, before any network activity: scheme, port, IP-literal
   and host-name rules, and the operator's internal allowlist.
2. **Connect-time validation and pinning**: the host name is resolved exactly once,
   inside the connection step; *every* returned address must pass the policy; the
   socket is then opened to one of those validated addresses (never re-resolved),
   and the peer address is checked again after connecting. TLS uses the original host
   name for SNI and certificate verification. This closes DNS rebinding: there is no
   second lookup an attacker could answer differently.
3. **Bounded exchange**: fixed method, no redirects (``httpcore`` never follows them;
   a 3xx is reported to the caller), no retries, no proxy (``httpcore`` ignores proxy
   environment variables, unlike ``httpx``), identity encoding only, a response cap
   and per-operation plus total deadlines.

Why: the connection test makes the API server call a URL an administrator typed while
holding a stored secret. Without these rules it could reach PostgreSQL, the API
itself, cloud metadata (169.254.169.254) or other private services.

How to verify: ``tests/unit/test_m4_egress.py`` (address table, endpoint table,
allowlist parsing, rebinding, redirect, oversize, slow responses, TLS/SNI).

Seams: ``resolve``, ``open_connection`` and ``tls_context`` are module-level functions
so tests can supply a resolver, a socket opener and a test CA, exactly like an
operator environment would. They are not bypasses: every resolved address still goes
through :func:`check_addresses`, and nothing here reads a "test mode" flag.

Nothing here logs, and exception messages never contain a host, address, header or
secret.
"""

import ipaddress
import re
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

import httpcore

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
WRITE_TIMEOUT = 5.0
TOTAL_TIMEOUT = 20.0  # below nginx's proxy_read_timeout (30 s)
MAX_RESPONSE_BYTES = 64 * 1024
MAX_ADDRESSES = 16
EXTERNAL_PORT = 443


class EgressBlocked(Exception):
    """The destination is not allowed by the egress policy."""

    def __init__(self) -> None:
        super().__init__("The destination is not allowed by the egress policy.")


class EgressTimeout(Exception):
    """The total deadline expired (DNS, connect, TLS, send or receive)."""

    def __init__(self) -> None:
        super().__init__("The connection test exceeded its time limit.")


class ResolutionFailed(Exception):
    """The host name could not be resolved."""

    def __init__(self) -> None:
        super().__init__("The host name could not be resolved.")


class ResponseTooLarge(Exception):
    def __init__(self) -> None:
        super().__init__("The response exceeded the size limit.")


class TrustStoreUnavailable(Exception):
    """The operator's internal CA file is configured but cannot be loaded."""

    def __init__(self) -> None:
        super().__init__("The internal CA file cannot be loaded.")


class InvalidAllowlist(ValueError):
    def __init__(self) -> None:
        super().__init__("The internal egress allowlist is invalid.")


def _networks(*values: str) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(value) for value in values)


# Never reachable, whatever the allowlist says: "this host", link-local (including
# cloud metadata 169.254.169.254 and fd00:ec2::254's link-local peers), multicast,
# reserved/broadcast, the unspecified address and deprecated site-local IPv6.
ALWAYS_BLOCKED = _networks(
    "0.0.0.0/8",
    "169.254.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "::/128",
    "fe80::/10",
    "fec0::/10",
    "ff00::/8",
)

# External providers must resolve only to public unicast addresses. ``is_global`` is
# checked as well; this explicit list keeps the rule stable across Python versions and
# also rejects IPv6 forms that embed or translate to IPv4 (mapped, compatible, 6to4,
# Teredo, NAT64), which could otherwise reach private IPv4 space.
EXTERNAL_BLOCKED = ALWAYS_BLOCKED + _networks(
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "::1/128",
    "::/96",
    "::ffff:0:0/96",
    "64:ff9b::/96",
    "64:ff9b:1::/48",
    "100::/64",
    "2001::/23",
    "2001:db8::/32",
    "2002::/16",
    "3fff::/20",
    "fc00::/7",
)

_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")
_NUMERIC_HOST = re.compile(r"(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*")


def _host_name(value: str) -> str | None:
    """Return a canonical ASCII host name, or None if it is not a plain DNS name.

    Only lower-case LDH labels are accepted (punycode ``xn--`` labels are LDH). Unicode
    host names are refused rather than IDNA-converted, because conversion can turn
    look-alike text (for example full-width digits) into an IP address.
    """
    host = value.lower().removesuffix(".")
    if not host or len(host) > 253 or not host.isascii():
        return None
    labels = host.split(".")
    if not all(_LABEL.fullmatch(label) for label in labels):
        return None
    # Decimal, octal, hex and short forms such as 2130706433, 0177.1 or 0x7f.1 are
    # numbers that resolvers turn into addresses; they are never host names here.
    if _NUMERIC_HOST.fullmatch(host) or labels[-1].isdigit():
        return None
    return host


def unwrap(address: IPAddress) -> IPAddress:
    """An IPv4-mapped IPv6 address is judged as the IPv4 address it reaches."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _in_any(address: IPAddress, networks: Iterable[IPNetwork]) -> bool:
    return any(address.version == net.version and address in net for net in networks)


def is_public(address: IPAddress) -> bool:
    """External rule: globally routable and outside every special-purpose range."""
    return address.is_global and not _in_any(address, EXTERNAL_BLOCKED)


def _port(text: str) -> int:
    if not text.isdigit() or not 1 <= int(text) <= 65535 or text != str(int(text)):
        raise InvalidAllowlist()
    return int(text)


@dataclass(frozen=True)
class InternalAllowlist:
    """Operator-configured destinations for INTERNAL providers (never set from the UI).

    Every entry names a destination **and one port** (M5 review: an entry without a port
    let an MDL administrator reach any port of an allowed host):

    - ``host:port``   host name, exact match, case-insensitive (``ollama:11434``);
    - ``a.b.c.d[/n]:port``   IPv4 address or CIDR (``10.20.0.0/16:8000``);
    - ``[v6addr[/n]]:port``   IPv6 address or CIDR in brackets (``[fd12::/64]:8000``).

    Several ports for one host need several entries.
    """

    hosts: frozenset[tuple[str, int]] = frozenset()
    networks: tuple[tuple[IPNetwork, int], ...] = ()

    @classmethod
    def parse(cls, raw: str) -> "InternalAllowlist":
        hosts: set[tuple[str, int]] = set()
        networks: list[tuple[IPNetwork, int]] = []
        for entry in (item.strip() for item in raw.split(",")):
            if not entry:
                continue
            if entry.startswith("["):
                inner, closing, rest = entry[1:].partition("]")
                if not closing or not rest.startswith(":"):
                    raise InvalidAllowlist()
                address, port = inner, _port(rest[1:])
            else:
                address, colon, port_text = entry.rpartition(":")
                if not colon or ":" in address:
                    raise InvalidAllowlist()  # missing port, or unbracketed IPv6
                port = _port(port_text)
            try:
                network = ipaddress.ip_network(address, strict=True)
            except ValueError:
                host = _host_name(address)
                if host is None or "/" in address or entry.startswith("["):
                    raise InvalidAllowlist() from None
                hosts.add((host, port))
                continue
            # Over-broad or always-blocked ranges are configuration mistakes: refuse
            # them loudly instead of silently ignoring part of the range.
            minimum_prefix = 8 if network.version == 4 else 16
            if network.prefixlen < minimum_prefix or any(
                network.version == blocked.version and network.overlaps(blocked)
                for blocked in ALWAYS_BLOCKED
            ):
                raise InvalidAllowlist()
            networks.append((network, port))
        return cls(frozenset(hosts), tuple(networks))

    @property
    def empty(self) -> bool:
        return not self.hosts and not self.networks

    def __len__(self) -> int:
        return len(self.hosts) + len(self.networks)

    def networks_for(self, port: int) -> tuple[IPNetwork, ...]:
        return tuple(network for network, allowed in self.networks if allowed == port)

    def has_host(self, host: str, port: int) -> bool:
        return (host, port) in self.hosts


@dataclass(frozen=True)
class Target:
    """A validated destination. ``host`` is what TLS verifies and Host carries."""

    scheme: str
    host: str
    port: int
    path: str
    ip_literal: IPAddress | None

    @property
    def authority(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.scheme == "https" else 80
        return host if self.port == default else f"{host}:{self.port}"


def parse_target(endpoint: str, suffix: str = "") -> Target:
    """Parse ``endpoint + suffix`` strictly. Raises :class:`EgressBlocked`."""
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise EgressBlocked() from None
    scheme = parts.scheme.lower()
    raw_host = parts.hostname or ""
    if (
        scheme not in ("http", "https")
        or "@" in parts.netloc
        or parts.query
        or parts.fragment
        or "?" in endpoint
        or "#" in endpoint
        or not raw_host
        or "%" in raw_host
        or any(character.isspace() or ord(character) < 0x20 for character in endpoint)
    ):
        raise EgressBlocked()
    try:
        literal: IPAddress | None = ipaddress.ip_address(raw_host)
    except ValueError:
        literal = None
    if literal is not None:
        host = literal.compressed
    else:
        named = _host_name(raw_host)
        if named is None:
            raise EgressBlocked()
        host = named
    path = quote(parts.path.rstrip("/") + suffix, safe="/-._~!$&'()*+,;=:@%")
    return Target(
        scheme=scheme,
        host=host,
        port=port or (443 if scheme == "https" else 80),
        path=path or "/",
        ip_literal=literal,
    )


@dataclass(frozen=True)
class EgressPolicy:
    allowlist: InternalAllowlist = field(default_factory=InternalAllowlist)
    allowlist_valid: bool = True
    # Operator-supplied CA bundle trusted for INTERNAL https providers only (M5 review).
    internal_ca_file: str | None = None

    @classmethod
    def from_setting(cls, raw: str, internal_ca_file: str = "") -> "EgressPolicy":
        ca_file = internal_ca_file.strip() or None
        try:
            return cls(InternalAllowlist.parse(raw), internal_ca_file=ca_file)
        except InvalidAllowlist:
            # Fail closed: an unreadable allowlist permits no internal destination.
            return cls(InternalAllowlist(), allowlist_valid=False, internal_ca_file=ca_file)

    def check_target(self, provider_type: str, target: Target) -> None:
        """Static rules, applied before any DNS lookup or connection."""
        if provider_type == "EXTERNAL":
            if (
                target.scheme != "https"
                or target.port != EXTERNAL_PORT
                or target.ip_literal is not None
                or "." not in target.host  # single-label names resolve to local services
                or target.host == "localhost"
                or target.host.endswith(".localhost")
            ):
                raise EgressBlocked()
            return
        if provider_type != "INTERNAL" or self.allowlist.empty:
            raise EgressBlocked()
        if target.ip_literal is not None:
            self.check_addresses(provider_type, target, [target.ip_literal])
        elif not self.allowlist.has_host(target.host, target.port) and not (
            self.allowlist.networks_for(target.port)
        ):
            raise EgressBlocked()

    def check_addresses(
        self, provider_type: str, target: Target, addresses: Sequence[IPAddress]
    ) -> None:
        """Every resolved address must pass, or the destination is refused."""
        if not addresses or len(addresses) > MAX_ADDRESSES:
            raise EgressBlocked()
        for address in addresses:
            if provider_type == "EXTERNAL":
                if not is_public(address):
                    raise EgressBlocked()
                continue
            if provider_type != "INTERNAL":
                raise EgressBlocked()
            plain = unwrap(address)
            if _in_any(plain, ALWAYS_BLOCKED):
                raise EgressBlocked()  # the blocklist always wins
            if _in_any(plain, self.allowlist.networks_for(target.port)):
                continue
            # A host-name entry trusts the operator's DNS, but never for loopback: the
            # API container reaching itself needs an explicit CIDR entry.
            if self.allowlist.has_host(target.host, target.port) and not plain.is_loopback:
                continue
            raise EgressBlocked()


# ----------------------------------------------------------------------------- seams


# At most this many lookup threads may exist at once, including abandoned ones that are
# still waiting for a slow resolver (M5 review: abandoned threads were unbounded).
MAX_LOOKUP_THREADS = 8
_LOOKUPS = threading.BoundedSemaphore(MAX_LOOKUP_THREADS)


def resolve(host: str, port: int, timeout: float) -> list[IPAddress]:
    """Resolve once with a deadline. ``getaddrinfo`` has no timeout of its own, so it
    runs in a daemon thread that is abandoned (not waited for) when time runs out. The
    thread releases its slot only when the lookup really ends."""
    if not _LOOKUPS.acquire(blocking=False):
        raise EgressTimeout()
    result: dict[str, object] = {}

    def lookup() -> None:
        try:
            result["value"] = socket.getaddrinfo(
                host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        except OSError:
            result["error"] = True
        finally:
            _LOOKUPS.release()

    worker = threading.Thread(target=lookup, name="mdl-egress-dns", daemon=True)
    try:
        worker.start()
    except RuntimeError:
        _LOOKUPS.release()
        raise EgressTimeout() from None
    worker.join(max(timeout, 0.0))
    if worker.is_alive():
        raise EgressTimeout()
    if "error" in result:
        raise ResolutionFailed()
    addresses: list[IPAddress] = []
    for _family, _type, _proto, _name, sockaddr in result.get("value", []):  # type: ignore[union-attr]
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise EgressBlocked() from None  # e.g. a scoped "fe80::1%eth0"
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ResolutionFailed()
    return addresses


def open_connection(address: IPAddress, port: int, timeout: float) -> httpcore.NetworkStream:
    """Open TCP to an already validated address literal and confirm the peer."""
    stream = httpcore.SyncBackend().connect_tcp(str(address), port, timeout=timeout)
    try:
        peer = ipaddress.ip_address(stream.get_extra_info("server_addr")[0])
    except (TypeError, ValueError, OSError):
        stream.close()
        raise EgressBlocked() from None
    if unwrap(peer) != unwrap(address):
        stream.close()
        raise EgressBlocked()
    return stream


def tls_context(extra_ca_file: str | None = None) -> ssl.SSLContext:
    """System trust store, plus the operator's internal CA file when one is configured
    (internal providers only). Verification and host-name checking always stay on."""
    context = ssl.create_default_context()  # CERT_REQUIRED + host-name checking
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if extra_ca_file:
        try:
            context.load_verify_locations(cafile=extra_ca_file)
        except (OSError, ssl.SSLError, ValueError):
            raise TrustStoreUnavailable() from None
    return context


# ----------------------------------------------------------------------- transport


class _Deadline:
    def __init__(self, seconds: float):
        self._end = time.monotonic() + seconds

    def remaining(self, limit: float | None = None) -> float:
        left = self._end - time.monotonic()
        if left <= 0:
            raise EgressTimeout()
        return left if limit is None else min(limit, left)


class _DeadlineStream(httpcore.NetworkStream):
    """Caps every socket operation by the total deadline (defeats slow-drip replies)."""

    def __init__(self, inner: httpcore.NetworkStream, deadline: _Deadline):
        self._inner = inner
        self._deadline = deadline

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._inner.read(max_bytes, self._deadline.remaining(timeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._inner.write(buffer, self._deadline.remaining(timeout))

    def close(self) -> None:
        self._inner.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        upgraded = self._inner.start_tls(
            ssl_context, server_hostname, self._deadline.remaining(timeout)
        )
        return _DeadlineStream(upgraded, self._deadline)

    def get_extra_info(self, info: str):
        return self._inner.get_extra_info(info)


class _PinnedBackend(httpcore.NetworkBackend):
    """Resolves, validates and connects in one step, to one validated address."""

    def __init__(
        self,
        policy: EgressPolicy,
        provider_type: str,
        target: Target,
        deadline: _Deadline,
        resolver: Callable[[str, int, float], list[IPAddress]],
        opener: Callable[[IPAddress, int, float], httpcore.NetworkStream],
    ):
        self._policy = policy
        self._provider_type = provider_type
        self._target = target
        self._deadline = deadline
        self._resolver = resolver
        self._opener = opener

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        if host != self._target.host or port != self._target.port or local_address:
            raise EgressBlocked()  # the pool may only ever open the validated target
        limit = timeout if timeout is not None else CONNECT_TIMEOUT
        if self._target.ip_literal is not None:
            addresses = [self._target.ip_literal]
        else:
            addresses = self._resolver(host, port, self._deadline.remaining(limit))
        self._policy.check_addresses(self._provider_type, self._target, addresses)
        failure: Exception | None = None
        for address in addresses:  # each one already validated; never re-resolved
            try:
                stream = self._opener(address, port, self._deadline.remaining(limit))
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                failure = exc
                continue
            return _DeadlineStream(stream, self._deadline)
        raise failure or httpcore.ConnectError("No address could be reached.")

    def connect_unix_socket(self, path: str, timeout=None, socket_options=None):
        raise EgressBlocked()

    def sleep(self, seconds: float) -> None:  # used only by retries, which are disabled
        raise EgressBlocked()


@dataclass(frozen=True)
class HttpResult:
    """What a caller may learn from the exchange. The body is bounded and must be
    discarded by the caller after classification; it is never stored or logged."""

    status: int
    body: bytes = field(repr=False)
    content_type: str | None


@dataclass(frozen=True)
class Timeouts:
    connect: float = CONNECT_TIMEOUT
    read: float = READ_TIMEOUT
    write: float = WRITE_TIMEOUT
    total: float = TOTAL_TIMEOUT


def post(
    policy: EgressPolicy,
    provider_type: str,
    endpoint: str,
    suffix: str,
    headers: Sequence[tuple[bytes, bytes]],
    body: bytes,
    *,
    sends_credential: bool = False,
    timeouts: Timeouts = Timeouts(),
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> HttpResult:
    """Send one POST through the policy. Raises the exceptions defined above or
    ``httpcore`` network/protocol exceptions; the caller maps them to error codes.

    ``sends_credential``: a stored secret is never sent without TLS (M5 review), for
    internal providers too; registration enforces the same rule.
    """
    target = parse_target(endpoint, suffix)
    policy.check_target(provider_type, target)
    if sends_credential and target.scheme != "https":
        raise EgressBlocked()
    deadline = _Deadline(timeouts.total)
    backend = _PinnedBackend(policy, provider_type, target, deadline, resolve, open_connection)
    url = httpcore.URL(
        scheme=target.scheme.encode(),
        host=target.host.encode("ascii"),
        port=target.port,
        target=target.path.encode("ascii"),
    )
    request_headers = [(b"Host", target.authority.encode("ascii")), *headers]
    extensions = {
        "timeout": {
            "connect": timeouts.connect,
            "read": timeouts.read,
            "write": timeouts.write,
            "pool": timeouts.connect,
        }
    }
    with httpcore.ConnectionPool(
        ssl_context=(
            tls_context(policy.internal_ca_file if provider_type == "INTERNAL" else None)
            if target.scheme == "https"
            else None
        ),
        max_connections=1,
        retries=0,
        http1=True,
        http2=False,
        network_backend=backend,
    ) as pool:
        with pool.stream(
            "POST", url, headers=request_headers, content=body, extensions=extensions
        ) as response:
            content_type = _header(response.headers, b"content-type")
            if response.status < 200 or response.status >= 300:
                # Redirects are never followed and error bodies are not needed.
                return HttpResult(response.status, b"", content_type)
            encoding = _header(response.headers, b"content-encoding")
            if encoding not in (None, "identity"):
                return HttpResult(response.status, b"", "application/x-encoded")
            declared = _header(response.headers, b"content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > max_bytes):
                raise ResponseTooLarge()
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_stream():
                size += len(chunk)
                if size > max_bytes:
                    raise ResponseTooLarge()
                chunks.append(chunk)
                deadline.remaining()
            return HttpResult(response.status, b"".join(chunks), content_type)


def _header(headers: Sequence[tuple[bytes, bytes]], name: bytes) -> str | None:
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1").strip().lower()
    return None
