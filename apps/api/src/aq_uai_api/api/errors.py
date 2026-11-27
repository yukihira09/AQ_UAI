"""Safe API failures and server-generated request identifiers."""

import logging
import re
from collections.abc import Mapping
from enum import Enum
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"
_PRIVATE_API_PATHS = tuple(
    f"/api/v1/{resource}"
    for resource in (
        "auth",
        "users",
        "units",
        "groups",
        "roles",
        "audit-events",
        "directory",
        "mdl",
        "qta",
    )
)


class ErrorCode(Enum):
    AUTH_REQUIRED = (401, "Authentication is required.")
    FORBIDDEN = (403, "Permission denied.")
    NOT_FOUND = (404, "The resource was not found.")
    CONFLICT = (409, "The requested change conflicts with existing data.")
    VALIDATION_FAILED = (422, "Request validation failed.")
    RATE_LIMITED = (429, "Too many requests.")
    SERVICE_UNAVAILABLE = (503, "The service is unavailable.")
    INTERNAL_ERROR = (500, "An internal error occurred.")
    DATABASE_ERROR = (500, "The database operation failed.")
    # MDL codes are appended: _http_error maps a bare HTTP status to the first member that
    # carries it, so these must stay after the generic codes above.
    MDL_DPA_REQUIRED = (409, "A recorded data-protection agreement is required.")
    MDL_CREDENTIAL_REQUIRED = (422, "A credential is required for this change.")
    MDL_CREDENTIAL_UNAVAILABLE = (503, "The stored credential cannot be used.")
    MDL_ENDPOINT_BLOCKED = (422, "The endpoint is not allowed by network policy.")
    MDL_MODEL_IN_USE = (409, "The model is in use and cannot be deactivated.")
    MDL_NOT_ELIGIBLE = (409, "The model is not eligible for routing.")
    MDL_ROUTING_CONFLICT = (409, "The routing configuration was changed by someone else.")
    MDL_FALLBACK_EQUALS_PRIMARY = (422, "The fallback model must differ from the primary model.")
    MDL_TEST_IN_PROGRESS = (409, "A connection test is already running for this model.")
    MDL_DUPLICATE = (409, "An entry with the same identity already exists.")
    MDL_RISK_REQUIRED = (422, "A risk level is required for this change.")
    # M4 (connection test). Appended for the same reason as above.
    MDL_TEST_UNSUPPORTED = (409, "Only models with the text capability can be tested.")
    MDL_TEST_COOLDOWN = (429, "This model was tested moments ago. Try again shortly.")
    MDL_CHARGES_NOT_ACKNOWLEDGED = (
        422,
        "Acknowledge that the provider may charge for this test before running it.",
    )
    # QTA (Phase 4, Q1). Appended after MDL codes for the same status-mapping reason.
    QTA_BUDGET_BELOW_ALLOCATED = (
        409,
        "The monthly institutional budget cannot be reduced below the amount already allocated.",
    )
    QTA_INVALID_PERIOD = (422, "Quota periods must be a valid calendar month (YYYY-MM).")
    QTA_GROUP_NOT_ELIGIBLE = (422, "This group is not eligible for AI quota management.")
    QTA_MODEL_NOT_ELIGIBLE = (409, "The model is not eligible for quota configuration.")
    QTA_USER_ALREADY_SUSPENDED = (409, "This account's AI quota is already suspended.")
    QTA_USER_NOT_SUSPENDED = (409, "This account's AI quota is not currently suspended.")
    QTA_RESET_ALREADY_EXECUTED = (
        409,
        "The monthly quota reset has already been executed for this period.",
    )
    QTA_DUPLICATE = (409, "A quota group or policy with the same identity already exists.")
    QTA_PERIOD_NOT_OPEN = (422, "Only the current or next month can be used here.")


_USED_IN_ITEM = re.compile(r"[a-z][a-z0-9_.-]{0,63}")


def _identifiers(value: object, limit: int) -> list[str]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) > limit
        or not all(isinstance(item, str) and _USED_IN_ITEM.fullmatch(item) for item in value)
    ):
        raise ValueError("Error details must be a short list of lowercase identifiers.")
    return list(value)


