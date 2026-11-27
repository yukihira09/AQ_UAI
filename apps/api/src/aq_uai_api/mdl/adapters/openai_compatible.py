"""Generic OpenAI-compatible chat-completions adapter (D1, decided in M4).

Request: ``POST {endpoint}/chat/completions`` with one fixed user message, a small
``max_tokens`` and ``stream: false``. Nothing from the institution is sent: the only
variable is the model's technical ID (FR-MDL-020). No temperature or other generation
setting is sent (FR-MDL-040).

PASS requires a 2xx status **and** a JSON object with a non-empty ``choices`` list whose
first element has a ``message`` object. That proves the credential and model work, not
merely that the host is reachable. The body is discarded after this check.
"""

import json

from pydantic import SecretStr

from aq_uai_api.mdl.adapters.base import Outcome, ProbeRequest
from aq_uai_api.mdl.egress import HttpResult

PATH_SUFFIX = "/chat/completions"
TEST_MESSAGE = "Reply with the single word OK."
MAX_TOKENS = 16
USER_AGENT = b"AQ-EduUAI-MDL-ConnectionTest/1"


def probe_body(technical_id: str, token_field: str = "max_tokens") -> bytes:
    """The exact bytes sent; tests compare captured requests with this.

    ``token_field`` is ``max_tokens`` (classic) or ``max_completion_tokens`` (V2 style,
    required by newer and reasoning models that reject ``max_tokens``)."""
    return json.dumps(
        {
            "model": technical_id,
            "messages": [{"role": "user", "content": TEST_MESSAGE}],
            token_field: MAX_TOKENS,
            "stream": False,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")


def _status_failure(status: int) -> str:
    if status in (401, 403):
        return "AUTH_FAILED"
    if status == 404:
        return "MODEL_NOT_FOUND"
    if status == 429:
        return "RATE_LIMITED"
    if 300 <= status < 400:
        return "REDIRECT_REFUSED"
    if 400 <= status < 500:
        return "REQUEST_REJECTED"
    if 500 <= status < 600:
        return "PROVIDER_ERROR"
    return "BAD_RESPONSE"


def _has_expected_shape(body: bytes) -> bool:
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False
    if not isinstance(document, dict) or "error" in document:
        return False
    choices = document.get("choices")
    return (
        isinstance(choices, list)
        and bool(choices)
        and isinstance(choices[0], dict)
        and isinstance(choices[0].get("message"), dict)
    )


class OpenAICompatibleAdapter:
    def __init__(self, token_field: str = "max_tokens"):
        self.token_field = token_field

    def build(
        self,
        technical_id: str,
        auth_scheme: str,
        auth_header_name: str | None,
        secret: SecretStr | None,
    ) -> ProbeRequest:
        headers = [
            (b"Content-Type", b"application/json"),
            (b"Accept", b"application/json"),
            (b"Accept-Encoding", b"identity"),
            (b"User-Agent", USER_AGENT),
        ]
        if auth_scheme in ("BEARER", "HEADER_KEY"):
            if secret is None:
                raise ValueError("A credential is required for this scheme.")
            # Control characters were refused when the secret was sealed (D14), so the
            # value cannot split the header.
            value = secret.get_secret_value().encode("utf-8")
            if auth_scheme == "BEARER":
                headers.append((b"Authorization", b"Bearer " + value))
            else:
                if not auth_header_name:
                    raise ValueError("A header name is required for HEADER_KEY.")
                headers.append((auth_header_name.encode("ascii"), value))
        return ProbeRequest(PATH_SUFFIX, tuple(headers), probe_body(technical_id, self.token_field))

    def classify(self, result: HttpResult) -> Outcome:
        status_class = result.status // 100 if 100 <= result.status <= 599 else None
        if not 200 <= result.status < 300:
            return Outcome("FAILED", _status_failure(result.status), status_class)
        if not _has_expected_shape(result.body):
            return Outcome("FAILED", "BAD_RESPONSE", status_class)
        return Outcome("PASSED", None, status_class)


ADAPTER = OpenAICompatibleAdapter()
ADAPTER_V2 = OpenAICompatibleAdapter("max_completion_tokens")
