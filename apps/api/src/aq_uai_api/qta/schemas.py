"""Explicit inputs and public projections for QTA endpoints (Phase 4, Stages Q2–Q4).

All quantities represent one abstract monthly quota unit ("đơn vị hạn mức", PD-Q1).
Every request input sets ``extra="forbid"``.
"""

import math
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from aq_uai_api.directory.schemas import (
    AccountState,
    Code,
    Input,
    Name,
    PageParams,
    SearchParams,
    clean_text,
)
from aq_uai_api.qta import periods

QuotaGroupKind = Literal["SYSTEM", "AI_SPECIALIST"]
QuotaGroupOrigin = Literal["SYNC", "SPECIALIST"]
ProviderType = Literal["EXTERNAL", "INTERNAL"]
Capability = Literal["TEXT", "IMAGE", "VOICE"]
RiskLevel = Literal["HIGH", "MEDIUM", "LOW"]
ExclusionReason = Literal["NOT_ENROLLED", "RETIRED", "GROUP_INACTIVE", "USER_NOT_ACTIVE"]
BudgetStatus = Literal["RECORDED", "NOT_RECORDED"]
AllocationStatus = Literal["LIVE", "NOT_SNAPSHOTTED"]
UnitLabel = Literal["đơn vị hạn mức"]
QuotaStatus = Literal["ACTIVE", "SUSPENDED"]
SuspensionScope = Literal["ALL_MODELS", "PAID_EXTERNAL_ONLY"]
SuspensionStatus = Literal["ACTIVE", "EXPIRED", "RESTORED"]
AccessReasonCode = Literal[
    "USER_NOT_FOUND",
    "USER_NOT_ACTIVE",
    "MODEL_UNAVAILABLE",
    "SUSPENDED_ALL_MODELS",
    "SUSPENDED_PAID_EXTERNAL",
    "NO_ENTITLEMENT",
]
EventType = Literal["MONTHLY_REFRESH", "SUSPEND", "RESTORE"]
ResetTriggerMode = Literal["SCHEDULED", "MANUAL_SIMULATION"]
CurrentResetStatus = Literal["COMPLETED", "PENDING"]

MAX_MONTHLY_LIMIT = 9_223_372_036_854_775_807
MonthlyLimit = Annotated[StrictInt, Field(ge=0, le=MAX_MONTHLY_LIMIT)]
PositiveBudgetLimit = Annotated[StrictInt, Field(ge=1, le=MAX_MONTHLY_LIMIT)]
WarningThresholdPct = Annotated[StrictInt, Field(ge=1, le=100)]
DecisionNumber = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128),
    AfterValidator(clean_text),
]
SuspensionReason = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(clean_text),
]
OrderedBy = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(clean_text),
]
RestoreNote = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(clean_text),
]


def _strict_calendar_date(value: object) -> object:
    """Reject datetimes, booleans, and integers so decision_date is a pure ISO calendar date."""
    if isinstance(value, (datetime, int, bool)):
        raise ValueError("Enter a valid calendar date (YYYY-MM-DD).")
    return value


def _strict_aware_input(value: object) -> object:
    """Reject booleans and numeric epoch values so expires_at is an ISO datetime."""
    if isinstance(value, (int, float, bool)):
        raise ValueError("Enter a timezone-aware ISO datetime.")
    return value


def _future_utc_datetime(value: datetime) -> datetime:
    """Require finite timezone-aware datetime strictly after utc_now() (PD-Q3)."""
    if not math.isfinite(value.timestamp()):
        raise ValueError("Expiry timestamp must be finite.")
    normalized = value.astimezone(UTC)
    if normalized <= periods.utc_now():
        raise ValueError("Expiry timestamp must be strictly in the future.")
    return normalized


StrictCalendarDate = Annotated[date, BeforeValidator(_strict_calendar_date)]
FutureAwareDatetime = Annotated[
    AwareDatetime,
    BeforeValidator(_strict_aware_input),
    AfterValidator(_future_utc_datetime),
]


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CreateSpecialistGroup(Input):
    """Create an AI_SPECIALIST group and enroll it in QTA (FR-QTA-022)."""

    code: Code
    name: Name


