"""Configuration history with before/after values (M7, FRD §6 "Should").

What: ``GET /api/v1/mdl/history`` lists the institution's MDL *configuration* events
(providers, credentials rotated, agreements, models, risk, state, routing, key rewrap),
newest first, each with the before/after values that were audited in the same
transaction as the change. The admin UI renders them as a field-by-field comparison.

Why here and not in the shared audit viewer: the audit viewer needs ``audit.read``,
which an MDL administrator does not hold; this view needs only ``mdl.read`` and only
ever shows ``mdl.*`` configuration events of the caller's own institution.

Safety: payloads go through ``public_audit_changes`` (the action's approved typed
schema), so a field that is not on the allowlist is never returned. Connection-test
events are excluded because each model already has its own test history.
"""

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.db.audit import AuditAction, public_audit_changes
from aq_uai_api.db.identity import AuditEvent
from aq_uai_api.directory.queries import page
from aq_uai_api.directory.schemas import Page
from aq_uai_api.mdl import queries, schemas

CONFIGURATION_ACTIONS = tuple(
    action.value
    for action in AuditAction
    if action.value.startswith("mdl.") and action is not AuditAction.MDL_MODEL_CONNECTION_TESTED
)


def event_out(event: AuditEvent) -> schemas.ConfigurationEventOut:
    return schemas.ConfigurationEventOut(
        id=event.id,
        action=event.action,
        target_type=event.target_type,
        target_id=event.target_id,
        actor_id=event.actor_id,
        occurred_at=event.occurred_at,
        changes=public_audit_changes(event),
    )


def history(
    db: Session, authority: ActorAuthority, params: schemas.HistoryFilters
) -> Page[schemas.ConfigurationEventOut]:
    tenant = queries.reader(authority)
    statement = sa.select(AuditEvent).where(
        AuditEvent.institution_id == tenant,
        AuditEvent.action.in_(CONFIGURATION_ACTIONS),
    )
    if params.target_type is not None:
        statement = statement.where(AuditEvent.target_type == params.target_type)
    if params.target_id is not None:
        statement = statement.where(AuditEvent.target_id == params.target_id)
    statement = statement.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
    return page(db, statement, params, event_out)