def _used_in(value: object) -> list[str]:
    return _identifiers(value, 16)


def _reasons(value: object) -> list[str]:
    # Two routing slots times every eligibility code, with room for later codes.
    return _identifiers(value, 48)


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Numeric error details must be non-negative integers.")
    return value


# Only these keys can ever reach a client. Each validator accepts fixed, non-user-controlled
# shapes, so adding a key is a reviewed contract change rather than a free-form message.
# ``reasons`` (M5): fixed eligibility codes such as ``primary.dpa_missing``; same shape rule.
# ``deficit`` / ``allocated`` (Q1, FR-QTA-011): non-negative integers for cap reduction checks.
_DETAIL_VALIDATORS = {
    "used_in": _used_in,
    "reasons": _reasons,
    "deficit": _non_negative_int,
    "allocated": _non_negative_int,
}


class DomainError(Exception):
    def __init__(self, code: ErrorCode, details: Mapping[str, object] | None = None):
        super().__init__(code.name)
        self.code = code
        checked = {}
        for key, value in (details or {}).items():
            validator = _DETAIL_VALIDATORS.get(key)
            if validator is None:
                raise ValueError("Unsupported error detail.")
            checked[key] = validator(value)
        self.details = checked or None


class DiagnosticUnavailable(Exception):
    """Preserve the existing Phase 1 diagnostic error contract."""


def _log_failure(request_id: str, code: str, status: int) -> None:
    logger.warning("request_failed request_id=%s code=%s status=%d", request_id, code, status)


def _error_response(
    request_id: str, code: ErrorCode, details: Mapping[str, object] | None = None
) -> JSONResponse:
    status, message = code.value
    _log_failure(request_id, code.name, status)
    body = {"code": code.name, "message": message, "request_id": request_id}
    if details:
        body["details"] = dict(details)
    return JSONResponse(body, status_code=status)


class RequestContextMiddleware:
    """Catch failures before the ASGI server can log their exception text."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                if any(
                    scope["path"] == path or scope["path"].startswith(path + "/")
                    for path in _PRIVATE_API_PATHS
                ):
                    headers["Cache-Control"] = "no-store"
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            if response_started:
                _log_failure(request_id, "RESPONSE_INTERRUPTED", 500)
                raise RuntimeError("API response interrupted") from None
            if isinstance(exc, IntegrityError) and getattr(exc.orig, "sqlstate", None) == "23505":
                code = ErrorCode.CONFLICT
            elif isinstance(exc, SQLAlchemyError):
                code = ErrorCode.DATABASE_ERROR
            else:
                code = ErrorCode.INTERNAL_ERROR
            await _error_response(request_id, code)(scope, receive, send_with_id)


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return _error_response(request.state.request_id, exc.code, exc.details)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's input values, error context, and locations can contain user-controlled text.
    return _error_response(request.state.request_id, ErrorCode.VALIDATION_FAILED)


async def _http_error(request: Request, exc: HTTPException) -> Response:
    if exc.status_code < 400:
        return Response(status_code=exc.status_code, headers=exc.headers)
    for code in ErrorCode:
        if code.value[0] == exc.status_code:
            return _error_response(request.state.request_id, code)
    _log_failure(request.state.request_id, "HTTP_ERROR", exc.status_code)
    headers = None
    if exc.status_code == 405 and exc.headers and "Allow" in exc.headers:
        headers = {"Allow": exc.headers["Allow"]}
    return JSONResponse(
        {
            "code": "HTTP_ERROR",
            "message": "The request failed.",
            "request_id": request.state.request_id,
        },
        status_code=exc.status_code,
        headers=headers,
    )


async def _diagnostic_unavailable(request: Request, exc: DiagnosticUnavailable) -> JSONResponse:
    _log_failure(request.state.request_id, "DATABASE_UNAVAILABLE", 503)
    return JSONResponse(
        {"detail": {"code": "DATABASE_UNAVAILABLE", "message": "Database is not ready"}},
        status_code=503,
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(DiagnosticUnavailable, _diagnostic_unavailable)
