"""Create one diagnostic table for proving PostgreSQL persistence.

Revision ID: 0001_phase1_metadata
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_phase1_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
    )
    op.bulk_insert(table, [
        {"key": "name", "value": "AQ EduUAI"},
        {"key": "milestone", "value": "phase-1-foundation"},
    ])


def downgrade() -> None:
    op.drop_table("app_metadata")
