"""QTA persistence (Phase 4, Q1-R). Mirrors migration ``0008_qta_schema`` exactly.

Tenant isolation: every table carries ``institution_id`` and every cross-table reference
uses a composite foreign key ``(institution_id, <id>)``.

Month-only invariant (FR-QTA-010, FR-QTA-050, RULE-QTA-01): every period column is a
``DATE`` constrained to the first day of a calendar month (``EXTRACT(DAY FROM period_month) = 1``).
No Semester, Research Project or Exam cycle column exists anywhere.

Append-only history (FR-QTA-010/050, INV-18, RULE-QTA-04): enforced by PostgreSQL column-level
grants in ``db/provision.py`` (zero DELETE on any QTA table; budget revisions, sync runs,
suspensions, restorations, monthly resets and QTA events are INSERT-only).
"""

from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from aq_uai_api.db.base import Base
from aq_uai_api.db.identity import UUIDPrimaryKey

QUOTA_GROUP_KINDS = ("SYSTEM", "AI_SPECIALIST")
QUOTA_GROUP_ORIGINS = ("SYNC", "SPECIALIST")
SUSPENSION_SCOPES = ("ALL_MODELS", "PAID_EXTERNAL_ONLY")
RESET_TRIGGER_MODES = ("SCHEDULED", "MANUAL_SIMULATION")
QTA_EVENT_TYPES = ("MONTHLY_REFRESH", "SUSPEND", "RESTORE")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _trimmed(column: str) -> str:
    return f"{column} <> '' AND {column} !~ '^[[:space:]]|[[:space:]]$'"


def _month_start(column: str = "period_month") -> str:
    return f"EXTRACT(DAY FROM {column}) = 1"


def _user_fk(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["institution_id", column], ["users.institution_id", "users.id"], name=name
    )


def _timestamp() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class QtaBudgetRevision(UUIDPrimaryKey, Base):
    """Append-only institutional monthly quota cap revisions (FR-QTA-010/011, INV-18).

    The active total for a month is the row with the highest ``revision`` for
    ``(institution_id, period_month)``. Earlier decisions are never overwritten.
    """

    __tablename__ = "qta_budget_revisions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_budget_revisions_institution"
        ),
        _user_fk("recorded_by", "fk_qta_budget_revisions_recorded_by"),
        sa.UniqueConstraint(
            "institution_id",
            "period_month",
            "revision",
            name="uq_qta_budget_revisions_institution_month_rev",
        ),
        sa.CheckConstraint(_month_start(), name="ck_qta_budget_revisions_month_start"),
        sa.CheckConstraint("revision >= 1", name="ck_qta_budget_revisions_revision"),
        sa.CheckConstraint("total_limit > 0", name="ck_qta_budget_revisions_total_limit"),
        sa.CheckConstraint(
            _trimmed("decision_number"), name="ck_qta_budget_revisions_decision_number"
        ),
    )

    institution_id: Mapped[UUID]
    period_month: Mapped[date]
    revision: Mapped[int]
    total_limit: Mapped[int] = mapped_column(sa.BigInteger)
    decision_number: Mapped[str] = mapped_column(sa.String(128))
    decision_date: Mapped[date]
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = _timestamp()


