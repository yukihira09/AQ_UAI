"""Transaction-time authentication and authorization for protected writes."""

from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, SessionTransactionOrigin

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.service import database_lock, lock_accounts
from aq_uai_api.auth.write import WriteProof, authenticate_write
from aq_uai_api.authorization.policy import ActorAuthority, PermissionCode, resolve_effective_grants
from aq_uai_api.core.config import Settings
from aq_uai_api.db import audit
from aq_uai_api.db.identity import User
from aq_uai_api.db.session import write_transaction

INSTITUTION_NAMESPACE = 41001
_GUARDED_TRANSACTION = "aq_uai_guarded_write_transaction"


def institution_key(institution_id: UUID) -> int:
    """Advisory-lock key for one institution (shared by every institution-scoped lock)."""
    return int.from_bytes(institution_id.bytes[12:], "big", signed=True)


def lock_institution(db: Session, institution_id: UUID, *, exclusive: bool) -> None:
    """Coordinate scope-sensitive writes with authority changes in the same institution."""
    database_lock(db, INSTITUTION_NAMESPACE, institution_key(institution_id), shared=not exclusive)


def resolve_write_authority(
    db: Session,
    proof: WriteProof,
    settings: Settings,
    *,
    changes_authority: bool = False,
    related_account_ids: Collection[UUID] = (),
    related_account_permission: PermissionCode | None = None,
) -> ActorAuthority:
    """Call once in the outer write transaction, before authorization and mutation."""
    transaction = db.get_transaction()
    if (
        transaction is None
        or transaction.origin is not SessionTransactionOrigin.BEGIN
        or db.in_nested_transaction()
    ):
        raise RuntimeError("Protected writes require an explicit outer service transaction.")
    if db.info.get(_GUARDED_TRANSACTION) is transaction:
        raise RuntimeError("Resolve protected write authority once per transaction.")
    if related_account_ids and related_account_permission is None:
        raise ValueError("Related accounts require an operation permission for scoping.")
    db.info[_GUARDED_TRANSACTION] = transaction

    initial = authenticate_write(db, proof, settings)
    actor_id, institution_id = initial.user.id, initial.user.institution_id
    lock_institution(db, institution_id, exclusive=changes_authority)

    account_ids = {actor_id}
    if related_account_ids and related_account_permission is not None:
        # Apply operation scope before waiting on a target's account lock. These
        # results are lock hints only; reauthenticate and authorize under the locks.
        scope = resolve_effective_grants(db, initial).require_permission(related_account_permission)
        account_ids.update(
            db.scalars(
                select(User.id).where(
                    scope.predicate(User.institution_id, User.primary_unit_id),
                    User.id.in_(related_account_ids),
                )
            )
        )
    lock_accounts(db, account_ids)

    current = authenticate_write(db, proof, settings)
    if current.user.id != actor_id or current.user.institution_id != institution_id:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    return resolve_effective_grants(db, current)


@dataclass(frozen=True, repr=False)
class WriteContext:
    """Per-request proof for a protected write. Shared by every module's services."""

    proof: WriteProof
    settings: Settings
    request_id: UUID


@contextmanager
def protected(
    context: WriteContext,
    *,
    changes_authority: bool,
    user_id: UUID | None = None,
    permission: PermissionCode | None = None,
    permission_hint: Callable[[Session], PermissionCode | None] | None = None,
) -> Iterator[tuple[Session, ActorAuthority]]:
    """Open the outer write transaction and resolve transaction-time authority.

    ``permission_hint`` lets a module derive the account-lock scoping permission from
    its own data inside the same transaction. A non-None result replaces ``permission``.
    """
    with write_transaction() as db:
        if permission_hint is not None:
            hinted = permission_hint(db)
            if hinted is not None:
                permission = hinted
        authority = resolve_write_authority(
            db,
            context.proof,
            context.settings,
            changes_authority=changes_authority,
            related_account_ids=(user_id,)
            if user_id is not None and permission is not None
            else (),
            related_account_permission=permission,
        )
        yield db, authority


def record(
    db: Session,
    context: WriteContext,
    authority: ActorAuthority,
    action: audit.AuditAction,
    target_id: UUID,
    changes,
) -> None:
    """Write the typed audit event in the caller's transaction."""
    audit.write_audit_event(
        db,
        action=action,
        request_id=context.request_id,
        institution_id=authority.institution_id,
        actor_id=authority.actor_id,
        target_id=target_id,
        changes=changes,
    )
