"""Individual kill-switch state and fail-closed AI access decision table (Phase 4, Stage Q4).

Implements FR-QTA-040, FR-QTA-041, RULE-QTA-03, PD-Q2, PD-Q3, and reviewer decisions R5, R6, R9:
- Lazy expiry: a suspension is ACTIVE at time ``t`` iff it has no restoration row AND
  ``(expires_at IS NULL OR expires_at > t)``. Nothing is written when a suspension expires.
- ``periods.utc_now()`` is the single clock used across QTA so tests can freeze time cleanly.
- Set-based ``active_suspensions_for`` loads active suspensions for any batch of users in one
  SQL query (zero N+1).
- ``check_ai_access`` is pure read-only, fail-closed, and uses one ordered decision table.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.db.identity import User
from aq_uai_api.mdl.models import MdlModel
from aq_uai_api.qta import entitlements, periods, schemas
from aq_uai_api.qta.models import QtaSuspension, QtaSuspensionRestoration

QTA_SUSPENSION_NAMESPACE = 52002


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: schemas.AccessReasonCode | None
    suspension_id: UUID | None = None


def suspension_status(
    suspension: QtaSuspension,
    restoration: QtaSuspensionRestoration | None,
    *,
    now: datetime | None = None,
) -> schemas.SuspensionStatus:
    """Compute suspension lifecycle state at ``now`` (lazy expiry; zero DB writes)."""
    if restoration is not None:
        return "RESTORED"
    at = periods.utc_now() if now is None else now
    if suspension.expires_at is None or suspension.expires_at > at:
        return "ACTIVE"
    return "EXPIRED"


def suspension_out(
    suspension: QtaSuspension,
    restoration: QtaSuspensionRestoration | None = None,
    *,
    now: datetime | None = None,
) -> schemas.SuspensionOut:
    return schemas.SuspensionOut(
        id=suspension.id,
        user_id=suspension.user_id,
        scope=suspension.scope,
        reason=suspension.reason,
        ordered_by=suspension.ordered_by,
        expires_at=suspension.expires_at,
        suspended_by=suspension.suspended_by,
        suspended_at=suspension.suspended_at,
        status=suspension_status(suspension, restoration, now=now),
        restoration=(
            schemas.SuspensionRestorationOut.model_validate(restoration)
            if restoration is not None
            else None
        ),
    )


def active_suspensions_for(
    db: Session,
    institution_id: UUID,
    user_ids: Collection[UUID],
    *,
    now: datetime | None = None,
) -> dict[UUID, QtaSuspension]:
    """Return ``{user_id: active QtaSuspension}`` in one SQL query (zero N+1)."""
    ids = list(user_ids)
    if not ids:
        return {}
    at = periods.utc_now() if now is None else now
    rows = db.scalars(
        sa.select(QtaSuspension)
        .outerjoin(
            QtaSuspensionRestoration,
            sa.and_(
                QtaSuspensionRestoration.suspension_id == QtaSuspension.id,
                QtaSuspensionRestoration.institution_id == QtaSuspension.institution_id,
            ),
        )
        .where(
            QtaSuspension.institution_id == institution_id,
            QtaSuspension.user_id.in_(ids),
            QtaSuspensionRestoration.suspension_id.is_(None),
            sa.or_(QtaSuspension.expires_at.is_(None), QtaSuspension.expires_at > at),
        )
        .order_by(QtaSuspension.suspended_at.desc(), QtaSuspension.id.desc())
    ).all()
    active: dict[UUID, QtaSuspension] = {}
    for row in rows:
        active.setdefault(row.user_id, row)
    return active


def active_suspension_for_user(
    db: Session,
    institution_id: UUID,
    user_id: UUID,
    *,
    now: datetime | None = None,
) -> QtaSuspension | None:
    return active_suspensions_for(db, institution_id, (user_id,), now=now).get(user_id)


def evaluate_access_rule(
    *,
    user_exists: bool,
    user_state: str | None,
    model_usable: bool,
    provider_type: str | None,
    active_suspension: QtaSuspension | None,
    base_entitlement: int,
) -> AccessDecision:
    """Single ordered fail-closed decision table (R5, R9, RULE-QTA-03, PD-Q2)."""
    if not user_exists:
        return AccessDecision(allowed=False, reason="USER_NOT_FOUND", suspension_id=None)
    if user_state != "ACTIVE":
        return AccessDecision(allowed=False, reason="USER_NOT_ACTIVE", suspension_id=None)
    if not model_usable:
        return AccessDecision(allowed=False, reason="MODEL_UNAVAILABLE", suspension_id=None)
    if active_suspension is not None:
        if active_suspension.scope == "ALL_MODELS":
            return AccessDecision(
                allowed=False,
                reason="SUSPENDED_ALL_MODELS",
                suspension_id=active_suspension.id,
            )
        if active_suspension.scope == "PAID_EXTERNAL_ONLY" and provider_type == "EXTERNAL":
            return AccessDecision(
                allowed=False,
                reason="SUSPENDED_PAID_EXTERNAL",
                suspension_id=active_suspension.id,
            )
    if base_entitlement <= 0:
        return AccessDecision(allowed=False, reason="NO_ENTITLEMENT", suspension_id=None)
    return AccessDecision(allowed=True, reason=None, suspension_id=None)


def check_ai_access(
    db: Session, institution_id: UUID, user_id: UUID, model_id: UUID
) -> AccessDecision:
    """Evaluate whether ``user_id`` may invoke ``model_id`` in ``institution_id`` (fail closed).

    Pure read-only evaluation with zero database writes or side effects. Ordered table (R5):
      1. ``USER_NOT_FOUND``          — user missing or belongs to another institution
      2. ``USER_NOT_ACTIVE``         — ``User.state != 'ACTIVE'``
      3. ``MODEL_UNAVAILABLE``       — model missing, other institution, or model/provider inactive (C1)
      4. ``SUSPENDED_ALL_MODELS``    — active suspension with ``scope == 'ALL_MODELS'``
      5. ``SUSPENDED_PAID_EXTERNAL`` — active ``PAID_EXTERNAL_ONLY`` suspension and ``EXTERNAL`` provider
      6. ``NO_ENTITLEMENT``          — live additive base entitlement for ``(user, model)`` is ``0``
      7. ``ALLOWED``                 — access permitted

    Gateway integration contract: a future AI invocation gateway must call BOTH
    ``aq_uai_api.mdl.routing.effective_model_id`` (to determine which model is eligible to serve)
    and ``check_ai_access`` (to verify that this user is allowed to use that model). Actual
    consumption is not checked while ``consumption_status`` is ``"NOT_INTEGRATED"``.
    """
    user_state = db.scalar(
        sa.select(User.state).where(User.institution_id == institution_id, User.id == user_id)
    )
    if user_state is None:
        return evaluate_access_rule(
            user_exists=False,
            user_state=None,
            model_usable=False,
            provider_type=None,
            active_suspension=None,
            base_entitlement=0,
        )
    if user_state != "ACTIVE":
        return evaluate_access_rule(
            user_exists=True,
            user_state=user_state,
            model_usable=False,
            provider_type=None,
            active_suspension=None,
            base_entitlement=0,
        )

    usable_pair = db.execute(
        entitlements.usable_models_query(institution_id).where(MdlModel.id == model_id)
    ).one_or_none()
    if usable_pair is None:
        return evaluate_access_rule(
            user_exists=True,
            user_state=user_state,
            model_usable=False,
            provider_type=None,
            active_suspension=None,
            base_entitlement=0,
        )
    _, provider = usable_pair

    active_susp = active_suspension_for_user(db, institution_id, user_id)
    base = entitlements.user_model_base_entitlement(db, institution_id, user_id, model_id)
    return evaluate_access_rule(
        user_exists=True,
        user_state=user_state,
        model_usable=True,
        provider_type=provider.provider_type,
        active_suspension=active_susp,
        base_entitlement=base,
    )
