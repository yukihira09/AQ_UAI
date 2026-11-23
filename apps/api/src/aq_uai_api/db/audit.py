"""Insert typed, low-sensitivity audit events into a service-owned transaction."""

import json
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
}
_OPERATOR_ACTIONS = {AuditAction.AUTH_OPERATOR_RESET, AuditAction.AUTH_ADMIN_BOOTSTRAPPED}


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
