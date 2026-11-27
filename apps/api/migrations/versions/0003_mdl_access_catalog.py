"""Add the MDL permission catalog and its direct-GLOBAL-only role constraints.

Revision ID: 0003_mdl_access_catalog
Revises: 0002_identity_foundation
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_mdl_access_catalog"
down_revision = "0002_identity_foundation"
branch_labels = None
depends_on = None

ROLE = "AI_MODEL_ADMIN"
PERMISSIONS = ("mdl.read", "mdl.manage")


def upgrade() -> None:
    # MDL authority is direct and institution-wide only. FOUNDATION_ADMIN is not changed.
    op.create_check_constraint(
        "ck_user_role_assignments_mdl_admin_global",
        "user_role_assignments",
        "role_code <> 'AI_MODEL_ADMIN' OR scope = 'GLOBAL'",
    )
    op.create_check_constraint(
        "ck_group_role_assignments_no_mdl_admin",
        "group_role_assignments",
        "role_code <> 'AI_MODEL_ADMIN'",
    )

    code_column = sa.String(64)
    op.bulk_insert(sa.table("roles", sa.column("code", code_column)), [{"code": ROLE}])
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
        [{"role_code": ROLE, "permission_code": code} for code in PERMISSIONS],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the MDL access catalog could orphan role assignments and audit history. "
        "Restore a verified pre-0003 backup to a separate database instead."
    )
