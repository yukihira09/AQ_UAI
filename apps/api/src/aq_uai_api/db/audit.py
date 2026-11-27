"""Insert typed, low-sensitivity audit events into a service-owned transaction."""

import json
from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, SessionTransactionOrigin

from aq_uai_api.db.identity import AuditEvent


class AuditAction(StrEnum):
    USER_CREATED = "user.created"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_IDENTITY_UPDATED = "user.identity_updated"
    USER_TRANSFERRED = "user.transferred"
    UNIT_CREATED = "unit.created"
    UNIT_UPDATED = "unit.updated"
    UNIT_STATE_CHANGED = "unit.state_changed"
    GROUP_CREATED = "group.created"
    GROUP_UPDATED = "group.updated"
    GROUP_STATE_CHANGED = "group.state_changed"
    USER_STATE_CHANGED = "user.state_changed"
    MEMBERSHIP_STATE_CHANGED = "membership.state_changed"
    ROLE_ASSIGNMENT_CREATED = "role_assignment.created"
    ROLE_ASSIGNMENT_REMOVED = "role_assignment.removed"
    AUTH_LOGIN_REJECTED = "auth.login_rejected"
    AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    AUTH_OPERATOR_RESET = "auth.operator_reset"
    AUTH_ADMIN_BOOTSTRAPPED = "auth.admin_bootstrapped"
    # MDL (M3). Payloads hold names, IDs and enum values only. The endpoint appears as
    # its origin (scheme://host[:port]); secrets never appear (RULE-MDL-04).
    MDL_PROVIDER_CREATED = "mdl.provider_created"
    MDL_PROVIDER_UPDATED = "mdl.provider_updated"
    MDL_PROVIDER_STATE_CHANGED = "mdl.provider_state_changed"
    MDL_PROVIDER_CREDENTIAL_ROTATED = "mdl.provider_credential_rotated"
    MDL_AGREEMENT_RECORDED = "mdl.agreement_recorded"
    MDL_AGREEMENT_WITHDRAWN = "mdl.agreement_withdrawn"
    MDL_MODEL_CREATED = "mdl.model_created"
    MDL_MODEL_UPDATED = "mdl.model_updated"
    MDL_MODEL_STATE_CHANGED = "mdl.model_state_changed"
    MDL_MODEL_RISK_CHANGED = "mdl.model_risk_changed"
    # M4. Outcome of one connection test: status and fixed codes only, never a provider
    # response body, header, endpoint path or secret.
    MDL_MODEL_CONNECTION_TESTED = "mdl.model_connection_tested"
    # M5. Routing change: model IDs, revision and the optional decision document number.
    MDL_ROUTING_CHANGED = "mdl.routing_changed"
    # Operator command (``python -m aq_uai_api.mdl.rewrap``): key rotation, no actor.
    MDL_CREDENTIAL_REWRAPPED = "mdl.credential_rewrapped"
    # QTA (Phase 4, Q1). Payloads hold IDs, counts, dates and policy fields only.
    QTA_MONTHLY_BUDGET_SET = "qta.monthly_budget_set"
    QTA_GROUPS_SYNCED = "qta.groups_synced"
    QTA_GROUP_QUOTA_UPDATED = "qta.group_quota_updated"
    QTA_USER_SUSPENDED = "qta.user_suspended"
    QTA_USER_RESTORED = "qta.user_restored"
    QTA_MONTHLY_RESET_EXECUTED = "qta.monthly_reset_executed"
    # Scheduled 1st-of-month CLI reset (no authenticated browser actor).
    QTA_MONTHLY_RESET_SCHEDULED = "qta.monthly_reset_scheduled"


class _AuditChanges(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )


class ActiveChange(_AuditChanges):
    before: bool
    after: bool


class UserStateChange(_AuditChanges):
    before: Literal["PENDING", "ACTIVE", "DISABLED"]
    after: Literal["PENDING", "ACTIVE", "DISABLED"]


class RevocationCount(_AuditChanges):
    revoked_sessions: int = Field(ge=0)


class UserCreated(_AuditChanges):
    primary_unit_id: UUID
    state: Literal["PENDING", "ACTIVE"]


class NameChange(_AuditChanges):
    before: str = Field(max_length=255)
    after: str = Field(min_length=1, max_length=255)


class IdentityFields(_AuditChanges):
    username: str = Field(min_length=1, max_length=64)
    code_type: Literal["STAFF", "STUDENT"]
    institutional_code: str = Field(min_length=1, max_length=64)