class QtaQuotaGroup(Base):
    """Registry of groups enrolled in QTA (FR-QTA-020, FR-QTA-022, RULE-QTA-05).

    System groups enter via explicit sync (``origin='SYNC'``); AI specialist groups enter
    when created through QTA (``origin='SPECIALIST'``). The composite FK to
    ``account_groups(institution_id, id, kind)`` combined with the kind check guarantees
    ``AUTHORIZATION`` groups can never be enrolled or receive quotas.
    """

    __tablename__ = "qta_quota_groups"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "group_id", "group_kind"],
            ["account_groups.institution_id", "account_groups.id", "account_groups.kind"],
            name="fk_qta_quota_groups_account_group",
        ),
        _user_fk("enrolled_by", "fk_qta_quota_groups_enrolled_by"),
        sa.CheckConstraint(_in("group_kind", QUOTA_GROUP_KINDS), name="ck_qta_quota_groups_kind"),
        sa.CheckConstraint(_in("origin", QUOTA_GROUP_ORIGINS), name="ck_qta_quota_groups_origin"),
        sa.CheckConstraint(
            "(origin = 'SYNC' AND group_kind = 'SYSTEM') "
            "OR (origin = 'SPECIALIST' AND group_kind = 'AI_SPECIALIST')",
            name="ck_qta_quota_groups_origin_kind",
        ),
    )

    institution_id: Mapped[UUID] = mapped_column(primary_key=True)
    group_id: Mapped[UUID] = mapped_column(primary_key=True)
    group_kind: Mapped[str] = mapped_column(sa.String(16))
    origin: Mapped[str] = mapped_column(sa.String(16))
    in_directory: Mapped[bool] = mapped_column(server_default=sa.true())
    enrolled_by: Mapped[UUID]
    enrolled_at: Mapped[datetime] = _timestamp()
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class QtaGroupModelQuota(UUIDPrimaryKey, Base):
    """Monthly quota rule for one enrolled (group, model) pair (FR-QTA-021, FR-QTA-030)."""

    __tablename__ = "qta_group_model_quotas"
    __table_args__ = (
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
        _user_fk("updated_by", "fk_qta_group_model_quotas_updated_by"),
        sa.UniqueConstraint(
            "institution_id",
            "group_id",
            "model_id",
            name="uq_qta_group_model_quotas_group_model",
        ),
        sa.CheckConstraint("monthly_limit >= 0", name="ck_qta_group_model_quotas_limit"),
        sa.CheckConstraint(
            "warning_threshold_pct BETWEEN 1 AND 100",
            name="ck_qta_group_model_quotas_warning_pct",
        ),
        sa.Index("ix_qta_group_model_quotas_institution_model", "institution_id", "model_id"),
    )

    institution_id: Mapped[UUID]
    group_id: Mapped[UUID]
    model_id: Mapped[UUID]
    enabled: Mapped[bool] = mapped_column(server_default=sa.true())
    monthly_limit: Mapped[int] = mapped_column(sa.BigInteger, server_default=sa.text("0"))
    warning_threshold_pct: Mapped[int | None] = mapped_column(sa.SmallInteger)
    updated_by: Mapped[UUID]
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class QtaGroupSyncRun(UUIDPrimaryKey, Base):
    """Append-only record of system-group reconciliation runs (FR-QTA-020)."""

    __tablename__ = "qta_group_sync_runs"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_group_sync_runs_institution"
        ),
        _user_fk("synced_by", "fk_qta_group_sync_runs_synced_by"),
        sa.CheckConstraint(
            "system_group_count >= 0 AND active_member_count >= 0 "
            "AND specialist_group_count >= 0 AND groups_added >= 0 AND groups_retired >= 0",
            name="ck_qta_group_sync_runs_counts",
        ),
        sa.Index("ix_qta_group_sync_runs_institution_synced", "institution_id", "synced_at"),
    )

    institution_id: Mapped[UUID]
    system_group_count: Mapped[int]
    active_member_count: Mapped[int]
    specialist_group_count: Mapped[int]
    groups_added: Mapped[int]
    groups_retired: Mapped[int]
    synced_by: Mapped[UUID]
    synced_at: Mapped[datetime] = _timestamp()


class QtaSuspension(UUIDPrimaryKey, Base):
    """Append-only individual kill-switch record (FR-QTA-040, RULE-QTA-03/04).

    Never mutates or zeroes the user's quota balance. ``expires_at`` is optional
    (``NULL`` = active until explicitly restored; PD-Q3). Lifting a suspension early
    inserts a row into ``qta_suspension_restorations`` rather than updating this row.
    """

    __tablename__ = "qta_suspensions"
    __table_args__ = (
        _user_fk("user_id", "fk_qta_suspensions_user"),
        _user_fk("suspended_by", "fk_qta_suspensions_suspended_by"),
        sa.UniqueConstraint("institution_id", "id", name="uq_qta_suspensions_institution_id"),
        sa.CheckConstraint(_in("scope", SUSPENSION_SCOPES), name="ck_qta_suspensions_scope"),
        sa.CheckConstraint(_trimmed("reason"), name="ck_qta_suspensions_reason"),
        sa.CheckConstraint(_trimmed("ordered_by"), name="ck_qta_suspensions_ordered_by"),
        sa.CheckConstraint(
            "isfinite(suspended_at) "
            "AND (expires_at IS NULL OR (isfinite(expires_at) AND expires_at > suspended_at))",
            name="ck_qta_suspensions_expiry",
        ),
        sa.Index(
            "ix_qta_suspensions_institution_user_suspended",
            "institution_id",
            "user_id",
            "suspended_at",
        ),
    )

    institution_id: Mapped[UUID]
    user_id: Mapped[UUID]
    scope: Mapped[str] = mapped_column(sa.String(24))
    reason: Mapped[str] = mapped_column(sa.String(500))
    ordered_by: Mapped[str] = mapped_column(sa.String(255))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    suspended_by: Mapped[UUID]
    suspended_at: Mapped[datetime] = _timestamp()


