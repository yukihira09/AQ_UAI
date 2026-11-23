"""Transaction-time authentication and authorization for protected writes."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, SessionTransactionOrigin

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.service import database_lock, lock_accounts
from aq_uai_api.auth.write import WriteProof, authenticate_write
from aq_uai_api.authorization.policy import ActorAuthority, PermissionCode, resolve_effective_grants
from aq_uai_api.core.config import Settings
from aq_uai_api.db.identity import User

INSTITUTION_NAMESPACE = 41001
_GUARDED_TRANSACTION = "aq_uai_guarded_write_transaction"


def lock_institution(db: Session, institution_id: UUID, *, exclusive: bool) -> None:
    """Coordinate scope-sensitive writes with authority changes in the same institution."""
    key = int.from_bytes(institution_id.bytes[12:], "big", signed=True)
    database_lock(db, INSTITUTION_NAMESPACE, key, shared=not exclusive)


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