class IdentityChange(_AuditChanges):
    before: IdentityFields
    after: IdentityFields


class UnitFields(_AuditChanges):
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)


class UnitCreated(_AuditChanges):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class UnitChange(_AuditChanges):
    before: UnitFields
    after: UnitFields


class GroupCreated(_AuditChanges):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["SYSTEM", "AUTHORIZATION", "AI_SPECIALIST"]


class TransferChange(_AuditChanges):
    before: UUID
    after: UUID


class MembershipChange(_AuditChanges):
    user_id: UUID
    before: bool | None
    after: bool


class AssignmentChange(_AuditChanges):
    subject_type: Literal["USER", "GROUP"]
    subject_id: UUID
    role_code: str = Field(min_length=1, max_length=64)
    scope: Literal["UNIT", "GLOBAL"]
    unit_id: UUID | None


ProviderTypeCode = Literal["EXTERNAL", "INTERNAL"]
AuthSchemeCode = Literal["BEARER", "HEADER_KEY", "NONE"]
CapabilityCode = Literal["TEXT", "IMAGE", "VOICE"]
RiskCode = Literal["HIGH", "MEDIUM", "LOW"]
AgreementBasisCode = Literal["NO_TRAINING_COMMITMENT", "SCHOOL_WRITTEN_AUTHORIZATION"]


class ProviderFields(_AuditChanges):
    name: str = Field(min_length=1, max_length=255)
    api_style: Literal["OPENAI_COMPATIBLE", "OPENAI_COMPATIBLE_V2"]
    endpoint_origin: str = Field(min_length=1, max_length=2048)
    auth_scheme: AuthSchemeCode
    auth_header_name: str | None = Field(default=None, max_length=64)


class ProviderCreated(ProviderFields):
    provider_type: ProviderTypeCode
    has_credential: bool


class ProviderChange(_AuditChanges):
    before: ProviderFields
    after: ProviderFields
    # The full endpoint is not audited; this records a path-only change.
    endpoint_changed: bool
    connection_version: int = Field(ge=1)


class CredentialRotated(_AuditChanges):
    credential_version: int = Field(ge=1)


class AgreementFields(_AuditChanges):
    provider_id: UUID
    basis: AgreementBasisCode
    document_number: str = Field(min_length=1, max_length=128)


class AgreementRecorded(AgreementFields):
    signed_on: date | None


class ModelFields(_AuditChanges):
    display_name: str = Field(min_length=1, max_length=255)
    capabilities: list[CapabilityCode] = Field(min_length=1, max_length=3)
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)


class ModelCreated(ModelFields):
    provider_id: UUID
    technical_id: str = Field(min_length=1, max_length=255)
    risk_level: RiskCode | None


class ModelChange(_AuditChanges):
    before: ModelFields
    after: ModelFields


class RiskChange(_AuditChanges):
    before: RiskCode | None
    after: RiskCode | None


class ConnectionTested(_AuditChanges):
    test_id: UUID
    status: Literal["PASSED", "FAILED"]
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z_]{0,39}$")
    http_status_class: int | None = Field(default=None, ge=1, le=5)
    latency_ms: int | None = Field(default=None, ge=0)
    connection_version: int = Field(ge=1)
    credential_version: int | None = Field(default=None, ge=1)
    # D4: whether the tester confirmed the provider-charge notice (external providers).
    charges_acknowledged: bool = False


class RoutingSlots(_AuditChanges):
    primary_model_id: UUID | None
    fallback_model_id: UUID | None


class RoutingChanged(_AuditChanges):
    revision: int = Field(ge=1)
    before: RoutingSlots
    after: RoutingSlots
    decision_reference: str | None = Field(default=None, min_length=1, max_length=128)


class CredentialRewrapped(_AuditChanges):
    key_id_before: str = Field(min_length=1, max_length=32)
    key_id_after: str = Field(min_length=1, max_length=32)
    credential_version: int = Field(ge=1)


SuspensionScopeCode = Literal["ALL_MODELS", "PAID_EXTERNAL_ONLY"]
ResetTriggerCode = Literal["SCHEDULED", "MANUAL_SIMULATION"]


class BudgetRevisionRecorded(_AuditChanges):
    period_month: date
    revision: int = Field(ge=1)
    before_limit: int | None = Field(default=None, ge=1)
    after_limit: int = Field(ge=1)
    before_decision_number: str | None = Field(default=None, min_length=1, max_length=128)
    decision_number: str = Field(min_length=1, max_length=128)
    decision_date: date


