"""Explicit inputs and public projections for QTA endpoints (Phase 4, Stage Q2).

All quantities represent one abstract monthly quota unit ("đơn vị hạn mức", PD-Q1).
No field carries forbidden naming or semantics (period, semester, cycle, price, token,
credit, consumption). Every request input sets ``extra="forbid"``.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from aq_uai_api.directory.schemas import Code, Input, Name, SearchParams

QuotaGroupKind = Literal["SYSTEM", "AI_SPECIALIST"]
QuotaGroupOrigin = Literal["SYNC", "SPECIALIST"]
ProviderType = Literal["EXTERNAL", "INTERNAL"]
Capability = Literal["TEXT", "IMAGE", "VOICE"]
RiskLevel = Literal["HIGH", "MEDIUM", "LOW"]

MAX_MONTHLY_LIMIT = 9_223_372_036_854_775_807
MonthlyLimit = Annotated[StrictInt, Field(ge=0, le=MAX_MONTHLY_LIMIT)]
WarningThresholdPct = Annotated[StrictInt, Field(ge=1, le=100)]


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
