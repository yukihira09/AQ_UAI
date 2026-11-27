"""Loopback-only OpenAI-compatible stand-in for MDL integration tests (M4, M5).

It serves HTTPS with a throwaway CA created per test session and a certificate for the
IP address 127.0.0.1. Tests trust that CA through the operator setting
``AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE`` and allow ``127.0.0.1/32:<port>`` through
``AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST``, exactly as an operator would configure an
on-premise model server. Nothing leaves the machine and nothing can be billed.
"""

import datetime
import ipaddress
import json
import ssl
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

OK_BODY = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}}]}
REPLIES = {
    "ok": (200, json.dumps(OK_BODY).encode(), {}),
    "auth": (401, b'{"error": "bad key"}', {}),
    "missing": (404, b'{"error": "no such model"}', {}),
    "bad": (200, b'{"unexpected": true}', {}),
    "server": (500, b"oops", {}),
    "redirect": (302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"}),
}


def _name(text):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


class ProviderPki:
    """A CA and one server certificate for 127.0.0.1, written to a private temp dir."""

    def __init__(self):
        self.folder = Path(tempfile.mkdtemp(prefix="aq-mdl-pki-"))
        now = datetime.datetime.now(datetime.UTC)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca = (
            x509.CertificateBuilder()
            .subject_name(_name("MDL test CA"))
            .issuer_name(_name("MDL test CA"))
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name("127.0.0.1"))
            .issuer_name(_name("MDL test CA"))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        self.ca_file = self.folder / "ca.pem"
        self.ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        self.cert_file = self.folder / "server.pem"
        self.cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        self.key_file = self.folder / "server.key"
        self.key_file.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    def server_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert_file, self.key_file)
        return context


class LocalProvider:
    """``gate`` holds a reply until released; ``mode`` selects the reply."""

    def __init__(self, pki: ProviderPki):
        self.mode = "ok"
        self.requests: list[dict] = []
        self.entered = threading.Event()
        self.gate: threading.Event | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                outer.entered.set()
                if outer.gate is not None:
                    outer.gate.wait(15)
                status, payload, headers = REPLIES[outer.mode]
                self.send_response(status)
                for name, value in {"Content-Type": "application/json", **headers}.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.socket = pki.server_context().wrap_socket(
            self.server.socket, server_side=True
        )
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, path="/v1"):
        return f"https://127.0.0.1:{self.port}{path}"

    @property
    def allowlist(self):
        return f"127.0.0.1/32:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