class GroupsSynced(_AuditChanges):
    system_group_count: int = Field(ge=0)
    active_member_count: int = Field(ge=0)
    specialist_group_count: int = Field(ge=0)
    groups_added: int = Field(ge=0)
    groups_retired: int = Field(ge=0)


class GroupQuotaUpdated(_AuditChanges):
    group_id: UUID
    model_id: UUID
    before_enabled: bool | None = None
    after_enabled: bool
    before_limit: int | None = Field(default=None, ge=0)
    after_limit: int = Field(ge=0)
    warning_threshold_pct: int | None = Field(default=None, ge=1, le=100)


class UserSuspended(_AuditChanges):
    user_id: UUID
    scope: SuspensionScopeCode
    ordered_by: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None


class UserRestored(_AuditChanges):
    user_id: UUID
    suspension_id: UUID


class MonthlyResetRecorded(_AuditChanges):
    period_month: date
    trigger_mode: ResetTriggerCode


_EVENT_RULES = {
    AuditAction.USER_CREATED: ("user", "SUCCESS", UserCreated),
    AuditAction.USER_PROFILE_UPDATED: ("user", "SUCCESS", NameChange),
    AuditAction.USER_IDENTITY_UPDATED: ("user", "SUCCESS", IdentityChange),
    AuditAction.USER_TRANSFERRED: ("user", "SUCCESS", TransferChange),
    AuditAction.UNIT_CREATED: ("unit", "SUCCESS", UnitCreated),
    AuditAction.UNIT_UPDATED: ("unit", "SUCCESS", UnitChange),
    AuditAction.UNIT_STATE_CHANGED: ("unit", "SUCCESS", ActiveChange),
    AuditAction.GROUP_CREATED: ("account_group", "SUCCESS", GroupCreated),
    AuditAction.GROUP_UPDATED: ("account_group", "SUCCESS", NameChange),
    AuditAction.GROUP_STATE_CHANGED: ("account_group", "SUCCESS", ActiveChange),
    AuditAction.USER_STATE_CHANGED: ("user", "SUCCESS", UserStateChange),
    AuditAction.MEMBERSHIP_STATE_CHANGED: ("group_membership", "SUCCESS", MembershipChange),
    AuditAction.ROLE_ASSIGNMENT_CREATED: ("role_assignment", "SUCCESS", AssignmentChange),
    AuditAction.ROLE_ASSIGNMENT_REMOVED: ("role_assignment", "SUCCESS", AssignmentChange),
    AuditAction.AUTH_LOGIN_REJECTED: ("login", "FAILURE", None),
    AuditAction.AUTH_LOGIN_SUCCEEDED: ("user", "SUCCESS", None),
    AuditAction.AUTH_LOGOUT: ("user", "SUCCESS", None),
    AuditAction.AUTH_PASSWORD_CHANGED: ("user", "SUCCESS", RevocationCount),
    AuditAction.AUTH_OPERATOR_RESET: ("user", "SUCCESS", RevocationCount),
    AuditAction.AUTH_ADMIN_BOOTSTRAPPED: ("user", "SUCCESS", None),
    AuditAction.MDL_PROVIDER_CREATED: ("mdl_provider", "SUCCESS", ProviderCreated),
    AuditAction.MDL_PROVIDER_UPDATED: ("mdl_provider", "SUCCESS", ProviderChange),
    AuditAction.MDL_PROVIDER_STATE_CHANGED: ("mdl_provider", "SUCCESS", ActiveChange),
    AuditAction.MDL_PROVIDER_CREDENTIAL_ROTATED: ("mdl_provider", "SUCCESS", CredentialRotated),
    AuditAction.MDL_AGREEMENT_RECORDED: ("mdl_agreement", "SUCCESS", AgreementRecorded),
    AuditAction.MDL_AGREEMENT_WITHDRAWN: ("mdl_agreement", "SUCCESS", AgreementFields),
    AuditAction.MDL_MODEL_CREATED: ("mdl_model", "SUCCESS", ModelCreated),
    AuditAction.MDL_MODEL_UPDATED: ("mdl_model", "SUCCESS", ModelChange),
    AuditAction.MDL_MODEL_STATE_CHANGED: ("mdl_model", "SUCCESS", ActiveChange),
    AuditAction.MDL_MODEL_RISK_CHANGED: ("mdl_model", "SUCCESS", RiskChange),
    AuditAction.MDL_MODEL_CONNECTION_TESTED: ("mdl_model", "SUCCESS", ConnectionTested),
    AuditAction.MDL_ROUTING_CHANGED: ("mdl_routing_revision", "SUCCESS", RoutingChanged),
    AuditAction.MDL_CREDENTIAL_REWRAPPED: ("mdl_provider", "SUCCESS", CredentialRewrapped),
    AuditAction.QTA_MONTHLY_BUDGET_SET: ("qta_budget_revision", "SUCCESS", BudgetRevisionRecorded),
    AuditAction.QTA_GROUPS_SYNCED: ("qta_group_sync_run", "SUCCESS", GroupsSynced),
    AuditAction.QTA_GROUP_QUOTA_UPDATED: ("qta_group_model_quota", "SUCCESS", GroupQuotaUpdated),
    AuditAction.QTA_USER_SUSPENDED: ("qta_suspension", "SUCCESS", UserSuspended),
    AuditAction.QTA_USER_RESTORED: ("qta_suspension", "SUCCESS", UserRestored),
    AuditAction.QTA_MONTHLY_RESET_EXECUTED: ("qta_monthly_reset", "SUCCESS", MonthlyResetRecorded),
    AuditAction.QTA_MONTHLY_RESET_SCHEDULED: ("qta_monthly_reset", "SUCCESS", MonthlyResetRecorded),
}
_OPERATOR_ACTIONS = {
    AuditAction.AUTH_OPERATOR_RESET,
    AuditAction.AUTH_ADMIN_BOOTSTRAPPED,
    AuditAction.MDL_CREDENTIAL_REWRAPPED,
    AuditAction.QTA_MONTHLY_RESET_SCHEDULED,
}


