"""Institution-wide primary/fallback routing with an append-only history (M5).

FR-MDL-021, FR-MDL-012, FR-MDL-030 (use gate), RULE-MDL-01/02; decisions D5, D8, D9,
D13 (see MDL_OPEN_DECISIONS, M5 decision record).

Two separate questions (D9):

- **Route persistence**: the configured primary/fallback changes only through
  ``PUT /routing`` by an MDL administrator, each change writing one immutable revision
  row and one audit event in the same transaction. Nothing changes it automatically, so
  the history always shows what was decided, by whom and when.
- **Permission to use** a configured slot is evaluated on every read with the same
  eligibility rules as a new selection (``queries.routing_issues``). A failed or
  outdated retest, a withdrawn agreement (D5), a lost key or a policy change makes the
  slot unusable at once (fail closed) without rewriting history; ``effective`` then
  names the fallback if that is usable, or nothing.

Lock order (architecture section 7): institution shared lock and account lock (shared
write path) → routing advisory lock and row → provider rows by ID (shared) → model rows
by ID (shared). No network I/O happens here.
"""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.authorization.writes import WriteContext, protected, record
from aq_uai_api.core.config import Settings
from aq_uai_api.db import audit
from aq_uai_api.directory.queries import page
from aq_uai_api.directory.schemas import Page, PageParams
from aq_uai_api.mdl import egress, queries, schemas, usage
from aq_uai_api.mdl.credentials import KeyRing
from aq_uai_api.mdl.models import MdlModel, MdlProvider, MdlRouting, MdlRoutingRevision

SLOTS = ("primary", "fallback")


def _slot_out(
    db: Session, model_id: UUID | None, keys: KeyRing | None, policy: egress.EgressPolicy
) -> schemas.RoutingSlotOut | None:
    if model_id is None:
        return None
    model = db.get(MdlModel, model_id)
    provider = db.get(MdlProvider, model.provider_id)
    issues = queries.routing_issues(db, model, keys, policy)
    return schemas.RoutingSlotOut(
        model_id=model.id,
        display_name=model.display_name,
        provider_id=provider.id,
        provider_name=provider.name,
        usable=not issues,
        issues=issues,
    )


def routing_out(db: Session, routing: MdlRouting | None, settings: Settings) -> schemas.RoutingOut:
    keys, policy = queries.key_ring_or_none(settings), queries.egress_policy(settings)
    primary = _slot_out(db, routing.primary_model_id if routing else None, keys, policy)
    fallback = _slot_out(db, routing.fallback_model_id if routing else None, keys, policy)
    if primary is None:
        effective = schemas.EffectiveRoute(state="NOT_CONFIGURED", model_id=None)
    elif primary.usable:
        effective = schemas.EffectiveRoute(state="PRIMARY", model_id=primary.model_id)
    elif fallback is not None and fallback.usable:
        effective = schemas.EffectiveRoute(state="FALLBACK", model_id=fallback.model_id)
    else:
        effective = schemas.EffectiveRoute(state="UNAVAILABLE", model_id=None)
    return schemas.RoutingOut(
        revision=routing.revision if routing else 0,
        primary=primary,
        fallback=fallback,
        effective=effective,
        updated_by=routing.updated_by if routing else None,
        updated_at=routing.updated_at if routing else None,
    )


def effective_model_id(db: Session, institution_id: UUID, settings: Settings) -> UUID | None:
    """The one entry point a future AI gateway must use: fail closed, no side effects."""
    routing = db.get(MdlRouting, institution_id)
    return routing_out(db, routing, settings).effective.model_id


def get_routing(db: Session, authority: ActorAuthority, settings: Settings) -> schemas.RoutingOut:
    tenant = queries.reader(authority)
    return routing_out(db, db.get(MdlRouting, tenant), settings)


def revisions(
    db: Session, authority: ActorAuthority, params: PageParams
) -> Page[schemas.RoutingRevisionOut]:
    tenant = queries.reader(authority)
    statement = (
        sa.select(MdlRoutingRevision)
        .where(MdlRoutingRevision.institution_id == tenant)
        .order_by(MdlRoutingRevision.revision.desc())
    )
    return page(db, statement, params, schemas.RoutingRevisionOut.model_validate)


