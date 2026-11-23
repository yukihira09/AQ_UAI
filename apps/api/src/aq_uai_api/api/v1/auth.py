"""Cookie-authenticated HTTP interface for the local identity service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aq_uai_api.auth import service
from aq_uai_api.auth.security import (
    COOKIE_NAME,
    CSRF_HEADER,
    PASSWORD_MAX,
    PASSWORD_MIN,
    SESSION_SECONDS,
    client_peer,
    csrf_token,
    require_origin,
)
from aq_uai_api.core.config import get_settings
from aq_uai_api.db.identity import User
from aq_uai_api.db.session import get_session

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _utf8_password(value: str) -> str:
    value.encode("utf-8")
    return value


CurrentPassword = Annotated[
    str, Field(min_length=1, max_length=PASSWORD_MAX), AfterValidator(_utf8_password)
]
NewPassword = Annotated[
    str, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX), AfterValidator(_utf8_password)
]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Annotated[str, Field(max_length=256)]
    password: CurrentPassword


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: CurrentPassword
    new_password: NewPassword


class CurrentUser(BaseModel):
    id: UUID
    username: str
    display_name: str
    institution_id: UUID
    primary_unit_id: UUID
    state: str
    must_change_password: bool
    csrf_token: str


def _current_session(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> service.AuthenticatedSession:
    return service.authenticate_session(db, request.cookies.get(COOKIE_NAME))


def require_unrestricted_session(
    principal: Annotated[service.AuthenticatedSession, Depends(_current_session)],
) -> service.AuthenticatedSession:
    return service.require_unrestricted(principal)


def require_authenticated_user(
    principal: Annotated[service.AuthenticatedSession, Depends(require_unrestricted_session)],
) -> User:
    """Default dependency for future protected routes. Authorization is separate."""
    return principal.user


@router.post("/login", status_code=204, response_class=Response)
def login(payload: LoginRequest, request: Request) -> Response:
    settings = get_settings()
    secure = require_origin(settings, request.headers.getlist("origin"))
    token = service.login(
        payload.username,
        payload.password,
        client_peer(
            settings,
            request.client.host if request.client else None,
            request.headers.getlist("x-forwarded-for"),
        ),
        request.cookies.get(COOKIE_NAME),
        UUID(request.state.request_id),
        settings,
    )
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_SECONDS,
        secure=secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me")
def me(
    request: Request,
    principal: Annotated[service.AuthenticatedSession, Depends(_current_session)],
) -> CurrentUser:
    user = principal.user
    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        institution_id=user.institution_id,
        primary_unit_id=user.primary_unit_id,
        state=user.state,
        must_change_password=principal.must_change_password,
        csrf_token=csrf_token(request.cookies[COOKIE_NAME]),
    )


def _cleared_cookie(secure: bool) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="lax")
    return response


@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request) -> Response:
    secure = require_origin(get_settings(), request.headers.getlist("origin"))
    service.logout(
        request.cookies.get(COOKIE_NAME),
        request.headers.getlist(CSRF_HEADER),
        UUID(request.state.request_id),
    )
    return _cleared_cookie(secure)


@router.post("/change-password", status_code=204, response_class=Response)
def change_password(payload: PasswordChangeRequest, request: Request) -> Response:
    settings = get_settings()
    secure = require_origin(settings, request.headers.getlist("origin"))
    service.change_password(
        request.cookies.get(COOKIE_NAME),
        request.headers.getlist(CSRF_HEADER),
        payload.current_password,
        payload.new_password,
        UUID(request.state.request_id),
        settings,
    )
    return _cleared_cookie(secure)
