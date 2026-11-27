"""Add the QTA permission catalog and direct-user role constraints (Phase 4, Q1).

Revision ID: 0007_qta_access_catalog
Revises: 0006_mdl_routing_and_styles
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_qta_access_catalog"
down_revision = "0006_mdl_routing_and_styles"
branch_labels = None
depends_on = None

ROLES = ("AI_QUOTA_ADMIN", "AI_QUOTA_VIEWER")
PERMISSIONS = ("qta.read", "qta.manage")
ROLE_PERMISSIONS = (
    ("AI_QUOTA_ADMIN", "qta.read"),
    ("AI_QUOTA_ADMIN", "qta.manage"),
    ("AI_QUOTA_VIEWER", "qta.read"),
)


def upgrade() -> None:
    # QTA administration is direct GLOBAL only; QTA viewing is direct GLOBAL or UNIT.
    # Neither role may be inherited via an authorization group. Existing roles stay unchanged.
    op.create_check_constraint(
        "ck_user_role_assignments_qta_admin_global",
        "user_role_assignments",
        "role_code <> 'AI_QUOTA_ADMIN' OR scope = 'GLOBAL'",
    )
    op.create_check_constraint(
        "ck_group_role_assignments_no_qta_admin",
        "group_role_assignments",
        "role_code <> 'AI_QUOTA_ADMIN'",
    )
    op.create_check_constraint(
        "ck_group_role_assignments_no_qta_viewer",
        "group_role_assignments",
        "role_code <> 'AI_QUOTA_VIEWER'",
    )

    code_column = sa.String(64)
    op.bulk_insert(
        sa.table("roles", sa.column("code", code_column)),
        [{"code": code} for code in ROLES],
    )
    op.bulk_insert(
        sa.table("permissions", sa.column("code", code_column)),
        [{"code": code} for code in PERMISSIONS],
    )
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_code", code_column),
            sa.column("permission_code", code_column),
        ),
        [
            {"role_code": role, "permission_code": permission}
            for role, permission in ROLE_PERMISSIONS
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the QTA access catalog could orphan role assignments and audit history. "
        "Restore a verified pre-0007 backup to a separate database instead."
    )
