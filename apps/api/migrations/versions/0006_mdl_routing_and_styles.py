"""M5: routing decision reference (D13) and a second OpenAI-compatible API style.

Revision ID: 0006_mdl_routing_and_styles
Revises: 0005_mdl_agreement_withdrawals
Create Date: 2026-11-26

1. ``mdl_routing_revisions.decision_reference``: one nullable column on the append-only
   routing history. Existing rows
(none are expected before M5, which introduces routing writes) keep NULL, which means
"no document number recorded". The runtime login may INSERT the column but, as for every
other revision column, never UPDATE it (``aq_uai_api.db.provision``).
2. ``mdl_providers.api_style`` also accepts ``OPENAI_COMPATIBLE_V2`` (same request, but
   ``max_completion_tokens`` instead of ``max_tokens``, which newer models require). The
   check constraint is widened; every existing value stays valid.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_mdl_routing_and_styles"
down_revision = "0005_mdl_agreement_withdrawals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mdl_routing_revisions",
        sa.Column("decision_reference", sa.String(length=128), nullable=True),
    )
    op.create_check_constraint(
        "ck_mdl_routing_revisions_decision_reference",
        "mdl_routing_revisions",
        "decision_reference <> '' AND decision_reference !~ '^[[:space:]]|[[:space:]]$'",
    )
    op.drop_constraint("ck_mdl_providers_api_style", "mdl_providers", type_="check")
    op.create_check_constraint(
        "ck_mdl_providers_api_style",
        "mdl_providers",
        "api_style IN ('OPENAI_COMPATIBLE', 'OPENAI_COMPATIBLE_V2')",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading would destroy recorded decision references in append-only history. "
        "Restore a verified pre-0006 backup to a separate database instead."
    )
