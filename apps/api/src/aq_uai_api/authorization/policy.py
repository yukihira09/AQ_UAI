"""Evaluate persisted grants and compose permission-specific database filters."""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.service import AuthenticatedSession, require_unrestricted
from aq_uai_api.db.identity import (
    AccountGroup,
    GroupMembership,
    GroupRoleAssignment,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserCredential,
    UserRoleAssignment,
)


class PermissionCode(StrEnum):
    DIRECTORY_READ = "directory.read"
    PROFILE_UPDATE = "directory.profile.update"
    DIRECTORY_MANAGE = "directory.manage"
    AUTHORIZATION_MANAGE = "authorization.manage"
    AUDIT_READ = "audit.read"
    MDL_READ = "mdl.read"
    MDL_MANAGE = "mdl.manage"
    QTA_READ = "qta.read"
    QTA_MANAGE = "qta.manage"


class GrantScope(StrEnum):
    GLOBAL = "GLOBAL"
    UNIT = "UNIT"


class GrantSubject(StrEnum):
    USER = "USER"
    GROUP = "GROUP"


# Permission membership comes from the catalog. This table only defines which
# subject types and scope shapes can use each approved role.
_ROLE_SCOPES = {
    ("FOUNDATION_ADMIN", GrantSubject.USER): {GrantScope.GLOBAL},
    ("DIRECTORY_READER", GrantSubject.USER): {GrantScope.GLOBAL, GrantScope.UNIT},
    ("DIRECTORY_READER", GrantSubject.GROUP): {GrantScope.GLOBAL, GrantScope.UNIT},
    ("UNIT_DIRECTORY_MANAGER", GrantSubject.USER): {GrantScope.UNIT},
    ("UNIT_DIRECTORY_MANAGER", GrantSubject.GROUP): {GrantScope.UNIT},
    # MDL authority is direct and institution-wide only (D7): no group row is valid.
    ("AI_MODEL_ADMIN", GrantSubject.USER): {GrantScope.GLOBAL},
    # QTA authority (QD1): AI_QUOTA_ADMIN is direct GLOBAL only; AI_QUOTA_VIEWER is direct
    # GLOBAL (Board) or exact-UNIT (Unit Head lookup). Neither may be group-inherited.
    ("AI_QUOTA_ADMIN", GrantSubject.USER): {GrantScope.GLOBAL},
    ("AI_QUOTA_VIEWER", GrantSubject.USER): {GrantScope.GLOBAL, GrantScope.UNIT},
}
_CENTRAL_PERMISSIONS = {
    PermissionCode.DIRECTORY_MANAGE,
    PermissionCode.AUTHORIZATION_MANAGE,
    PermissionCode.AUDIT_READ,
    PermissionCode.MDL_READ,
    PermissionCode.MDL_MANAGE,
    PermissionCode.QTA_MANAGE,
}


@dataclass(frozen=True)
class EffectiveGrant:
    assignment_id: UUID
    role_code: str
    permission: PermissionCode
    institution_id: UUID
    scope: GrantScope
    unit_id: UUID | None
    group_id: UUID | None


@dataclass(frozen=True)
class PermissionScope:
    institution_id: UUID
    institution_wide: bool = False
    unit_ids: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.institution_id, UUID) or any(
            not isinstance(unit_id, UUID) for unit_id in self.unit_ids
        ):
            raise ValueError("Permission scopes require valid institution and unit identifiers.")

    def allows_institution(self, institution_id: UUID) -> bool:
        return self.institution_wide and institution_id == self.institution_id

    def allows_unit(self, institution_id: UUID, unit_id: UUID | None) -> bool:
        return (
            isinstance(unit_id, UUID)
            and institution_id == self.institution_id
            and (self.institution_wide or unit_id in self.unit_ids)
        )

    def predicate(self, institution_column, unit_column=None) -> ColumnElement[bool]:
        """Filter a scope-bearing row, with an omitted unit column denoting central resources."""
        institution_matches = institution_column == self.institution_id
        if self.institution_wide:
            return institution_matches
        if unit_column is None or not self.unit_ids:
            return sa.false()
        return sa.and_(institution_matches, unit_column.in_(self.unit_ids))