class QtaSuspensionRestoration(Base):
    """Append-only restoration of one suspension (FR-QTA-041). At most one row per suspension."""

    __tablename__ = "qta_suspension_restorations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "suspension_id"],
            ["qta_suspensions.institution_id", "qta_suspensions.id"],
            name="fk_qta_suspension_restorations_suspension",
        ),
        _user_fk("restored_by", "fk_qta_suspension_restorations_restored_by"),
        sa.CheckConstraint(
            "note IS NULL OR (note <> '' AND note !~ '^[[:space:]]|[[:space:]]$')",
            name="ck_qta_suspension_restorations_note",
        ),
    )

    suspension_id: Mapped[UUID] = mapped_column(primary_key=True)
    institution_id: Mapped[UUID]
    restored_by: Mapped[UUID]
    restored_at: Mapped[datetime] = _timestamp()
    note: Mapped[str | None] = mapped_column(sa.String(500))


class QtaMonthlyReset(UUIDPrimaryKey, Base):
    """Append-only monthly reset execution (FR-QTA-032). Unique per (institution, month)."""

    __tablename__ = "qta_monthly_resets"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_monthly_resets_institution"
        ),
        _user_fk("triggered_by", "fk_qta_monthly_resets_triggered_by"),
        sa.UniqueConstraint(
            "institution_id", "period_month", name="uq_qta_monthly_resets_institution_month"
        ),
        sa.CheckConstraint(_month_start(), name="ck_qta_monthly_resets_month_start"),
        sa.CheckConstraint(
            _in("trigger_mode", RESET_TRIGGER_MODES), name="ck_qta_monthly_resets_trigger_mode"
        ),
        sa.CheckConstraint(
            "trigger_mode = 'SCHEDULED' OR triggered_by IS NOT NULL",
            name="ck_qta_monthly_resets_manual_actor",
        ),
    )

    institution_id: Mapped[UUID]
    period_month: Mapped[date]
    trigger_mode: Mapped[str] = mapped_column(sa.String(20))
    triggered_by: Mapped[UUID | None]
    executed_at: Mapped[datetime] = _timestamp()


class QtaEvent(UUIDPrimaryKey, Base):
    """Append-only QTA event ledger: MONTHLY_REFRESH, SUSPEND, RESTORE (FR-QTA-032/040/041/050)."""

    __tablename__ = "qta_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_qta_events_institution"
        ),
        _user_fk("user_id", "fk_qta_events_user"),
        _user_fk("actor_id", "fk_qta_events_actor"),
        sa.CheckConstraint(_month_start(), name="ck_qta_events_month_start"),
        sa.CheckConstraint(_in("event_type", QTA_EVENT_TYPES), name="ck_qta_events_type"),
        sa.CheckConstraint(
            "(event_type = 'MONTHLY_REFRESH') = (user_id IS NULL)",
            name="ck_qta_events_user_presence",
        ),
        sa.CheckConstraint(_trimmed("summary"), name="ck_qta_events_summary"),
        sa.Index(
            "ix_qta_events_institution_month_occurred",
            "institution_id",
            "period_month",
            "occurred_at",
        ),
    )

    institution_id: Mapped[UUID]
    period_month: Mapped[date]
    event_type: Mapped[str] = mapped_column(sa.String(20))
    user_id: Mapped[UUID | None]
    actor_id: Mapped[UUID | None]
    summary: Mapped[str] = mapped_column(sa.String(500))
    occurred_at: Mapped[datetime] = _timestamp()
