"""Database-backed authentication using the shared service transaction boundary."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.security import (
    SESSION_SECONDS,
    hash_password,
    new_session_token,
    normalize_username,
    throttle_digest,
    token_digest,
    validate_csrf,
    verify_password,
)
from aq_uai_api.core.config import Settings
from aq_uai_api.db.audit import AuditAction, RevocationCount, write_audit_event
from aq_uai_api.db.identity import AuthSession, AuthThrottleBucket, User, UserCredential
from aq_uai_api.db.session import write_transaction

THROTTLE_NAMESPACE = 31001
ACCOUNT_NAMESPACE = 31002
BOOTSTRAP_NAMESPACE = 31003
WINDOW_MINUTES = 15


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session_id: UUID
    must_change_password: bool


def _key32(value: bytes) -> int:
    return int.from_bytes(value[:4], "big", signed=True)


def database_lock(db: Session, namespace: int, key: int) -> None:
    db.execute(select(func.pg_advisory_xact_lock(namespace, key)))


def lock_account(db: Session, user_id: UUID) -> None:
    """WP5 must take this same lock before disabling an account and revoking its sessions."""
    # Hash collisions only serialize two accounts; the database lookup still uses the full UUID.
    database_lock(db, ACCOUNT_NAMESPACE, _key32(user_id.bytes[12:]))


def revoke_user_sessions(
    db: Session,
    user_id: UUID,
    now: datetime,
    session_id: UUID | None = None,
    digest: bytes | None = None,
) -> int:
    statement = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if session_id is not None:
        statement = statement.where(AuthSession.id == session_id)
    if digest is not None:
        statement = statement.where(AuthSession.token_digest == digest)
    result = db.execute(statement.values(revoked_at=func.greatest(AuthSession.issued_at, now)))
    return result.rowcount


def _address_key(peer: str | None) -> str:
    try:
        if peer is None:
            return "unknown"
        address = ip_address(peer)
        return str(getattr(address, "ipv4_mapped", None) or address)
    except ValueError:
        return "unknown"


def _failure_count(db: Session, dimension: str, digest: bytes, window: datetime) -> int:
    return (
        db.scalar(
            select(AuthThrottleBucket.failure_count).where(
                AuthThrottleBucket.dimension == dimension,
                AuthThrottleBucket.key_digest == digest,
                AuthThrottleBucket.window_start == window,
            )
        )
        or 0
    )


def _record_failure(db: Session, dimension: str, digest: bytes, window: datetime) -> None:
    db.execute(
        insert(AuthThrottleBucket)
        .values(
            dimension=dimension,
            key_digest=digest,
            window_start=window,
            failure_count=1,
        )
        .on_conflict_do_update(
            index_elements=[
                AuthThrottleBucket.dimension,
                AuthThrottleBucket.key_digest,
                AuthThrottleBucket.window_start,
            ],
            set_={"failure_count": AuthThrottleBucket.failure_count + 1},
        )
    )


def cleanup_throttle(db: Session, now: datetime) -> int:
    """Delete at most 100 buckets older than one day, avoiding concurrent writers."""
    table = AuthThrottleBucket.__table__
    keys = (table.c.dimension, table.c.key_digest, table.c.window_start)
    old = (
        select(*keys)
        .where(table.c.window_start < now - timedelta(days=1))
        .order_by(table.c.window_start)
        .limit(100)
        .with_for_update(skip_locked=True)
        .cte("old")
    )
    result = db.execute(
        delete(table).where(
            table.c.dimension == old.c.dimension,
            table.c.key_digest == old.c.key_digest,
            table.c.window_start == old.c.window_start,
        )
    )
    return result.rowcount


def _session_query(digest: bytes, now: datetime):
    return (
        select(User, AuthSession.id, UserCredential.must_change_password)
        .join(AuthSession, AuthSession.user_id == User.id)
        .join(UserCredential, UserCredential.user_id == User.id)
        .where(
            AuthSession.token_digest == digest,
            AuthSession.revoked_at.is_(None),
            AuthSession.issued_at <= now,
            AuthSession.expires_at > now,
            User.state == "ACTIVE",
        )
    )


def authenticate_session(db: Session, token: str | None) -> AuthenticatedSession:
    digest = token_digest(token)
    if digest is None:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    row = db.execute(_session_query(digest, datetime.now(UTC))).one_or_none()
    if row is None:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    return AuthenticatedSession(*row)


def login(
    username: str,
    password: str,
    peer: str | None,
    previous_token: str | None,
    request_id: UUID,
    settings: Settings,
) -> str:
    canonical = normalize_username(username)
    buckets = (
        ("LOGIN", throttle_digest(settings, "LOGIN", canonical or "<invalid>"), 5),
        ("ADDRESS", throttle_digest(settings, "ADDRESS", _address_key(peer)), 30),
    )
    token = None
    error = ErrorCode.AUTH_REQUIRED
    with write_transaction() as db:
        for key in sorted({_key32(digest) for _, digest, _ in buckets}):
            database_lock(db, THROTTLE_NAMESPACE, key)
        now = datetime.now(UTC)
        window = now.replace(
            minute=now.minute // WINDOW_MINUTES * WINDOW_MINUTES, second=0, microsecond=0
        )
        if any(
            _failure_count(db, dimension, digest, window) >= limit
            for dimension, digest, limit in buckets
        ):
            error = ErrorCode.RATE_LIMITED
        else:
            user_id = (
                db.scalar(select(User.id).where(User.username == canonical)) if canonical else None
            )
            user, credential = None, None
            if user_id is not None:
                lock_account(db, user_id)
                user = db.get(User, user_id)
                credential = db.get(UserCredential, user_id)
            verified = verify_password(credential.password_hash if credential else None, password)
            if (
                user is not None
                and user.username == canonical
                and user.state == "ACTIVE"
                and verified
            ):
                issued_at = datetime.now(UTC)
                previous_digest = token_digest(previous_token)
                if previous_digest is not None:
                    revoke_user_sessions(db, user.id, issued_at, digest=previous_digest)
                token = new_session_token()
                db.execute(
                    insert(AuthSession).values(
                        user_id=user.id,
                        token_digest=token_digest(token),
                        issued_at=issued_at,
                        expires_at=issued_at + timedelta(seconds=SESSION_SECONDS),
                    )
                )
                write_audit_event(
                    db,
                    action=AuditAction.AUTH_LOGIN_SUCCEEDED,
                    request_id=request_id,
                    institution_id=user.institution_id,
                    actor_id=user.id,
                    target_id=user.id,
                )
            else:
                for dimension, digest, _ in buckets:
                    _record_failure(db, dimension, digest, window)
        if token is None:
            write_audit_event(db, action=AuditAction.AUTH_LOGIN_REJECTED, request_id=request_id)
        cleanup_throttle(db, now)

    # A rejection commits its audit and counters before the response is built.
    if token is None:
        raise DomainError(error)
    return token


def _locked_session(db: Session, token: str | None, csrf: list[str]) -> AuthenticatedSession:
    digest = token_digest(token)
    if digest is None:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    user_id = db.scalar(select(AuthSession.user_id).where(AuthSession.token_digest == digest))
    if user_id is None:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    lock_account(db, user_id)
    principal = authenticate_session(db, token)
    validate_csrf(token, csrf)
    return principal


def logout(token: str | None, csrf: list[str], request_id: UUID) -> None:
    with write_transaction() as db:
        principal = _locked_session(db, token, csrf)
        user = principal.user
        revoke_user_sessions(db, user.id, datetime.now(UTC), session_id=principal.session_id)
        write_audit_event(
            db,
            action=AuditAction.AUTH_LOGOUT,
            request_id=request_id,
            institution_id=user.institution_id,
            actor_id=user.id,
            target_id=user.id,
        )


def change_password(
    token: str | None,
    csrf: list[str],
    current_password: str,
    new_password: str,
    request_id: UUID,
    settings: Settings,
) -> None:
    with write_transaction() as db:
        principal = _locked_session(db, token, csrf)
        user = principal.user
        credential = db.get(UserCredential, user.id)
        if credential is None or not verify_password(credential.password_hash, current_password):
            raise DomainError(ErrorCode.AUTH_REQUIRED)
        if new_password in {current_password, settings.db_password}:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        now = datetime.now(UTC)
        credential.password_hash = hash_password(new_password)
        credential.must_change_password = False
        credential.updated_at = now
        count = revoke_user_sessions(db, user.id, now)
        write_audit_event(
            db,
            action=AuditAction.AUTH_PASSWORD_CHANGED,
            request_id=request_id,
            institution_id=user.institution_id,
            actor_id=user.id,
            target_id=user.id,
            changes=RevocationCount(revoked_sessions=count),
        )
