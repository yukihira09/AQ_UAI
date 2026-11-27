"""Synthetic OpenAI-compatible AI provider for local demos and tests (NOT a real vendor).

What: a tiny HTTPS server that answers ``POST /v1/chat/completions`` like an
OpenAI-compatible model server, with a fixed reply and no real model behind it. It lets
the MDL connection test (FR-MDL-020) run end to end on a developer machine with real
TLS, a real credential check and real failure classes, without any external call or
charge.

Why: the project owner decided (MDL decision D15, 2026-11-26) that this demo/test
project uses a synthetic provider instead of a commercial one.

How:
- At start it creates a throwaway certificate authority (CA) and a server certificate
  for the host names in ``AQ_DEMO_PROVIDER_HOSTNAMES`` (default ``demo-provider``).
  Private keys stay in a private temporary folder inside this container; only the
  *public* CA certificate is written to ``AQ_DEMO_PROVIDER_CA_DIR/ca.pem`` so the API
  can trust it (``AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE``). TLS verification stays on.
- It accepts the key from ``AQ_DEMO_PROVIDER_API_KEY`` either as ``Authorization:
  Bearer <key>`` or in the ``X-Api-Key`` header. A wrong or missing key gives 401
  (``AUTH_FAILED`` in MDL); an unknown model gives 404 (``MODEL_NOT_FOUND``).
- Models come from ``AQ_DEMO_PROVIDER_MODELS`` (default ``demo-chat,demo-chat-mini``).
- It never logs headers, keys or bodies: one line per request with method, path and
  status only.

Runs with the API image's Python (it needs ``cryptography``); see
``infra/compose.demo-provider.yaml`` and ``docs/phase3/mdl-handoff.md``.
"""

import datetime
import hmac
import ipaddress
import json
import os
import ssl
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

MAX_BODY = 64 * 1024
DEFAULT_MODELS = "demo-chat,demo-chat-mini"
REPLY_TEXT = "OK"


def _name(text: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


def _san(hostnames: list[str]) -> x509.SubjectAlternativeName:
    names: list[x509.GeneralName] = []
    for host in hostnames:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    return x509.SubjectAlternativeName(names)


def publish_ca(ca_dir: Path, pem: bytes) -> None:
    """Write the public CA certificate atomically (readers never see a partial file)."""
    ca_dir.mkdir(parents=True, exist_ok=True)
    staging = ca_dir / ".ca.pem.tmp"
    staging.write_bytes(pem)
    staging.chmod(0o644)
    staging.replace(ca_dir / "ca.pem")


def create_pki(hostnames: list[str], ca_dir: Path, publish: bool = True) -> tuple[ssl.SSLContext, bytes]:
    """Create a CA and server certificate. Returns the server TLS context and the public
    CA certificate (PEM); ``publish`` also writes it to ``ca_dir/ca.pem``."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("AQ EduUAI synthetic demo provider CA"))
        .issuer_name(_name("AQ EduUAI synthetic demo provider CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(hostnames[0]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_san(hostnames), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    private = Path(tempfile.mkdtemp(prefix="aq-demo-provider-"))  # mode 700
    (private / "server.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path = private / "server.key"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(private / "server.pem", key_path)
    pem = ca.public_bytes(serialization.Encoding.PEM)
    if publish:
        publish_ca(ca_dir, pem)
    return context, pem


class DemoProvider:
    """The HTTPS server. ``requests`` keeps (path, status) pairs for tests, never keys."""

    def __init__(self, api_key: str, models: list[str], context: ssl.SSLContext,
                 host: str = "0.0.0.0", port: int = 8443, quiet: bool = False):
        if len(api_key) < 16:
            raise ValueError("AQ_DEMO_PROVIDER_API_KEY must have at least 16 characters.")
        expected = api_key.encode("utf-8")
        known = set(models)
        outer = self
        self.requests: list[tuple[str, int]] = []

        class Handler(BaseHTTPRequestHandler):
            server_version = "AQ-Demo-Provider/1"
            sys_version = ""

            def _send(self, status: int, document: dict) -> None:
                payload = json.dumps(document).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                outer.requests.append((self.path, status))

            def _error(self, status: int, code: str, message: str) -> None:
                self._send(status, {"error": {"type": code, "code": code, "message": message}})

            def _authorized(self) -> bool:
                bearer = self.headers.get("Authorization", "")
                supplied = bearer[7:] if bearer.startswith("Bearer ") else self.headers.get("X-Api-Key", "")
                return hmac.compare_digest(supplied.encode("utf-8"), expected)

            def do_GET(self):
                if self.path.rstrip("/") != "/v1/models":
                    return self._error(404, "not_found", "Unknown path.")
                if not self._authorized():
                    return self._error(401, "invalid_api_key", "Invalid API key.")
                return self._send(200, {"object": "list", "data": [
                    {"id": model, "object": "model", "owned_by": "aq-demo"} for model in sorted(known)
                ]})

            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    return self._error(404, "not_found", "Unknown path.")
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY:
                    return self._error(400, "invalid_request", "Missing or oversized body.")
                raw = self.rfile.read(length)
                if not self._authorized():
                    return self._error(401, "invalid_api_key", "Invalid API key.")
                try:
                    request = json.loads(raw)
                except ValueError:
                    return self._error(400, "invalid_request", "Body is not JSON.")
                if not isinstance(request, dict) or not isinstance(request.get("messages"), list):
                    return self._error(400, "invalid_request", "A messages list is required.")
                model = request.get("model")
                if model not in known:
                    return self._error(404, "model_not_found", "The model does not exist.")
                if request.get("stream"):
                    return self._error(400, "invalid_request", "Streaming is not supported.")
                return self._send(200, {
                    "id": f"chatcmpl-demo-{int(time.time() * 1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": REPLY_TEXT},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1},
                    "system_fingerprint": "aq-demo-synthetic",
                })

            def log_message(self, format, *args):
                if not quiet:  # method, path and status only; never headers or bodies
                    sys.stdout.write(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else '-'}\n")
                    sys.stdout.flush()

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]

    def start(self) -> "DemoProvider":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def main() -> int:
    api_key = os.environ.get("AQ_DEMO_PROVIDER_API_KEY", "")
    models = [m.strip() for m in os.environ.get("AQ_DEMO_PROVIDER_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
    hostnames = [h.strip() for h in os.environ.get("AQ_DEMO_PROVIDER_HOSTNAMES", "demo-provider").split(",") if h.strip()]
    ca_dir = Path(os.environ.get("AQ_DEMO_PROVIDER_CA_DIR", "/run/demo-provider-ca"))
    port = int(os.environ.get("AQ_DEMO_PROVIDER_PORT", "8443"))
    # A CA left by a previous run would make the health check pass before this server
    # listens; remove it, bind first, then publish the new CA.
    (ca_dir / "ca.pem").unlink(missing_ok=True)
    try:
        context, pem = create_pki(hostnames, ca_dir, publish=False)
        provider = DemoProvider(api_key, models, context, port=port)
    except ValueError as error:
        print(f"Demo provider not started: {error}", file=sys.stderr)
        return 1
    publish_ca(ca_dir, pem)
    print(f"Synthetic demo provider on https://{hostnames[0]}:{port}/v1 models={','.join(models)}", flush=True)
    provider.server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