def _lock_models(db: Session, tenant: UUID, model_ids: set[UUID]) -> dict[UUID, MdlModel]:
    """Providers then models, each ordered by ID and locked FOR SHARE (blocks concurrent
    deactivation, edits, credential rotation and test completion until commit)."""
    found = {
        model.id: model
        for model in db.scalars(queries.model_query(tenant).where(MdlModel.id.in_(model_ids)))
    }
    if len(found) != len(model_ids):
        raise DomainError(ErrorCode.NOT_FOUND)
    provider_ids = sorted({model.provider_id for model in found.values()})
    db.scalars(
        queries.provider_query(tenant)
        .where(MdlProvider.id.in_(provider_ids))
        .order_by(MdlProvider.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).all()
    locked = db.scalars(
        queries.model_query(tenant)
        .where(MdlModel.id.in_(sorted(model_ids)))
        .order_by(MdlModel.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).all()
    return {model.id: model for model in locked}


def update_routing(context: WriteContext, payload: schemas.RoutingIn) -> schemas.RoutingOut:
    with protected(context, changes_authority=False) as (db, authority):
        authority.require_institution(P.MDL_MANAGE, authority.institution_id)
        tenant = authority.institution_id
        routing = usage.lock_routing(db, tenant)
        current = routing.revision if routing else 0
        if payload.expected_revision != current:
            raise DomainError(ErrorCode.MDL_ROUTING_CONFLICT)
        before = {
            "primary": routing.primary_model_id if routing else None,
            "fallback": routing.fallback_model_id if routing else None,
        }
        after = {"primary": payload.primary_model_id, "fallback": payload.fallback_model_id}
        if after["fallback"] is not None and after["fallback"] == after["primary"]:
            raise DomainError(ErrorCode.MDL_FALLBACK_EQUALS_PRIMARY)
        if after == before:
            return routing_out(db, routing, context.settings)  # no-op: no revision

        involved = {value for value in (*before.values(), *after.values()) if value}
        models = _lock_models(db, tenant, involved)
        keys = queries.key_ring_or_none(context.settings)
        policy = queries.egress_policy(context.settings)
        reasons = []
        for slot in SLOTS:
            # Only a new value in a slot is validated; an unchanged slot persists (D9).
            if after[slot] is not None and after[slot] != before[slot]:
                issues = queries.routing_issues(db, models[after[slot]], keys, policy)
                reasons += [f"{slot}.{issue}" for issue in issues]
        if reasons:
            raise DomainError(ErrorCode.MDL_NOT_ELIGIBLE, {"reasons": reasons})

        revision = current + 1
        if routing is None:
            db.execute(
                sa.insert(MdlRouting).values(
                    institution_id=tenant,
                    primary_model_id=after["primary"],
                    fallback_model_id=after["fallback"],
                    revision=revision,
                    updated_by=authority.actor_id,
                )
            )
        else:
            db.execute(
                sa.update(MdlRouting)
                .where(MdlRouting.institution_id == tenant, MdlRouting.revision == current)
                .values(
                    primary_model_id=after["primary"],
                    fallback_model_id=after["fallback"],
                    revision=revision,
                    updated_by=authority.actor_id,
                    updated_at=sa.func.now(),
                )
            )

        def name(model_id: UUID | None) -> str | None:
            return models[model_id].display_name if model_id else None

        revision_id = db.execute(
            sa.insert(MdlRoutingRevision)
            .values(
                institution_id=tenant,
                revision=revision,
                before_primary_model_id=before["primary"],
                before_fallback_model_id=before["fallback"],
                after_primary_model_id=after["primary"],
                after_fallback_model_id=after["fallback"],
                before_primary_name=name(before["primary"]),
                before_fallback_name=name(before["fallback"]),
                after_primary_name=name(after["primary"]),
                after_fallback_name=name(after["fallback"]),
                decision_reference=payload.decision_reference,
                changed_by=authority.actor_id,
            )
            .returning(MdlRoutingRevision.id)
        ).scalar_one()
        record(
            db,
            context,
            authority,
            audit.AuditAction.MDL_ROUTING_CHANGED,
            revision_id,
            audit.RoutingChanged(
                revision=revision,
                before=audit.RoutingSlots(
                    primary_model_id=before["primary"], fallback_model_id=before["fallback"]
                ),
                after=audit.RoutingSlots(
                    primary_model_id=after["primary"], fallback_model_id=after["fallback"]
                ),
                decision_reference=payload.decision_reference,
            ),
        )
        db.flush()
        return routing_out(db, usage.current_routing(db, tenant), context.settings)