class UpdateSpecialistGroup(Input):
    """Rename an enrolled AI_SPECIALIST group."""

    name: Name


class GroupQuotaItemIn(Input):
    """One (group × model) monthly quota rule in abstract 'đơn vị hạn mức' (FR-QTA-021)."""

    model_id: UUID
    enabled: StrictBool
    monthly_limit: MonthlyLimit
    warning_threshold_pct: WarningThresholdPct | None = None


class UpsertGroupQuotas(Input):
    """Batch upsert for one enrolled group's per-model quotas; never deletes unmentioned models."""

    quotas: list[GroupQuotaItemIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def distinct_models(self):
        seen: set[UUID] = set()
        for item in self.quotas:
            if item.model_id in seen:
                raise ValueError("Each model may appear at most once in a quota update.")
            seen.add(item.model_id)
        return self


class QtaGroupFilters(SearchParams):
    kind: QuotaGroupKind | None = None
    origin: QuotaGroupOrigin | None = None
    active: bool | None = None
    in_directory: bool | None = None


class MonthQuery(Input):
    """Optional YYYY-MM calendar month query parameter (strictly rejects extra query keys)."""

    month: str | None = None


class SetMonthlyBudget(Input):
    """Record a new append-only monthly school budget revision (FR-QTA-010, PD-Q4)."""

    total_limit: PositiveBudgetLimit
    decision_number: DecisionNumber
    decision_date: StrictCalendarDate


class SuspendUser(Input):
    """Individual AI kill-switch request (FR-QTA-040, PD-Q2, PD-Q3)."""

    scope: SuspensionScope
    reason: SuspensionReason
    ordered_by: OrderedBy
    expires_at: FutureAwareDatetime | None = None


class RestoreUser(Input):
    """Restore an active AI suspension without altering quota rules (FR-QTA-041)."""

    note: RestoreNote | None = None


class QtaEventFilters(PageParams):
    """Query filters for append-only QTA events (FR-QTA-050)."""

    month: str | None = None
    event_type: EventType | None = None
    user_id: UUID | None = None


class QtaModelOut(Output):
    """Read-only projection of an active MDL model eligible for QTA quota rules."""

    id: UUID
    institution_id: UUID
    provider_id: UUID
    provider_name: str
    provider_type: ProviderType
    technical_id: str
    display_name: str
    capabilities: list[Capability]
    risk_level: RiskLevel | None
    active: bool


class GroupQuotaRuleOut(Output):
    """One configured per-member monthly quota rule (group × model)."""

    id: UUID
    model_id: UUID
    model_technical_id: str
    model_display_name: str
    model_active: bool
    provider_name: str
    provider_type: ProviderType
    enabled: bool
    monthly_limit: int
    warning_threshold_pct: int | None
    updated_by: UUID
    updated_at: datetime


class QtaGroupOut(Output):
    """Enrolled QTA quota group combining registry metadata, directory status, and quotas."""

    id: UUID
    institution_id: UUID
    code: str
    name: str
    kind: QuotaGroupKind
    origin: QuotaGroupOrigin
    active: bool
    in_directory: bool
    enrolled_by: UUID
    enrolled_at: datetime
    last_synced_at: datetime | None
    active_member_count: int
    quotas: list[GroupQuotaRuleOut]


class SyncRunOut(Output):
    """Immutable record of one system-group reconciliation run (FR-QTA-020)."""

    id: UUID
    institution_id: UUID
    system_group_count: int
    active_member_count: int
    specialist_group_count: int
    groups_added: int
    groups_retired: int
    synced_by: UUID
    synced_at: datetime


class QtaUserOut(Output):
    """Scoped user item for QTA personal lookup picker (no group or quota payload)."""

    id: UUID
    username: str
    display_name: str
    institutional_code: str
    primary_unit_id: UUID
    state: AccountState
    quota_status: QuotaStatus


class QtaUserSummaryOut(Output):
    """Compact user identity summary included in entitlement lookup responses."""

    id: UUID
    username: str
    display_name: str
    state: AccountState


class SuspensionRestorationOut(Output):
    """Immutable restoration metadata attached to a restored suspension (FR-QTA-041)."""

    restored_by: UUID
    restored_at: datetime
    note: str | None


class SuspensionOut(Output):
    """Append-only individual kill-switch record with computed state (FR-QTA-040/041)."""

    id: UUID
    user_id: UUID
    scope: SuspensionScope
    reason: str
    ordered_by: str
    expires_at: datetime | None
    suspended_by: UUID
    suspended_at: datetime
    status: SuspensionStatus
    restoration: SuspensionRestorationOut | None = None


class ModelAccessOut(Output):
    """Per-model access evaluation from check_ai_access (R5, RULE-QTA-03)."""

    allowed: bool
    reason: AccessReasonCode | None


class UserGroupMembershipOut(Output):
    """One active directory membership of a user in a SYSTEM or AI_SPECIALIST group."""

    group_id: UUID
    code: str
    name: str
    kind: QuotaGroupKind
    origin: QuotaGroupOrigin | None
    active: bool
    in_directory: bool | None
    qualifies: bool
    excluded_reason: ExclusionReason | None


class GroupContributionOut(Output):
    """One qualifying group's contribution toward a user's model base entitlement."""

    group_id: UUID
    code: str
    name: str
    kind: QuotaGroupKind
    origin: QuotaGroupOrigin
    enabled: bool
    monthly_limit: int
    contributes: int


class ModelEntitlementOut(Output):
    """Additive monthly base entitlement and access status for one usable model."""

    model_id: UUID
    display_name: str
    technical_id: str
    provider_type: ProviderType
    base_entitlement: int
    contributions: list[GroupContributionOut]
    access: ModelAccessOut
    actual_consumption: None = None
    remaining_quota: None = None
    consumption_status: Literal["NOT_INTEGRATED"] = "NOT_INTEGRATED"


class UserEntitlementsOut(Output):
    """Personal additive monthly entitlement lookup with kill-switch status (FR-QTA-030/031/040)."""

    user: QtaUserSummaryOut
    month: str
    unit_label: UnitLabel = "đơn vị hạn mức"
    quota_status: QuotaStatus
    suspension: SuspensionOut | None
    memberships: list[UserGroupMembershipOut]
    models: list[ModelEntitlementOut]
    base_entitlement_total: int


class BudgetRevisionOut(Output):
    """One immutable institutional monthly budget revision (FR-QTA-010, INV-18)."""

    id: UUID
    revision: int
    total_limit: int
    decision_number: str
    decision_date: date
    recorded_by: UUID
    recorded_at: datetime


class MonthlyBudgetOut(Output):
    """Institutional monthly budget view with revision history and live allocation status."""

    month: str
    unit_label: UnitLabel = "đơn vị hạn mức"
    status: BudgetStatus
    status_label: str
    current: BudgetRevisionOut | None
    revisions: list[BudgetRevisionOut]
    allocation_status: AllocationStatus
    allocated: int | None
    remaining: int | None
    over_allocated: int | None


class QtaEventOut(Output):
    """Immutable QTA ledger event row (FR-QTA-032, FR-QTA-040, FR-QTA-041, FR-QTA-050)."""

    id: UUID
    month: str
    event_type: EventType
    user_id: UUID | None
    actor_id: UUID | None
    summary: str
    occurred_at: datetime


class MonthlyResetOut(Output):
    """Immutable monthly reset marker row (FR-QTA-032)."""

    id: UUID
    month: str
    trigger_mode: ResetTriggerMode
    triggered_by: UUID | None
    executed_at: datetime


class CurrentMonthlyResetOut(Output):
    """Current institution month reset status summary."""

    month: str
    status: CurrentResetStatus
    reset: MonthlyResetOut | None


class MonthlyResetsOut(Output):
    """Monthly reset history newest-first plus current institution month status."""

    current: CurrentMonthlyResetOut
    items: list[MonthlyResetOut]
    total: int
    limit: int
    offset: int
