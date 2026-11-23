"""SQL-level visibility, filtering, and explicit response projections."""

from collections.abc import Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.policy import ActorAuthority, GrantSubject
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.db.audit import public_audit_changes
from aq_uai_api.db.identity import (
    AccountGroup,
    AuditEvent,
    GroupMembership,
    GroupRoleAssignment,
    Role,
    RolePermission,
    Unit,
    User,
    UserRoleAssignment,
)
from aq_uai_api.directory import schemas


def one[T](db: Session, statement: sa.Select[tuple[T]]) -> T:
    result = db.scalar(statement)
    if result is None:
        raise DomainError(ErrorCode.NOT_FOUND)
    return result


def page[T](
    db: Session, statement, params: schemas.PageParams, project: Callable[..., T]
) -> schemas.Page[T]:
    total = db.scalar(sa.select(sa.func.count()).select_from(statement.order_by(None).subquery()))
    rows = db.execute(statement.offset(params.offset).limit(params.limit))
    return schemas.Page(
        items=[project(*row) for row in rows], total=total, limit=params.limit, offset=params.offset
    )


def user_query(authority: ActorAuthority):
    scope = authority.scope_for(P.DIRECTORY_READ)
    return sa.select(User).where(scope.predicate(User.institution_id, User.primary_unit_id))


def unit_query(authority: ActorAuthority):
    scope = authority.scope_for(P.DIRECTORY_READ)
    return sa.select(Unit).where(scope.predicate(Unit.institution_id, Unit.id))


def group_query(authority: ActorAuthority):
    scope = authority.scope_for(P.DIRECTORY_READ)
    return sa.select(AccountGroup).where(scope.predicate(AccountGroup.institution_id))


def tenant_unit(db: Session, institution_id: UUID, unit_id: UUID, *, active: bool = False) -> Unit:
    unit = one(db, sa.select(Unit).where(Unit.institution_id == institution_id, Unit.id == unit_id))
    if active and not unit.active:
        raise DomainError(ErrorCode.CONFLICT)
    return unit


def users(
    db: Session, authority: ActorAuthority, params: schemas.UserFilters
) -> schemas.Page[schemas.UserOut]:
    authority.require_permission(P.DIRECTORY_READ)
    query = user_query(authority)
    if params.q:
        query = query.where(
            sa.or_(
                User.display_name.icontains(params.q, autoescape=True),
                User.username.icontains(params.q, autoescape=True),
                User.institutional_code.icontains(params.q, autoescape=True),
            )
        )
    for column, value in (
        (User.primary_unit_id, params.primary_unit_id),
        (User.state, params.state),
        (User.code_type, params.code_type),
    ):
        if value is not None:
            query = query.where(column == value)
    return page(db, query.order_by(User.username, User.id), params, schemas.UserOut.model_validate)


def units(
    db: Session, authority: ActorAuthority, params: schemas.UnitFilters
) -> schemas.Page[schemas.UnitOut]:
    authority.require_permission(P.DIRECTORY_READ)
    query = unit_query(authority)
    if params.q:
        query = query.where(
            sa.or_(
                Unit.code.icontains(params.q, autoescape=True),
                Unit.name.icontains(params.q, autoescape=True),
            )
        )
    if params.active is not None:
        query = query.where(Unit.active == params.active)
    return page(db, query.order_by(Unit.code, Unit.id), params, schemas.UnitOut.model_validate)


def groups(
    db: Session, authority: ActorAuthority, params: schemas.GroupFilters
) -> schemas.Page[schemas.GroupOut]:
    authority.require_institution(P.DIRECTORY_READ, authority.institution_id)
    query = group_query(authority)
    if params.q:
        query = query.where(
            sa.or_(
                AccountGroup.code.icontains(params.q, autoescape=True),
                AccountGroup.name.icontains(params.q, autoescape=True),
            )
        )
    if params.active is not None:
        query = query.where(AccountGroup.active == params.active)
    if params.kind is not None:
        query = query.where(AccountGroup.kind == params.kind)
    return page(
        db,
        query.order_by(AccountGroup.code, AccountGroup.id),
        params,
        schemas.GroupOut.model_validate,
    )


def membership_query(institution_id: UUID):
    """One row per current stored user–group pair. Callers choose lifecycle predicates."""
    return (
        sa.select(GroupMembership, User)
        .join(
            User,
            sa.and_(
                User.id == GroupMembership.user_id,
                User.institution_id == GroupMembership.institution_id,
            ),
        )
        .join(
            AccountGroup,
            sa.and_(
                AccountGroup.id == GroupMembership.group_id,
                AccountGroup.institution_id == GroupMembership.institution_id,
            ),
        )
        .where(GroupMembership.institution_id == institution_id)
    )