def write_audit_event(
    session: Session,
    *,
    action: AuditAction,
    request_id: UUID,
    institution_id: UUID | None = None,
    actor_id: UUID | None = None,
    target_id: UUID | None = None,
    changes: _AuditChanges | None = None,
) -> AuditEvent:
    transaction = session.get_transaction()
    if transaction is None or transaction.origin != SessionTransactionOrigin.BEGIN:
        raise RuntimeError("Audit writes require an explicit service transaction.")
    if not isinstance(action, AuditAction) or not isinstance(request_id, UUID):
        raise ValueError("Unsupported audit action or request ID.")
    if any(
        value is not None and not isinstance(value, UUID)
        for value in (institution_id, actor_id, target_id)
    ):
        raise ValueError("Audit identifiers must be UUIDs.")

    target_type, outcome, change_model = _EVENT_RULES[action]
    if action == AuditAction.AUTH_LOGIN_REJECTED:
        if actor_id is not None or target_id is not None:
            raise ValueError("Rejected sign-in events contain no actor or target ID.")
    elif action in _OPERATOR_ACTIONS:
        if institution_id is None or target_id is None or actor_id is not None:
            raise ValueError("Operator events require an institution and target without an actor.")
    elif institution_id is None or actor_id is None or target_id is None:
        raise ValueError("Administrative events require institution, actor, and target IDs.")

    if change_model is None:
        if changes is not None:
            raise ValueError("This audit action has no change payload.")
        payload = {}
    else:
        if type(changes) is not change_model:
            raise ValueError("Unsupported audit changes for this action.")
        try:
            payload = change_model.model_validate(changes).model_dump(mode="json")
        except ValueError:
            raise ValueError("Invalid audit changes for this action.") from None

    event = AuditEvent(
        institution_id=institution_id,
        actor_id=actor_id,
        action=action.value,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        occurred_at=func.clock_timestamp(),
        request_id=str(request_id),
        changes=payload,
    )
    session.add(event)
    return event


def public_audit_changes(event: AuditEvent) -> dict:
    """Project stored changes through the action's approved payload schema."""
    try:
        action = AuditAction(event.action)
    except ValueError:
        return {}
    model = _EVENT_RULES[action][2]
    if model is None:
        return {}
    payload = json.dumps(event.changes)
    try:
        return model.model_validate_json(payload).model_dump(mode="json")
    except ValueError:
        if action is AuditAction.MEMBERSHIP_STATE_CHANGED:
            # Earlier records used only the state pair. Preserve those fields
            # without inventing a user identifier.
            try:
                return ActiveChange.model_validate_json(payload).model_dump(mode="json")
            except ValueError:
                return {}
        return {}
