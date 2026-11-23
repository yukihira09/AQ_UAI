"""Origin and CSRF guard for normal authenticated mutations."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from aq_uai_api.auth.security import require_origin, validate_csrf
from aq_uai_api.auth.service import (
    AuthenticatedSession,
    authenticate_session,
    require_unrestricted,
)
from aq_uai_api.core.config import Settings


@dataclass(frozen=True, repr=False)
class WriteProof:
    """Request-bound evidence to check again in the service's write transaction."""

    token: str | None
    origins: tuple[str, ...]
    csrf_headers: tuple[str, ...]


def authenticate_write(db: Session, proof: WriteProof, settings: Settings) -> AuthenticatedSession:
    require_origin(settings, list(proof.origins))
    principal = require_unrestricted(authenticate_session(db, proof.token))
    validate_csrf(proof.token, list(proof.csrf_headers))
    return principal
