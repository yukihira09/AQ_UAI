"""Where-used registry seam (FR-MDL-012, D10).

Answers "where is this model used?" with short, fixed identifiers that may be sent to
clients through ``DomainError(details={"used_in": [...]})``. Today only routing can use
a model; QTA/CRT register their own checks when they exist (no stub now).

Lock order (architecture section 7): call ``lock_routing`` before locking provider or
model rows, so a deactivation and a routing change (M5) serialize on the routing row.
"""

from collections.abc import Collection
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.auth.service import database_lock
from aq_uai_api.authorization.writes import institution_key
from aq_uai_api.mdl.models import MdlModel, MdlRouting

ROUTING_NAMESPACE = 51001


def lock_routing(db: Session, institution_id: UUID) -> MdlRouting | None:
    """Serialize every routing-sensitive write of one institution.

    The advisory lock also covers the case where no routing row exists yet (first
    configuration), which a row lock alone cannot; the row lock then protects updates.
    """
    database_lock(db, ROUTING_NAMESPACE, institution_key(institution_id))
    return db.scalar(
        sa.select(MdlRouting)
        .where(MdlRouting.institution_id == institution_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _routing_usage(routing: MdlRouting | None, model_ids: Collection[UUID]) -> list[str]:
    if routing is None:
        return []
    used = []
    if routing.primary_model_id in model_ids:
        used.append("routing.primary")
    if routing.fallback_model_id in model_ids:
        used.append("routing.fallback")
    return used


def models_used_in(routing: MdlRouting | None, model_ids: Collection[UUID]) -> list[str]:
    return _routing_usage(routing, set(model_ids))


def provider_used_in(db: Session, routing: MdlRouting | None, provider_id: UUID) -> list[str]:
    model_ids = db.scalars(sa.select(MdlModel.id).where(MdlModel.provider_id == provider_id))
    return models_used_in(routing, set(model_ids))


def current_routing(db: Session, institution_id: UUID) -> MdlRouting | None:
    """Re-read the routing row inside the caller's transaction (after a write)."""
    return db.scalar(
        sa.select(MdlRouting)
        .where(MdlRouting.institution_id == institution_id)
        .execution_options(populate_existing=True)
    )
