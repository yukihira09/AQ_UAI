"""Record agreement withdrawals in an append-only table (D5, M3).

Revision ID: 0005_mdl_agreement_withdrawals
Revises: 0004_mdl_schema
Create Date: 2026-11-25

Additive only: one new, empty table, plus a unique (institution_id, id) constraint on
agreements that every existing row already satisfies (id is the primary key). Agreements stay immutable; a withdrawal is
its own row, at most one per agreement, INSERT-only for the runtime login.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_mdl_agreement_withdrawals"
down_revision = "0004_mdl_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_mdl_provider_agreements_institution_id",
        "mdl_provider_agreements",
        ["institution_id", "id"],
    )
    op.create_table(
        "mdl_provider_agreement_withdrawals",
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("withdrawn_by", sa.Uuid(), nullable=False),
        sa.Column(
            "withdrawn_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "agreement_id"],
            ["mdl_provider_agreements.institution_id", "mdl_provider_agreements.id"],
            name="fk_mdl_agreement_withdrawals_agreement",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "withdrawn_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_agreement_withdrawals_withdrawn_by",
        ),
        sa.PrimaryKeyConstraint("agreement_id"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading would destroy append-only withdrawal history. "
        "Restore a verified pre-0005 backup to a separate database instead."
    )
