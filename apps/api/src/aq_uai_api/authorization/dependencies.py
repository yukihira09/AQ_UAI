"""FastAPI integration for future protected routes."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from aq_uai_api.api.v1.auth import require_unrestricted_session
from aq_uai_api.auth.security import COOKIE_NAME, CSRF_HEADER
from aq_uai_api.auth.service import AuthenticatedSession
from aq_uai_api.auth.write import WriteProof, authenticate_write
from aq_uai_api.authorization.policy import ActorAuthority, resolve_effective_grants
from aq_uai_api.core.config import Settings, get_settings
from aq_uai_api.db.session import get_session


def read_authority(
    principal: Annotated[AuthenticatedSession, Depends(require_unrestricted_session)],
    db: Annotated[Session, Depends(get_session)],
) -> ActorAuthority:
    return resolve_effective_grants(db, principal)


def require_authenticated_write(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WriteProof:
    """Precheck browser proof. The service checks it again under write locks."""
    proof = WriteProof(
        token=request.cookies.get(COOKIE_NAME),
        origins=tuple(request.headers.getlist("origin")),
        csrf_headers=tuple(request.headers.getlist(CSRF_HEADER)),
    )
    authenticate_write(db, proof, settings)
    return proof