@dataclass(frozen=True)
class ActorAuthority:
    actor_id: UUID
    institution_id: UUID
    grants: tuple[EffectiveGrant, ...]

    def scope_for(self, permission: PermissionCode | str) -> PermissionScope:
        try:
            permission = PermissionCode(permission)
        except ValueError:
            return PermissionScope(self.institution_id)
        matches = (
            grant
            for grant in self.grants
            if grant.permission == permission and grant.institution_id == self.institution_id
        )
        units = set()
        for grant in matches:
            if grant.scope is GrantScope.GLOBAL and grant.unit_id is None:
                return PermissionScope(self.institution_id, institution_wide=True)
            if grant.scope is GrantScope.UNIT and isinstance(grant.unit_id, UUID):
                units.add(grant.unit_id)
        return PermissionScope(self.institution_id, unit_ids=frozenset(units))

    def has_permission(self, permission: PermissionCode | str) -> bool:
        scope = self.scope_for(permission)
        return scope.institution_wide or bool(scope.unit_ids)

    def require_permission(self, permission: PermissionCode | str) -> PermissionScope:
        scope = self.scope_for(permission)
        if not scope.institution_wide and not scope.unit_ids:
            raise DomainError(ErrorCode.FORBIDDEN)
        return scope

    def require_institution(self, permission: PermissionCode | str, institution_id: UUID) -> None:
        if not self.scope_for(permission).allows_institution(institution_id):
            raise DomainError(ErrorCode.FORBIDDEN)

    def require_unit(
        self, permission: PermissionCode | str, institution_id: UUID, unit_id: UUID | None
    ) -> None:
        if not self.scope_for(permission).allows_unit(institution_id, unit_id):
            raise DomainError(ErrorCode.FORBIDDEN)


def _valid_shape(role_code: str, subject: GrantSubject, scope: str, unit_id: UUID | None) -> bool:
    return scope in _ROLE_SCOPES.get((role_code, subject), ()) and (
        (scope == GrantScope.GLOBAL and unit_id is None)
        or (scope == GrantScope.UNIT and isinstance(unit_id, UUID))
    )


def _grant_rows(actor_id: UUID):
    direct = sa.select(
        UserRoleAssignment.id.label("assignment_id"),
        UserRoleAssignment.institution_id,
        UserRoleAssignment.role_code,
        UserRoleAssignment.scope,
        UserRoleAssignment.unit_id,
        sa.cast(sa.null(), sa.Uuid()).label("group_id"),
    ).where(UserRoleAssignment.user_id == actor_id)

    inherited = (
        sa.select(
            GroupRoleAssignment.id,
            GroupRoleAssignment.institution_id,
            GroupRoleAssignment.role_code,
            GroupRoleAssignment.scope,
            GroupRoleAssignment.unit_id,
            GroupRoleAssignment.group_id,
        )
        .select_from(GroupRoleAssignment)
        .join(
            AccountGroup,
            sa.and_(
                AccountGroup.id == GroupRoleAssignment.group_id,
                AccountGroup.institution_id == GroupRoleAssignment.institution_id,
            ),
        )
        .join(
            GroupMembership,
            sa.and_(
                GroupMembership.group_id == AccountGroup.id,
                GroupMembership.institution_id == AccountGroup.institution_id,
            ),
        )
        .where(
            GroupMembership.user_id == actor_id,
            GroupMembership.active.is_(True),
            AccountGroup.active.is_(True),
            AccountGroup.kind == "AUTHORIZATION",
        )
    )
    assignments = direct.union_all(inherited).subquery()
    return (
        sa.select(
            assignments, Permission.code.label("permission_code"), Unit.active.label("unit_active")
        )
        .select_from(assignments)
        .join(Role, Role.code == assignments.c.role_code)
        .join(RolePermission, RolePermission.role_code == Role.code)
        .join(Permission, Permission.code == RolePermission.permission_code)
        .outerjoin(
            Unit,
            sa.and_(
                Unit.id == assignments.c.unit_id,
                Unit.institution_id == assignments.c.institution_id,
            ),
        )
        .where(Permission.code.in_(list(PermissionCode)))
        .subquery()
    )


