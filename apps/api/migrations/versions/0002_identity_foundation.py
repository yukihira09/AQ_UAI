"""Create the shared Phase 2 identity schema and seed its permission catalog.

Revision ID: 0002_identity_foundation
Revises: 0001_phase1_metadata
Create Date: 2026-11-20 13:41:40.109152
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_identity_foundation"
down_revision = "0001_phase1_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_throttle_buckets",
        sa.Column("dimension", sa.String(length=7), nullable=False),
        sa.Column("key_digest", sa.LargeBinary(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("dimension IN ('LOGIN', 'ADDRESS')", name="ck_auth_throttle_dimension"),
        sa.CheckConstraint("failure_count >= 0", name="ck_auth_throttle_failure_count"),
        sa.CheckConstraint("octet_length(key_digest) = 32", name="ck_auth_throttle_digest_length"),
        sa.PrimaryKeyConstraint("dimension", "key_digest", "window_start"),
    )
    op.create_index(
        "ix_auth_throttle_window_start", "auth_throttle_buckets", ["window_start"], unique=False
    )
    op.create_table(
        "institutions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_institutions_code"),
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_table(
        "account_groups",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('SYSTEM', 'AUTHORIZATION', 'AI_SPECIALIST')", name="ck_account_groups_kind"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_account_groups_institution"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("institution_id", "code", name="uq_account_groups_institution_code"),
        sa.UniqueConstraint("institution_id", "id", name="uq_account_groups_institution_id"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("permission_code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"], ["permissions.code"], name="fk_role_permissions_permission"
        ),
        sa.ForeignKeyConstraint(["role_code"], ["roles.code"], name="fk_role_permissions_role"),
        sa.PrimaryKeyConstraint("role_code", "permission_code"),
    )
    op.create_table(
        "units",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_units_institution"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("institution_id", "code", name="uq_units_institution_code"),
        sa.UniqueConstraint("institution_id", "id", name="uq_units_institution_id"),
    )
    op.create_table(
        "group_role_assignments",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=6), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(scope = 'GLOBAL' AND unit_id IS NULL) OR (scope = 'UNIT' AND unit_id IS NOT NULL)",
            name="ck_group_role_assignments_scope",
        ),
        sa.CheckConstraint(
            "role_code <> 'FOUNDATION_ADMIN'", name="ck_group_role_assignments_no_admin"
        ),
        sa.CheckConstraint(
            "role_code <> 'UNIT_DIRECTORY_MANAGER' OR scope = 'UNIT'",
            name="ck_group_role_assignments_manager_unit",
        ),
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
        sa.ForeignKeyConstraint(
            ["role_code"], ["roles.code"], name="fk_group_role_assignments_role"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "group_id",
            "role_code",
            "unit_id",
            name="uq_group_role_assignments_grant",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_group_role_assignments_group", "group_role_assignments", ["group_id"], unique=False
    )
    op.create_index(
        "ix_group_role_assignments_institution_unit",
        "group_role_assignments",
        ["institution_id", "unit_id"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("primary_unit_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("code_type", sa.String(length=7), nullable=False),
        sa.Column("institutional_code", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=8), server_default="PENDING", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code_type IN ('STAFF', 'STUDENT')", name="ck_users_code_type"),
        sa.CheckConstraint(
            "institutional_code <> '' AND institutional_code !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_users_institutional_code",
        ),
        sa.CheckConstraint("state IN ('PENDING', 'ACTIVE', 'DISABLED')", name="ck_users_state"),
        sa.CheckConstraint(
            "username COLLATE \"C\" ~ '^[a-z0-9][a-z0-9._-]{0,63}$'",
            name="ck_users_canonical_username",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "primary_unit_id"],
            ["units.institution_id", "units.id"],
            name="fk_users_primary_unit",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id", "code_type", "institutional_code", name="uq_users_institution_code"
        ),
        sa.UniqueConstraint("institution_id", "id", name="uq_users_institution_id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index(
        "ix_users_institution_primary_unit",
        "users",
        ["institution_id", "primary_unit_id"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=7), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'object'", name="ck_audit_events_changes_object"
        ),
        sa.CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="ck_audit_events_outcome"),
        sa.CheckConstraint(
            "actor_id IS NULL OR institution_id IS NOT NULL",
            name="ck_audit_events_actor_institution",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "actor_id"],
            ["users.institution_id", "users.id"],
            name="fk_audit_events_actor",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_audit_events_institution"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_id"], unique=False)
    op.create_index(
        "ix_audit_events_institution_occurred_at",
        "audit_events",
        ["institution_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"], unique=False)
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "isfinite(issued_at) AND isfinite(expires_at) AND expires_at > issued_at",
            name="ck_auth_sessions_expiry",
        ),
        sa.CheckConstraint(
            "octet_length(token_digest) = 32", name="ck_auth_sessions_digest_length"
        ),
        sa.CheckConstraint(
            "isfinite(revoked_at) AND revoked_at >= issued_at",
            name="ck_auth_sessions_revocation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_auth_sessions_digest"),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
    op.create_index("ix_auth_sessions_user", "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "group_memberships",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )
    op.create_index("ix_group_memberships_user", "group_memberships", ["user_id"], unique=False)
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_credentials_user"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=6), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(scope = 'GLOBAL' AND unit_id IS NULL) OR (scope = 'UNIT' AND unit_id IS NOT NULL)",
            name="ck_user_role_assignments_scope",
        ),
        sa.CheckConstraint(
            "role_code <> 'FOUNDATION_ADMIN' OR scope = 'GLOBAL'",
            name="ck_user_role_assignments_admin_global",
        ),
        sa.CheckConstraint(
            "role_code <> 'UNIT_DIRECTORY_MANAGER' OR scope = 'UNIT'",
            name="ck_user_role_assignments_manager_unit",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "unit_id"],
            ["units.institution_id", "units.id"],
            name="fk_user_role_assignments_unit",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["users.institution_id", "users.id"],
            name="fk_user_role_assignments_user",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"], ["roles.code"], name="fk_user_role_assignments_role"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "user_id",
            "role_code",
            "unit_id",
            name="uq_user_role_assignments_grant",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_user_role_assignments_institution_unit",
        "user_role_assignments",
        ["institution_id", "unit_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_role_assignments_user", "user_role_assignments", ["user_id"], unique=False
    )

    # Keep historical seed values in this revision. Future catalog changes get new revisions.
    role_permissions = {
        "FOUNDATION_ADMIN": (
            "directory.read",
            "directory.profile.update",
            "directory.manage",
            "authorization.manage",
            "audit.read",
        ),
        "DIRECTORY_READER": ("directory.read",),
        "UNIT_DIRECTORY_MANAGER": ("directory.read", "directory.profile.update"),
    }
    code_column = sa.String(64)
    op.bulk_insert(
        sa.table("roles", sa.column("code", code_column)),
        [{"code": code} for code in role_permissions],
    )
    op.bulk_insert(
        sa.table("permissions", sa.column("code", code_column)),
        [{"code": code} for code in sorted(set().union(*role_permissions.values()))],
    )
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_code", code_column),
            sa.column("permission_code", code_column),
        ),
        [
            {"role_code": role, "permission_code": permission}
            for role, permissions in role_permissions.items()
            for permission in permissions
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading WP1 could discard identity and audit history. "
        "Restore a verified pre-WP1 backup to a separate database instead."
    )
