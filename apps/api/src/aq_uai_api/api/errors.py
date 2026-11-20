"""Safe API failures and server-generated request identifiers."""

import logging
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


class DomainError(Exception):
    def __init__(self, code: ErrorCode):
        super().__init__(code.name)
        self.code = code


class DiagnosticUnavailable(Exception):
    """Preserve the existing Phase 1 diagnostic error contract."""


def _log_failure(request_id: str, code: str, status: int) -> None:
    logger.warning("request_failed request_id=%s code=%s status=%d", request_id, code, status)


def _error_response(request_id: str, code: ErrorCode) -> JSONResponse:
    status, message = code.value
    _log_failure(request_id, code.name, status)
    return JSONResponse(
        {"code": code.name, "message": message, "request_id": request_id},
        status_code=status,
    )


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
                if scope["path"].rstrip("/") == "/api/v1/auth" or scope["path"].startswith(
                    "/api/v1/auth/"
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
    return _error_response(request.state.request_id, exc.code)


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