def resolve_effective_grants(db: Session, principal: AuthenticatedSession) -> ActorAuthority:
    """Use an authenticated principal and read current identity and grants in one statement."""
    require_unrestricted(principal)
    actor_id = principal.user.id
    if not isinstance(actor_id, UUID):
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    grants = _grant_rows(actor_id)
    rows = db.execute(
        sa.select(
            User.institution_id.label("actor_institution_id"),
            UserCredential.must_change_password,
            grants,
        )
        .select_from(User)
        .join(UserCredential, UserCredential.user_id == User.id)
        .outerjoin(grants, grants.c.institution_id == User.institution_id)
        .where(User.id == actor_id, User.state == "ACTIVE")
    ).all()
    if not rows:
        raise DomainError(ErrorCode.AUTH_REQUIRED)
    if rows[0].must_change_password:
        raise DomainError(ErrorCode.FORBIDDEN)

    effective = []
    for row in rows:
        if row.assignment_id is None:
            continue
        subject = GrantSubject.GROUP if row.group_id is not None else GrantSubject.USER
        if not _valid_shape(row.role_code, subject, row.scope, row.unit_id):
            continue
        if row.scope == GrantScope.UNIT and row.unit_active is not True:
            continue
        permission = PermissionCode(row.permission_code)
        if permission in _CENTRAL_PERMISSIONS and (
            subject != GrantSubject.USER or row.scope != GrantScope.GLOBAL
        ):
            continue
        effective.append(
            EffectiveGrant(
                row.assignment_id,
                row.role_code,
                permission,
                row.institution_id,
                GrantScope(row.scope),
                row.unit_id,
                row.group_id,
            )
        )
    return ActorAuthority(actor_id, rows[0].actor_institution_id, tuple(effective))


def validate_profile_fields(fields: Collection[str]) -> None:
    """Validate the keys of a profile-only payload before applying it."""
    if set(fields) != {"display_name"}:
        raise DomainError(ErrorCode.VALIDATION_FAILED)


def require_group_management(
    authority: ActorAuthority, institution_id: UUID, group_kind: str
) -> None:
    """Use the group's persisted kind, or the validated kind of a new group."""
    if group_kind == "AUTHORIZATION":
        authority.require_institution(PermissionCode.AUTHORIZATION_MANAGE, institution_id)
    elif group_kind == "SYSTEM":
        authority.require_institution(PermissionCode.DIRECTORY_MANAGE, institution_id)
    elif group_kind == "AI_SPECIALIST":
        if not (
            authority.scope_for(PermissionCode.DIRECTORY_MANAGE).allows_institution(institution_id)
            or authority.scope_for(PermissionCode.QTA_MANAGE).allows_institution(institution_id)
        ):
            raise DomainError(ErrorCode.FORBIDDEN)
    else:
        raise DomainError(ErrorCode.VALIDATION_FAILED)


def validate_role_assignment(
    db: Session,
    authority: ActorAuthority,
    *,
    institution_id: UUID,
    subject: GrantSubject,
    subject_id: UUID,
    role_code: str,
    scope: GrantScope,
    unit_id: UUID | None = None,
) -> None:
    """Validate a proposed grant after the caller acquires the authority-change lock."""
    authority.require_institution(PermissionCode.AUTHORIZATION_MANAGE, institution_id)
    if not isinstance(subject_id, UUID) or not _valid_shape(role_code, subject, scope, unit_id):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    if subject == GrantSubject.USER:
        subject_exists = db.scalar(
            sa.select(User.id).where(
                User.id == subject_id,
                User.institution_id == institution_id,
            )
        )
        if subject_exists is None:
            raise DomainError(ErrorCode.NOT_FOUND)
    else:
        group = db.execute(
            sa.select(AccountGroup.kind, AccountGroup.active).where(
                AccountGroup.id == subject_id,
                AccountGroup.institution_id == institution_id,
            )
        ).one_or_none()
        if group is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if group.kind != "AUTHORIZATION" or not group.active:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
    if unit_id is not None:
        unit = db.scalar(
            sa.select(Unit.active).where(
                Unit.id == unit_id,
                Unit.institution_id == institution_id,
            )
        )
        if unit is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if not unit:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
    if db.scalar(sa.select(Role.id).where(Role.code == role_code)) is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