def member_out(row: GroupMembership, user: User) -> schemas.MemberOut:
    return schemas.MemberOut(
        group_id=row.group_id,
        user=schemas.UserOut.model_validate(user),
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def members(
    db: Session, authority: ActorAuthority, group_id: UUID, params: schemas.MemberFilters
) -> schemas.Page[schemas.MemberOut]:
    authority.require_institution(P.DIRECTORY_READ, authority.institution_id)
    one(db, group_query(authority).where(AccountGroup.id == group_id))
    query = membership_query(authority.institution_id).where(GroupMembership.group_id == group_id)
    if params.active is not None:
        query = query.where(GroupMembership.active == params.active)
    if params.q:
        query = query.where(
            sa.or_(
                User.display_name.icontains(params.q, autoescape=True),
                User.username.icontains(params.q, autoescape=True),
                User.institutional_code.icontains(params.q, autoescape=True),
            )
        )
    return page(db, query.order_by(User.username, User.id), params, member_out)


def assignment_target(
    db: Session, authority: ActorAuthority, subject: GrantSubject, subject_id: UUID
):
    authority.require_institution(P.AUTHORIZATION_MANAGE, authority.institution_id)
    model = User if subject is GrantSubject.USER else AccountGroup
    return one(
        db,
        sa.select(model).where(
            model.id == subject_id,
            authority.scope_for(P.AUTHORIZATION_MANAGE).predicate(model.institution_id),
        ),
    )


def assignment_query(authority: ActorAuthority, subject: GrantSubject, subject_id: UUID):
    if subject is GrantSubject.USER:
        model, column = UserRoleAssignment, UserRoleAssignment.user_id
    else:
        model, column = GroupRoleAssignment, GroupRoleAssignment.group_id
    query = sa.select(model).where(
        column == subject_id,
        authority.scope_for(P.AUTHORIZATION_MANAGE).predicate(model.institution_id),
    )
    return model, query


def assignment_out(row: UserRoleAssignment | GroupRoleAssignment) -> schemas.AssignmentOut:
    user_grant = isinstance(row, UserRoleAssignment)
    return schemas.AssignmentOut(
        id=row.id,
        institution_id=row.institution_id,
        role_code=row.role_code,
        scope=row.scope,
        unit_id=row.unit_id,
        subject=GrantSubject.USER if user_grant else GrantSubject.GROUP,
        subject_id=row.user_id if user_grant else row.group_id,
    )


def assignments(
    db: Session,
    authority: ActorAuthority,
    subject: GrantSubject,
    subject_id: UUID,
    params: schemas.AssignmentFilters,
) -> schemas.Page[schemas.AssignmentOut]:
    assignment_target(db, authority, subject, subject_id)
    model, query = assignment_query(authority, subject, subject_id)
    for column, value in (
        (model.role_code, params.role_code),
        (model.scope, params.scope),
        (model.unit_id, params.unit_id),
    ):
        if value is not None:
            query = query.where(column == value)
    return page(db, query.order_by(model.role_code, model.id), params, assignment_out)


def roles(
    db: Session, authority: ActorAuthority, params: schemas.SearchParams
) -> schemas.Page[schemas.RoleOut]:
    authority.require_institution(P.AUTHORIZATION_MANAGE, authority.institution_id)
    query = sa.select(Role.code)
    if params.q:
        query = query.where(Role.code.icontains(params.q, autoescape=True))
    result = page(
        db,
        query.order_by(Role.code),
        params,
        lambda code: schemas.RoleOut(code=code, permissions=[]),
    )
    by_code = {item.code: item for item in result.items}
    if by_code:
        for code, permission in db.execute(
            sa.select(RolePermission.role_code, RolePermission.permission_code)
            .where(RolePermission.role_code.in_(by_code))
            .order_by(RolePermission.permission_code)
        ):
            by_code[code].permissions.append(permission)
    return result


def audit_query(authority: ActorAuthority):
    authority.require_institution(P.AUDIT_READ, authority.institution_id)
    return sa.select(AuditEvent).where(
        authority.scope_for(P.AUDIT_READ).predicate(AuditEvent.institution_id)
    )


def audit_out(row: AuditEvent) -> schemas.AuditOut:
    return schemas.AuditOut(
        id=row.id,
        institution_id=row.institution_id,
        actor_id=row.actor_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        outcome=row.outcome,
        occurred_at=row.occurred_at,
        request_id=row.request_id,
        changes=public_audit_changes(row),
    )


def audit_events(
    db: Session, authority: ActorAuthority, params: schemas.AuditFilters
) -> schemas.Page[schemas.AuditOut]:
    query = audit_query(authority)
    for column, value in (
        (AuditEvent.action, params.action),
        (AuditEvent.actor_id, params.actor_id),
        (AuditEvent.target_type, params.target_type),
        (AuditEvent.target_id, params.target_id),
        (AuditEvent.outcome, params.outcome),
    ):
        if value is not None:
            query = query.where(column == value)
    if params.from_time is not None:
        query = query.where(AuditEvent.occurred_at >= params.from_time)
    if params.to_time is not None:
        query = query.where(AuditEvent.occurred_at < params.to_time)
    return page(
        db, query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()), params, audit_out
    )


def capabilities(authority: ActorAuthority) -> schemas.Capabilities:
    scopes = {permission: authority.scope_for(permission) for permission in P}
    return schemas.Capabilities(
        institution_id=authority.institution_id,
        permissions={
            permission: schemas.CapabilityScope(
                institution_wide=scope.institution_wide, unit_ids=sorted(scope.unit_ids)
            )
            for permission, scope in scopes.items()
        },
    )
