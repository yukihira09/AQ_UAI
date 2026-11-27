"""Create the QTA budget revision, group registry, quota, sync, kill-switch, reset and event tables.

Revision ID: 0008_qta_schema
Revises: 0007_qta_access_catalog
Create Date: 2026-11-26 (revised in Q1-R before any persistent deployment)

Additive only: one composite UNIQUE constraint on ``account_groups(institution_id, id, kind)``
and eight new empty QTA tables; no existing rows change and no seed data is inserted.
Every period column is constrained to day 1 of a calendar month (FR-QTA-010, FR-QTA-050).
No consumption/usage deduction, pricing or token-to-credit conversion table is created.
Runtime column-level grants (zero DELETE anywhere; append-only history/events INSERT-only)
are applied by ``aq_uai_api.db.provision.apply_runtime_privileges``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_qta_schema"
down_revision = "0007_qta_access_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_account_groups_institution_id_kind",
        "account_groups",
        ["institution_id", "id", "kind"],
    )
    op.create_table(
        "qta_budget_revisions",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("total_limit", sa.BigInteger(), nullable=False),
        sa.Column("decision_number", sa.String(length=128), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1", name="ck_qta_budget_revisions_month_start"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_qta_budget_revisions_revision"),
        sa.CheckConstraint("total_limit > 0", name="ck_qta_budget_revisions_total_limit"),
        sa.CheckConstraint(
            "decision_number <> '' AND decision_number !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_qta_budget_revisions_decision_number",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_budget_revisions_institution"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "recorded_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_budget_revisions_recorded_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "period_month",
            "revision",
            name="uq_qta_budget_revisions_institution_month_rev",
        ),
    )
    op.create_table(
        "qta_quota_groups",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("group_kind", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("in_directory", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("enrolled_by", sa.Uuid(), nullable=False),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "group_kind IN ('SYSTEM', 'AI_SPECIALIST')", name="ck_qta_quota_groups_kind"
        ),
        sa.CheckConstraint(
            "origin IN ('SYNC', 'SPECIALIST')", name="ck_qta_quota_groups_origin"
        ),
        sa.CheckConstraint(
            "(origin = 'SYNC' AND group_kind = 'SYSTEM') "
            "OR (origin = 'SPECIALIST' AND group_kind = 'AI_SPECIALIST')",
            name="ck_qta_quota_groups_origin_kind",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "group_id", "group_kind"],
            ["account_groups.institution_id", "account_groups.id", "account_groups.kind"],
            name="fk_qta_quota_groups_account_group",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "enrolled_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_quota_groups_enrolled_by",
        ),
        sa.PrimaryKeyConstraint("institution_id", "group_id"),
    )
    op.create_table(
        "qta_group_model_quotas",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("monthly_limit", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("warning_threshold_pct", sa.SmallInteger(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
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
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("monthly_limit >= 0", name="ck_qta_group_model_quotas_limit"),
        sa.CheckConstraint(
            "warning_threshold_pct BETWEEN 1 AND 100",
            name="ck_qta_group_model_quotas_warning_pct",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "group_id"],
            ["qta_quota_groups.institution_id", "qta_quota_groups.group_id"],
            name="fk_qta_group_model_quotas_group",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_qta_group_model_quotas_model",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "updated_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_group_model_quotas_updated_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "group_id",
            "model_id",
            name="uq_qta_group_model_quotas_group_model",
        ),
    )
    op.create_index(
        "ix_qta_group_model_quotas_institution_model",
        "qta_group_model_quotas",
        ["institution_id", "model_id"],
        unique=False,
    )
    op.create_table(
        "qta_group_sync_runs",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("system_group_count", sa.Integer(), nullable=False),
        sa.Column("active_member_count", sa.Integer(), nullable=False),
        sa.Column("specialist_group_count", sa.Integer(), nullable=False),
        sa.Column("groups_added", sa.Integer(), nullable=False),
        sa.Column("groups_retired", sa.Integer(), nullable=False),
        sa.Column("synced_by", sa.Uuid(), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "system_group_count >= 0 AND active_member_count >= 0 "
            "AND specialist_group_count >= 0 AND groups_added >= 0 AND groups_retired >= 0",
            name="ck_qta_group_sync_runs_counts",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_group_sync_runs_institution"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "synced_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_group_sync_runs_synced_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_qta_group_sync_runs_institution_synced",
        "qta_group_sync_runs",
        ["institution_id", "synced_at"],
        unique=False,
    )
    op.create_table(
        "qta_suspensions",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("ordered_by", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by", sa.Uuid(), nullable=False),
        sa.Column(
            "suspended_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "scope IN ('ALL_MODELS', 'PAID_EXTERNAL_ONLY')", name="ck_qta_suspensions_scope"
        ),
        sa.CheckConstraint(
            "reason <> '' AND reason !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_qta_suspensions_reason",
        ),
        sa.CheckConstraint(
            "ordered_by <> '' AND ordered_by !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_qta_suspensions_ordered_by",
        ),
        sa.CheckConstraint(
            "isfinite(suspended_at) "
            "AND (expires_at IS NULL OR (isfinite(expires_at) AND expires_at > suspended_at))",
            name="ck_qta_suspensions_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["users.institution_id", "users.id"],
            name="fk_qta_suspensions_user",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "suspended_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_suspensions_suspended_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("institution_id", "id", name="uq_qta_suspensions_institution_id"),
    )
    op.create_index(
        "ix_qta_suspensions_institution_user_suspended",
        "qta_suspensions",
        ["institution_id", "user_id", "suspended_at"],
        unique=False,
    )
    op.create_table(
        "qta_suspension_restorations",
        sa.Column("suspension_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("restored_by", sa.Uuid(), nullable=False),
        sa.Column(
            "restored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "note IS NULL OR (note <> '' AND note !~ '^[[:space:]]|[[:space:]]$')",
            name="ck_qta_suspension_restorations_note",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "suspension_id"],
            ["qta_suspensions.institution_id", "qta_suspensions.id"],
            name="fk_qta_suspension_restorations_suspension",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "restored_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_suspension_restorations_restored_by",
        ),
        sa.PrimaryKeyConstraint("suspension_id"),
    )
    op.create_table(
        "qta_monthly_resets",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("trigger_mode", sa.String(length=20), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1", name="ck_qta_monthly_resets_month_start"
        ),
        sa.CheckConstraint(
            "trigger_mode IN ('SCHEDULED', 'MANUAL_SIMULATION')",
            name="ck_qta_monthly_resets_trigger_mode",
        ),
        sa.CheckConstraint(
            "trigger_mode = 'SCHEDULED' OR triggered_by IS NOT NULL",
            name="ck_qta_monthly_resets_manual_actor",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_monthly_resets_institution"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "triggered_by"],
            ["users.institution_id", "users.id"],
            name="fk_qta_monthly_resets_triggered_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id", "period_month", name="uq_qta_monthly_resets_institution_month"
        ),
    )
    op.create_table(
        "qta_events",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("EXTRACT(DAY FROM period_month) = 1", name="ck_qta_events_month_start"),
        sa.CheckConstraint(
            "event_type IN ('MONTHLY_REFRESH', 'SUSPEND', 'RESTORE')", name="ck_qta_events_type"
        ),
        sa.CheckConstraint(
            "(event_type = 'MONTHLY_REFRESH') = (user_id IS NULL)",
            name="ck_qta_events_user_presence",
        ),
        sa.CheckConstraint(
            "summary <> '' AND summary !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_qta_events_summary",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_events_institution"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["users.institution_id", "users.id"],
            name="fk_qta_events_user",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "actor_id"],
            ["users.institution_id", "users.id"],
            name="fk_qta_events_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_qta_events_institution_month_occurred",
        "qta_events",
        ["institution_id", "period_month", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the QTA schema would destroy append-only quota, suspension and reset history. "
        "Restore a verified pre-0008 backup to a separate database instead."
    )
