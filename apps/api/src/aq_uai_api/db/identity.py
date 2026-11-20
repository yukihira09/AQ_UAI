"""Phase 2 identity, authorization, session, and audit persistence."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aq_uai_api.db.base import Base


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=sa.text("gen_random_uuid()"))


class ChangeTimestamps:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Institution(UUIDPrimaryKey, Base):
    __tablename__ = "institutions"
    __table_args__ = (sa.UniqueConstraint("code", name="uq_institutions_code"),)

    code: Mapped[str] = mapped_column(sa.String(64))
    name: Mapped[str] = mapped_column(sa.String(255))


class Unit(UUIDPrimaryKey, Base):
    __tablename__ = "units"
    __table_args__ = (
        sa.UniqueConstraint("institution_id", "id", name="uq_units_institution_id"),
        sa.UniqueConstraint("institution_id", "code", name="uq_units_institution_code"),
    )

    institution_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("institutions.id", name="fk_units_institution")
    )
    code: Mapped[str] = mapped_column(sa.String(64))
    name: Mapped[str] = mapped_column(sa.String(255))
    active: Mapped[bool] = mapped_column(server_default=sa.true())


class User(UUIDPrimaryKey, ChangeTimestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "primary_unit_id"],
            ["units.institution_id", "units.id"],
            name="fk_users_primary_unit",
        ),
        sa.UniqueConstraint("institution_id", "id", name="uq_users_institution_id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint(
            "institution_id", "code_type", "institutional_code", name="uq_users_institution_code"
        ),
        sa.CheckConstraint(
            """username COLLATE "C" ~ '^[a-z0-9][a-z0-9._-]{0,63}$'""",
            name="ck_users_canonical_username",
        ),
        sa.CheckConstraint("code_type IN ('STAFF', 'STUDENT')", name="ck_users_code_type"),
        sa.CheckConstraint(
            "institutional_code <> '' AND institutional_code !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_users_institutional_code",
        ),
        sa.CheckConstraint("state IN ('PENDING', 'ACTIVE', 'DISABLED')", name="ck_users_state"),
        sa.Index("ix_users_institution_primary_unit", "institution_id", "primary_unit_id"),
    )

    institution_id: Mapped[UUID]
    primary_unit_id: Mapped[UUID]
    username: Mapped[str] = mapped_column(sa.String(64))
    display_name: Mapped[str] = mapped_column(sa.String(255))
    code_type: Mapped[str] = mapped_column(sa.String(7))
    institutional_code: Mapped[str] = mapped_column(sa.String(64))
    state: Mapped[str] = mapped_column(sa.String(8), server_default="PENDING")


class UserCredential(ChangeTimestamps, Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("users.id", name="fk_user_credentials_user"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(sa.Text)
    must_change_password: Mapped[bool] = mapped_column(server_default=sa.true())


class AccountGroup(UUIDPrimaryKey, ChangeTimestamps, Base):
    __tablename__ = "account_groups"
    __table_args__ = (
        sa.UniqueConstraint("institution_id", "id", name="uq_account_groups_institution_id"),
        sa.UniqueConstraint("institution_id", "code", name="uq_account_groups_institution_code"),
        sa.CheckConstraint(
            "kind IN ('SYSTEM', 'AUTHORIZATION', 'AI_SPECIALIST')", name="ck_account_groups_kind"
        ),
    )

    institution_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("institutions.id", name="fk_account_groups_institution")
    )
    code: Mapped[str] = mapped_column(sa.String(64))
    name: Mapped[str] = mapped_column(sa.String(255))
    kind: Mapped[str] = mapped_column(sa.String(16))
    active: Mapped[bool] = mapped_column(server_default=sa.true())


class GroupMembership(ChangeTimestamps, Base):
    __tablename__ = "group_memberships"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "group_id"],
            ["account_groups.institution_id", "account_groups.id"],
            name="fk_group_memberships_group",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["users.institution_id", "users.id"],
            name="fk_group_memberships_user",
        ),
        sa.Index("ix_group_memberships_user", "user_id"),
    )

    group_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    institution_id: Mapped[UUID]
    active: Mapped[bool] = mapped_column(server_default=sa.true())


class Role(UUIDPrimaryKey, Base):
    __tablename__ = "roles"
    __table_args__ = (sa.UniqueConstraint("code", name="uq_roles_code"),)

    code: Mapped[str] = mapped_column(sa.String(64))


class Permission(UUIDPrimaryKey, Base):
    __tablename__ = "permissions"
    __table_args__ = (sa.UniqueConstraint("code", name="uq_permissions_code"),)

    code: Mapped[str] = mapped_column(sa.String(64))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("roles.code", name="fk_role_permissions_role"),
        primary_key=True,
    )
    permission_code: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("permissions.code", name="fk_role_permissions_permission"),
        primary_key=True,
    )


SCOPE_REQUIRES_UNIT = (
    "(scope = 'GLOBAL' AND unit_id IS NULL) OR (scope = 'UNIT' AND unit_id IS NOT NULL)"
)


class UserRoleAssignment(UUIDPrimaryKey, Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["users.institution_id", "users.id"],
            name="fk_user_role_assignments_user",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "unit_id"],
            ["units.institution_id", "units.id"],
            name="fk_user_role_assignments_unit",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "user_id",
            "role_code",
            "unit_id",
            name="uq_user_role_assignments_grant",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(SCOPE_REQUIRES_UNIT, name="ck_user_role_assignments_scope"),
        sa.CheckConstraint(
            "role_code <> 'FOUNDATION_ADMIN' OR scope = 'GLOBAL'",
            name="ck_user_role_assignments_admin_global",
        ),
        sa.CheckConstraint(
            "role_code <> 'UNIT_DIRECTORY_MANAGER' OR scope = 'UNIT'",
            name="ck_user_role_assignments_manager_unit",
        ),
        sa.Index("ix_user_role_assignments_user", "user_id"),
        sa.Index("ix_user_role_assignments_institution_unit", "institution_id", "unit_id"),
    )

    institution_id: Mapped[UUID]
    user_id: Mapped[UUID]
    role_code: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("roles.code", name="fk_user_role_assignments_role")
    )
    scope: Mapped[str] = mapped_column(sa.String(6))
    unit_id: Mapped[UUID | None]


class GroupRoleAssignment(UUIDPrimaryKey, Base):
    __tablename__ = "group_role_assignments"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "group_id"],
            ["account_groups.institution_id", "account_groups.id"],
            name="fk_group_role_assignments_group",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "unit_id"],
            ["units.institution_id", "units.id"],
            name="fk_group_role_assignments_unit",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "group_id",
            "role_code",
            "unit_id",
            name="uq_group_role_assignments_grant",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(SCOPE_REQUIRES_UNIT, name="ck_group_role_assignments_scope"),
        sa.CheckConstraint(
            "role_code <> 'FOUNDATION_ADMIN'", name="ck_group_role_assignments_no_admin"
        ),
        sa.CheckConstraint(
            "role_code <> 'UNIT_DIRECTORY_MANAGER' OR scope = 'UNIT'",
            name="ck_group_role_assignments_manager_unit",
        ),
        sa.Index("ix_group_role_assignments_group", "group_id"),
        sa.Index("ix_group_role_assignments_institution_unit", "institution_id", "unit_id"),
    )

    institution_id: Mapped[UUID]
    group_id: Mapped[UUID]
    role_code: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("roles.code", name="fk_group_role_assignments_role")
    )
    scope: Mapped[str] = mapped_column(sa.String(6))
    unit_id: Mapped[UUID | None]


class AuthSession(UUIDPrimaryKey, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        sa.UniqueConstraint("token_digest", name="uq_auth_sessions_digest"),
        sa.CheckConstraint(
            "octet_length(token_digest) = 32", name="ck_auth_sessions_digest_length"
        ),
        sa.CheckConstraint(
            "isfinite(issued_at) AND isfinite(expires_at) AND expires_at > issued_at",
            name="ck_auth_sessions_expiry",
        ),
        sa.CheckConstraint(
            "isfinite(revoked_at) AND revoked_at >= issued_at",
            name="ck_auth_sessions_revocation",
        ),
        sa.Index("ix_auth_sessions_user", "user_id"),
        sa.Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id", name="fk_auth_sessions_user"))
    token_digest: Mapped[bytes]
    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuthThrottleBucket(Base):
    __tablename__ = "auth_throttle_buckets"
    __table_args__ = (
        sa.CheckConstraint("dimension IN ('LOGIN', 'ADDRESS')", name="ck_auth_throttle_dimension"),
        sa.CheckConstraint("octet_length(key_digest) = 32", name="ck_auth_throttle_digest_length"),
        sa.CheckConstraint("failure_count >= 0", name="ck_auth_throttle_failure_count"),
        sa.Index("ix_auth_throttle_window_start", "window_start"),
    )

    dimension: Mapped[str] = mapped_column(sa.String(7), primary_key=True)
    key_digest: Mapped[bytes] = mapped_column(primary_key=True)
    window_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), primary_key=True)
    failure_count: Mapped[int] = mapped_column(server_default=sa.text("0"))


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "actor_id"],
            ["users.institution_id", "users.id"],
            name="fk_audit_events_actor",
        ),
        sa.CheckConstraint(
            "actor_id IS NULL OR institution_id IS NOT NULL",
            name="ck_audit_events_actor_institution",
        ),
        sa.CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="ck_audit_events_outcome"),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'object'", name="ck_audit_events_changes_object"
        ),
        sa.Index("ix_audit_events_actor", "actor_id"),
        sa.Index("ix_audit_events_institution_occurred_at", "institution_id", "occurred_at"),
        sa.Index("ix_audit_events_request_id", "request_id"),
    )

    institution_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("institutions.id", name="fk_audit_events_institution")
    )
    actor_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(sa.String(96))
    target_type: Mapped[str] = mapped_column(sa.String(64))
    target_id: Mapped[UUID | None]
    outcome: Mapped[str] = mapped_column(sa.String(7))
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    request_id: Mapped[str] = mapped_column(sa.String(64))
    changes: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
