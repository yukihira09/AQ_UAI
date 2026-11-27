"""Adapter contract shared by every API style."""

from dataclasses import dataclass, field
from typing import Literal, Protocol, get_args

from pydantic import SecretStr

from aq_uai_api.mdl.egress import HttpResult

# Fixed failure classes stored in ``mdl_connection_tests.error_code`` (format-checked by
# the database). Provider text is never stored; only one of these codes is.
FailureCode = Literal[
    "AUTH_FAILED",  # 401/403
    "MODEL_NOT_FOUND",  # 404
    "RATE_LIMITED",  # 429
    "REQUEST_REJECTED",  # other 4xx
    "PROVIDER_ERROR",  # 5xx
    "REDIRECT_REFUSED",  # 3xx: redirects are never followed
    "BAD_RESPONSE",  # 2xx without the expected shape, encoded body or protocol error
    "RESPONSE_TOO_LARGE",
    "TIMEOUT",
    "DNS_FAILED",
    "TLS_ERROR",
    "NETWORK_ERROR",
    "ENDPOINT_BLOCKED",  # the egress policy refused the destination
    "TEST_ERROR",  # unexpected local failure; details are never exposed
    "STALE_CONFIGURATION",  # provider connection or credential changed meanwhile
    "ABORTED",  # the tester lost authority before the result could be recorded
    "EXPIRED",  # a RUNNING row was left behind (crash) and closed later
]
FAILURE_CODES: tuple[str, ...] = get_args(FailureCode)


@dataclass(frozen=True)
class ProbeRequest:
    """One fixed request. ``headers`` may hold the plaintext credential: never log,
    repr or persist this object."""

    suffix: str
    headers: tuple[tuple[bytes, bytes], ...] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True)
class Outcome:
    status: Literal["PASSED", "FAILED"]
    error_code: str | None = None
    http_status_class: int | None = None


class Adapter(Protocol):
    def build(
        self,
        technical_id: str,
        auth_scheme: str,
        auth_header_name: str | None,
        secret: SecretStr | None,
    ) -> ProbeRequest: ...

    def classify(self, result: HttpResult) -> Outcome: ...
