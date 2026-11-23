"""Protected writes with transaction-time scope checks and typed audit events."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.security import hash_password
from aq_uai_api.auth.service import revoke_user_sessions
from aq_uai_api.auth.write import WriteProof, authenticate_write
from aq_uai_api.authorization.policy import (
    ActorAuthority,
    GrantScope,
    GrantSubject,
    require_group_management,
    resolve_effective_grants,
    validate_profile_fields,
    validate_role_assignment,
)
from aq_uai_api.authorization.policy import (
    PermissionCode as P,
)
from aq_uai_api.authorization.writes import resolve_write_authority
from aq_uai_api.core.config import Settings
from aq_uai_api.db import audit
from aq_uai_api.db.identity import (
    AccountGroup,
    GroupMembership,
    GroupRoleAssignment,
    Unit,
    User,
    UserCredential,
    UserRoleAssignment,
)
from aq_uai_api.db.session import write_transaction
from aq_uai_api.directory import queries, schemas


@dataclass(frozen=True, repr=False)
class WriteContext:
    proof: WriteProof
    settings: Settings
    request_id: UUID


@contextmanager
def protected(
    context: WriteContext,
    *,
    changes_authority: bool,
    user_id: UUID | None = None,
    permission: P | None = None,
    membership_group_id: UUID | None = None,
) -> Iterator[tuple[Session, ActorAuthority]]:
    with write_transaction() as db:
        if membership_group_id is not None:
            # The group's institution and kind are immutable. Read them only
            # to choose the permission for the WP4 account lock hint. The
            # service still checks the actual group and user under the locks.
            current = authenticate_write(db, context.proof, context.settings)
            initial_authority = resolve_effective_grants(db, current)
            kind = db.scalar(
                queries.group_query(initial_authority)
                .with_only_columns(AccountGroup.kind)
                .where(AccountGroup.id == membership_group_id)
            )
            if kind is not None:
                permission = (
                    P.AUTHORIZATION_MANAGE if kind == "AUTHORIZATION" else P.DIRECTORY_MANAGE
                )
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
        if membership_group_id is not None and permission is None:
            # A concurrent create may make this UUID visible after the hint
            # read. This transaction did not coordinate with the target account.
            _require_group_administration(authority)
            raise DomainError(ErrorCode.NOT_FOUND)
        yield db, authority


def record(
    db: Session,
    context: WriteContext,
    authority: ActorAuthority,
    action: audit.AuditAction,
    target_id: UUID,
    changes,
) -> None:
    audit.write_audit_event(
        db,
        action=action,
        request_id=context.request_id,
        institution_id=authority.institution_id,
        actor_id=authority.actor_id,
        target_id=target_id,
        changes=changes,
    )


def _central(authority: ActorAuthority, permission: P = P.DIRECTORY_MANAGE) -> UUID:
    authority.require_institution(permission, authority.institution_id)
    return authority.institution_id


def _user(db: Session, authority: ActorAuthority, user_id: UUID) -> User:
    return queries.one(db, queries.user_query(authority).where(User.id == user_id))


def _require_group_administration(authority: ActorAuthority) -> None:
    if not any(
        authority.scope_for(permission).institution_wide
        for permission in (
            P.DIRECTORY_MANAGE,
            P.AUTHORIZATION_MANAGE,
        )
    ):
        raise DomainError(ErrorCode.FORBIDDEN)


def _group(
    db: Session, authority: ActorAuthority, group_id: UUID, *, lock: bool = False
) -> AccountGroup:
    _require_group_administration(authority)
    query = queries.group_query(authority).where(AccountGroup.id == group_id)
    group = queries.one(db, query)
    require_group_management(authority, group.institution_id, group.kind)
    if lock:
        # Refresh after acquiring the row lock so before/after audit values
        # reflect any earlier shared-scope writer that just committed.
        group = queries.one(db, query.with_for_update().execution_options(populate_existing=True))
    return group


def _initial_credential(
    db: Session, context: WriteContext, user_id: UUID, password: SecretStr
) -> None:
    raw = password.get_secret_value()
    if raw == context.settings.db_password:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    try:
        hashed = hash_password(raw)
    except ValueError:
        raise DomainError(ErrorCode.VALIDATION_FAILED) from None
    db.add(UserCredential(user_id=user_id, password_hash=hashed, must_change_password=True))


def require_remaining_administrator(db: Session, institution_id: UUID) -> None:
    """Evaluate the proposed state under the exclusive institution lock."""
    db.flush()
    usable = db.scalar(
        sa.select(User.id)
        .join(UserCredential, UserCredential.user_id == User.id)
        .join(
            UserRoleAssignment,
            sa.and_(
                UserRoleAssignment.user_id == User.id,
                UserRoleAssignment.institution_id == User.institution_id,
            ),
        )
        .where(
            User.institution_id == institution_id,
            User.state == "ACTIVE",
            UserRoleAssignment.role_code == "FOUNDATION_ADMIN",
            UserRoleAssignment.scope == GrantScope.GLOBAL,
            UserRoleAssignment.unit_id.is_(None),
        )
        .limit(1)
    )
    if usable is None:
        raise DomainError(ErrorCode.CONFLICT)


def create_user(context: WriteContext, payload: schemas.CreateUser) -> schemas.UserOut:
    with protected(context, changes_authority=True) as (db, authority):
        tenant_id = _central(authority)
        queries.tenant_unit(db, tenant_id, payload.primary_unit_id, active=True)
        state = "ACTIVE" if payload.temporary_password is not None else "PENDING"
        user = User(
            institution_id=tenant_id,
            state=state,
            **payload.model_dump(exclude={"temporary_password"}),
        )
        db.add(user)
        db.flush()
        if payload.temporary_password is not None:
            _initial_credential(db, context, user.id, payload.temporary_password)
        record(
            db,
            context,
            authority,
            audit.AuditAction.USER_CREATED,
            user.id,
            audit.UserCreated(primary_unit_id=user.primary_unit_id, state=state),
        )
        return schemas.UserOut.model_validate(user)


def update_profile(
    context: WriteContext, user_id: UUID, payload: schemas.ProfilePatch
) -> schemas.UserOut:
    with protected(
        context, changes_authority=False, user_id=user_id, permission=P.PROFILE_UPDATE
    ) as (db, authority):
        authority.require_permission(P.PROFILE_UPDATE)
        user = _user(db, authority, user_id)
        authority.require_unit(P.PROFILE_UPDATE, user.institution_id, user.primary_unit_id)
        validate_profile_fields(payload.model_fields_set)
        if user.display_name != payload.display_name:
            changes = audit.NameChange(before=user.display_name, after=payload.display_name)
            user.display_name = payload.display_name
            user.updated_at = datetime.now(UTC)
            record(db, context, authority, audit.AuditAction.USER_PROFILE_UPDATED, user.id, changes)
        return schemas.UserOut.model_validate(user)


def _identity(user: User) -> audit.IdentityFields:
    return audit.IdentityFields(
        username=user.username, code_type=user.code_type, institutional_code=user.institutional_code
    )


def update_identity(
    context: WriteContext, user_id: UUID, payload: schemas.IdentityPatch
) -> schemas.UserOut:
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.DIRECTORY_MANAGE
    ) as (db, authority):
        _central(authority)
        user = _user(db, authority, user_id)
        before = _identity(user)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        after = _identity(user)
        if before != after:
            now = datetime.now(UTC)
            user.updated_at = now
            if before.username != after.username:
                revoke_user_sessions(db, user.id, now)
            record(
                db,
                context,
                authority,
                audit.AuditAction.USER_IDENTITY_UPDATED,
                user.id,
                audit.IdentityChange(before=before, after=after),
            )
        return schemas.UserOut.model_validate(user)


def set_user_state(
    context: WriteContext,
    user_id: UUID,
    state: Literal["ACTIVE", "DISABLED"],
    temporary_password: SecretStr | None = None,
) -> schemas.UserOut:
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.DIRECTORY_MANAGE
    ) as (db, authority):
        _central(authority)
        user = _user(db, authority, user_id)
        if user.state == state:
            raise DomainError(ErrorCode.CONFLICT)
        before = user.state
        now = datetime.now(UTC)
        if state == "ACTIVE":
            queries.tenant_unit(db, user.institution_id, user.primary_unit_id, active=True)
            credential_exists = (
                db.scalar(
                    sa.select(UserCredential.user_id).where(
                        UserCredential.user_id == user.id,
                    )
                )
                is not None
            )
            if credential_exists and temporary_password is not None:
                raise DomainError(ErrorCode.CONFLICT)
            if not credential_exists:
                if temporary_password is None:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                _initial_credential(db, context, user.id, temporary_password)
        user.state = state
        user.updated_at = now
        if state == "DISABLED":
            revoke_user_sessions(db, user.id, now)
            require_remaining_administrator(db, authority.institution_id)
        record(
            db,
            context,
            authority,
            audit.AuditAction.USER_STATE_CHANGED,
            user.id,
            audit.UserStateChange(before=before, after=state),
        )
        return schemas.UserOut.model_validate(user)


def transfer(context: WriteContext, user_id: UUID, payload: schemas.Transfer) -> schemas.UserOut:
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.DIRECTORY_MANAGE
    ) as (db, authority):
        _central(authority)
        user = _user(db, authority, user_id)
        origin = queries.tenant_unit(db, user.institution_id, user.primary_unit_id)
        destination = queries.tenant_unit(
            db, user.institution_id, payload.primary_unit_id, active=True
        )
        if origin.id == destination.id:
            raise DomainError(ErrorCode.CONFLICT)
        user.primary_unit_id = destination.id
        user.updated_at = datetime.now(UTC)
        record(
            db,
            context,
            authority,
            audit.AuditAction.USER_TRANSFERRED,
            user.id,
            audit.TransferChange(before=origin.id, after=destination.id),
        )
        return schemas.UserOut.model_validate(user)


def create_unit(context: WriteContext, payload: schemas.CreateUnit) -> schemas.UnitOut:
    with protected(context, changes_authority=True) as (db, authority):
        unit = Unit(institution_id=_central(authority), **payload.model_dump())
        db.add(unit)
        db.flush()
        record(
            db,
            context,
            authority,
            audit.AuditAction.UNIT_CREATED,
            unit.id,
            audit.UnitCreated(code=unit.code, name=unit.name),
        )
        return schemas.UnitOut.model_validate(unit)


def update_unit(
    context: WriteContext, unit_id: UUID, payload: schemas.UnitPatch
) -> schemas.UnitOut:
    with protected(context, changes_authority=False) as (db, authority):
        _central(authority)
        unit = queries.one(
            db, queries.unit_query(authority).where(Unit.id == unit_id).with_for_update()
        )
        before = audit.UnitFields(code=unit.code, name=unit.name)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(unit, field, value)
        after = audit.UnitFields(code=unit.code, name=unit.name)
        if before != after:
            record(
                db,
                context,
                authority,
                audit.AuditAction.UNIT_UPDATED,
                unit.id,
                audit.UnitChange(before=before, after=after),
            )
        return schemas.UnitOut.model_validate(unit)


def set_unit_active(context: WriteContext, unit_id: UUID, active: bool) -> schemas.UnitOut:
    with protected(context, changes_authority=True) as (db, authority):
        tenant_id = _central(authority)
        unit = queries.one(db, queries.unit_query(authority).where(Unit.id == unit_id))
        if unit.active == active:
            raise DomainError(ErrorCode.CONFLICT)
        if not active:
            referenced = db.scalar(
                sa.select(
                    sa.or_(
                        sa.exists().where(
                            User.institution_id == tenant_id,
                            User.primary_unit_id == unit_id,
                            User.state == "ACTIVE",
                        ),
                        sa.exists().where(
                            UserRoleAssignment.institution_id == tenant_id,
                            UserRoleAssignment.unit_id == unit_id,
                        ),
                        sa.exists().where(
                            GroupRoleAssignment.institution_id == tenant_id,
                            GroupRoleAssignment.unit_id == unit_id,
                        ),
                    )
                )
            )
            if referenced:
                raise DomainError(ErrorCode.CONFLICT)
        changes = audit.ActiveChange(before=unit.active, after=active)
        unit.active = active
        record(db, context, authority, audit.AuditAction.UNIT_STATE_CHANGED, unit.id, changes)
        return schemas.UnitOut.model_validate(unit)


def create_group(context: WriteContext, payload: schemas.CreateGroup) -> schemas.GroupOut:
    with protected(context, changes_authority=True) as (db, authority):
        require_group_management(authority, authority.institution_id, payload.kind)
        group = AccountGroup(institution_id=authority.institution_id, **payload.model_dump())
        db.add(group)
        db.flush()
        record(
            db,
            context,
            authority,
            audit.AuditAction.GROUP_CREATED,
            group.id,
            audit.GroupCreated(code=group.code, name=group.name, kind=group.kind),
        )
        return schemas.GroupOut.model_validate(group)


def update_group(
    context: WriteContext, group_id: UUID, payload: schemas.GroupPatch
) -> schemas.GroupOut:
    with protected(context, changes_authority=False) as (db, authority):
        group = _group(db, authority, group_id, lock=True)
        if group.name != payload.name:
            changes = audit.NameChange(before=group.name, after=payload.name)
            group.name = payload.name
            group.updated_at = datetime.now(UTC)
            record(db, context, authority, audit.AuditAction.GROUP_UPDATED, group.id, changes)
        return schemas.GroupOut.model_validate(group)


def set_group_active(context: WriteContext, group_id: UUID, active: bool) -> schemas.GroupOut:
    with protected(context, changes_authority=True) as (db, authority):
        group = _group(db, authority, group_id)
        if group.active == active:
            raise DomainError(ErrorCode.CONFLICT)
        changes = audit.ActiveChange(before=group.active, after=active)
        group.active = active
        group.updated_at = datetime.now(UTC)
        record(db, context, authority, audit.AuditAction.GROUP_STATE_CHANGED, group.id, changes)
        return schemas.GroupOut.model_validate(group)


def set_membership(
    context: WriteContext, group_id: UUID, user_id: UUID, active: bool
) -> schemas.MemberOut | None:
    with protected(
        context, changes_authority=True, user_id=user_id, membership_group_id=group_id
    ) as (db, authority):
        group = _group(db, authority, group_id)
        user = _user(db, authority, user_id)
        if active and not group.active:
            raise DomainError(ErrorCode.CONFLICT)
        row = db.scalar(
            sa.select(GroupMembership).where(
                GroupMembership.institution_id == authority.institution_id,
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
        if row is None and not active:
            return None
        before = row.active if row is not None else None
        if before != active:
            if row is None:
                row = GroupMembership(
                    institution_id=authority.institution_id,
                    group_id=group_id,
                    user_id=user_id,
                    active=active,
                )
                db.add(row)
                db.flush()
            else:
                row.active = active
                row.updated_at = datetime.now(UTC)
            record(
                db,
                context,
                authority,
                audit.AuditAction.MEMBERSHIP_STATE_CHANGED,
                group_id,
                audit.MembershipChange(user_id=user_id, before=before, after=active),
            )
        return queries.member_out(row, user) if active else None


def _grant_audit(row: schemas.AssignmentOut) -> audit.AssignmentChange:
    return audit.AssignmentChange(
        subject_type=row.subject.value,
        subject_id=row.subject_id,
        role_code=row.role_code,
        scope=row.scope.value,
        unit_id=row.unit_id,
    )


def create_assignment(
    context: WriteContext,
    subject: GrantSubject,
    subject_id: UUID,
    payload: schemas.CreateAssignment,
) -> schemas.AssignmentOut:
    user_id = subject_id if subject is GrantSubject.USER else None
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.AUTHORIZATION_MANAGE
    ) as (db, authority):
        validate_role_assignment(
            db,
            authority,
            institution_id=authority.institution_id,
            subject=subject,
            subject_id=subject_id,
            role_code=payload.role_code,
            scope=payload.scope,
            unit_id=payload.unit_id,
        )
        values = {
            "institution_id": authority.institution_id,
            "role_code": payload.role_code,
            "scope": payload.scope.value,
            "unit_id": payload.unit_id,
        }
        if subject is GrantSubject.USER:
            row = UserRoleAssignment(user_id=subject_id, **values)
        else:
            row = GroupRoleAssignment(group_id=subject_id, **values)
        db.add(row)
        db.flush()
        result = queries.assignment_out(row)
        record(
            db,
            context,
            authority,
            audit.AuditAction.ROLE_ASSIGNMENT_CREATED,
            row.id,
            _grant_audit(result),
        )
        return result


def remove_assignment(
    context: WriteContext, subject: GrantSubject, subject_id: UUID, grant_id: UUID
) -> None:
    user_id = subject_id if subject is GrantSubject.USER else None
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.AUTHORIZATION_MANAGE
    ) as (db, authority):
        queries.assignment_target(db, authority, subject, subject_id)
        model, query = queries.assignment_query(authority, subject, subject_id)
        row = queries.one(db, query.where(model.id == grant_id))
        changes = _grant_audit(queries.assignment_out(row))
        db.delete(row)
        if subject is GrantSubject.USER and row.role_code == "FOUNDATION_ADMIN":
            require_remaining_administrator(db, authority.institution_id)
        record(db, context, authority, audit.AuditAction.ROLE_ASSIGNMENT_REMOVED, grant_id, changes)
