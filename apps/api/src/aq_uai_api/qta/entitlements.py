"""Single source of truth for usable models, additive entitlements & institutional allocation (Q3–Q4).

Implements architecture §2.1, PO decisions PD-Q1 & PD-Q5, and carry-over fixes C1 & C2:
- Usable model M_usable(I) (R6 / C1): ``mdl_models.active=true AND mdl_providers.active=true``
  joined on ``(institution_id, provider_id)``.
- Qualifying groups G(u): enrolled in ``qta_quota_groups`` with ``in_directory=true``,
  ``account_groups.active=true``, and an active ``group_memberships`` row for ``u``.
- Single base selectable ``_qualifying_quota_rows`` (C2): shared by ``compute_user_entitlements``,
  ``allocated_for_month``, and ``user_model_base_entitlement`` (used by ``check_ai_access``).
- Individual base entitlement E_base(u, m) = SUM over G(u) of q(g, m) (additive; NEVER MAX).
- Users with ``User.state != 'ACTIVE'`` have E_base = 0 across all models and contribute 0
  to institutional allocation.
- Consumption is never fabricated (``actual_consumption`` and ``remaining_quota`` are always
  ``null`` with ``consumption_status = "NOT_INTEGRATED"``).
"""

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.db.identity import AccountGroup, GroupMembership, User
from aq_uai_api.mdl.models import MdlModel, MdlProvider
from aq_uai_api.qta import schemas
from aq_uai_api.qta.models import QtaGroupModelQuota, QtaQuotaGroup


@dataclass(frozen=True)
class ComputedEntitlements:
    quota_status: schemas.QuotaStatus
    suspension: schemas.SuspensionOut | None
    memberships: list[schemas.UserGroupMembershipOut]
    models: list[schemas.ModelEntitlementOut]
    base_entitlement_total: int


def usable_model_predicate() -> sa.ColumnElement[bool]:
    """R6 / C1: a model is usable in QTA iff both the model and its provider are active."""
    return sa.and_(MdlModel.active.is_(True), MdlProvider.active.is_(True))


def usable_models_query(institution_id: UUID) -> sa.Select[tuple[MdlModel, MdlProvider]]:
    """Select usable ``(MdlModel, MdlProvider)`` pairs in one institution."""
    return (
        sa.select(MdlModel, MdlProvider)
        .join(
            MdlProvider,
            sa.and_(
                MdlProvider.id == MdlModel.provider_id,
                MdlProvider.institution_id == MdlModel.institution_id,
            ),
        )
        .where(
            MdlModel.institution_id == institution_id,
            usable_model_predicate(),
        )
    )


def _qualifying_quota_rows(
    institution_id: UUID,
    *,
    user_id: UUID | None = None,
    model_id: UUID | None = None,
) -> sa.Subquery:
    """Single source of truth for qualifying ``(user, group, model)`` quota rows (C1, C2).

    Each row represents one active user's active membership in an enrolled, in-directory,
    active group with an enabled quota rule on a usable MDL model (model and provider active).
    Unique keys on ``group_memberships(group_id, user_id)`` and
    ``qta_group_model_quotas(institution_id, group_id, model_id)`` guarantee zero fan-out.
    """
    stmt = (
        sa.select(
            GroupMembership.user_id.label("user_id"),
            QtaGroupModelQuota.group_id.label("group_id"),
            QtaGroupModelQuota.model_id.label("model_id"),
            QtaGroupModelQuota.monthly_limit.label("monthly_limit"),
        )
        .select_from(GroupMembership)
        .join(
            User,
            sa.and_(
                User.id == GroupMembership.user_id,
                User.institution_id == GroupMembership.institution_id,
            ),
        )
        .join(
            QtaQuotaGroup,
            sa.and_(
                QtaQuotaGroup.group_id == GroupMembership.group_id,
                QtaQuotaGroup.institution_id == GroupMembership.institution_id,
            ),
        )
        .join(
            AccountGroup,
            sa.and_(
                AccountGroup.id == QtaQuotaGroup.group_id,
                AccountGroup.institution_id == QtaQuotaGroup.institution_id,
                AccountGroup.kind == QtaQuotaGroup.group_kind,
            ),
        )
        .join(
            QtaGroupModelQuota,
            sa.and_(
                QtaGroupModelQuota.group_id == QtaQuotaGroup.group_id,
                QtaGroupModelQuota.institution_id == QtaQuotaGroup.institution_id,
            ),
        )
        .join(
            MdlModel,
            sa.and_(
                MdlModel.id == QtaGroupModelQuota.model_id,
                MdlModel.institution_id == QtaGroupModelQuota.institution_id,
            ),
        )
        .join(
            MdlProvider,
            sa.and_(
                MdlProvider.id == MdlModel.provider_id,
                MdlProvider.institution_id == MdlModel.institution_id,
            ),
        )
        .where(
            GroupMembership.institution_id == institution_id,
            GroupMembership.active.is_(True),
            User.state == "ACTIVE",
            QtaQuotaGroup.in_directory.is_(True),
            AccountGroup.active.is_(True),
            QtaGroupModelQuota.enabled.is_(True),
            usable_model_predicate(),
        )
    )
    if user_id is not None:
        stmt = stmt.where(GroupMembership.user_id == user_id)
    if model_id is not None:
        stmt = stmt.where(QtaGroupModelQuota.model_id == model_id)
    return stmt.subquery("qualifying_quota_rows")


def user_model_base_entitlement(
    db: Session, institution_id: UUID, user_id: UUID, model_id: UUID
) -> int:
    """Compute live additive base entitlement for one ``(user, model)`` pair (used by R5 step 6)."""
    qualifying = _qualifying_quota_rows(institution_id, user_id=user_id, model_id=model_id)
    total = db.scalar(sa.select(sa.func.coalesce(sa.func.sum(qualifying.c.monthly_limit), 0)))
    return int(total or 0)


def _excluded_reason(
    user_state: str, group: AccountGroup, registry: QtaQuotaGroup | None
) -> schemas.ExclusionReason | None:
    if user_state != "ACTIVE":
        return "USER_NOT_ACTIVE"
    if registry is None:
        return "NOT_ENROLLED"
    if not registry.in_directory:
        return "RETIRED"
    if not group.active:
        return "GROUP_INACTIVE"
    return None


def compute_user_entitlements(
    db: Session, institution_id: UUID, user_id: UUID
) -> ComputedEntitlements:
    """Compute live additive per-model base entitlements, suspension & access for one user."""
    from aq_uai_api.qta import access

    user_state = db.scalar(
        sa.select(User.state).where(User.institution_id == institution_id, User.id == user_id)
    )
    if user_state is None:
        from aq_uai_api.api.errors import DomainError, ErrorCode

        raise DomainError(ErrorCode.NOT_FOUND)

    active_susp = access.active_suspension_for_user(db, institution_id, user_id)
    suspension_projection = (
        access.suspension_out(active_susp, None) if active_susp is not None else None
    )
    quota_status: schemas.QuotaStatus = "SUSPENDED" if active_susp is not None else "ACTIVE"

    membership_rows = db.execute(
        sa.select(AccountGroup, QtaQuotaGroup)
        .select_from(GroupMembership)
        .join(
            AccountGroup,
            sa.and_(
                AccountGroup.id == GroupMembership.group_id,
                AccountGroup.institution_id == GroupMembership.institution_id,
            ),
        )
        .outerjoin(
            QtaQuotaGroup,
            sa.and_(
                QtaQuotaGroup.group_id == AccountGroup.id,
                QtaQuotaGroup.institution_id == AccountGroup.institution_id,
                QtaQuotaGroup.group_kind == AccountGroup.kind,
            ),
        )
        .where(
            GroupMembership.institution_id == institution_id,
            GroupMembership.user_id == user_id,
            GroupMembership.active.is_(True),
            AccountGroup.kind.in_(("SYSTEM", "AI_SPECIALIST")),
        )
        .order_by(AccountGroup.code, AccountGroup.id)
    ).all()

    memberships: list[schemas.UserGroupMembershipOut] = []
    qualifying_group_ids: list[UUID] = []
    for group, registry in membership_rows:
        reason = _excluded_reason(user_state, group, registry)
        qualifies = reason is None
        if qualifies:
            qualifying_group_ids.append(group.id)
        memberships.append(
            schemas.UserGroupMembershipOut(
                group_id=group.id,
                code=group.code,
                name=group.name,
                kind=group.kind,
                origin=registry.origin if registry is not None else None,
                active=group.active,
                in_directory=registry.in_directory if registry is not None else None,
                qualifies=qualifies,
                excluded_reason=reason,
            )
        )

    usable_models = db.execute(
        usable_models_query(institution_id).order_by(
            sa.func.lower(MdlModel.display_name), MdlModel.id
        )
    ).all()

    # Single SQL aggregate built from _qualifying_quota_rows (RULE-QTA-02: SUM, never MAX).
    totals_by_model: dict[UUID, int] = {}
    if usable_models:
        qualifying = _qualifying_quota_rows(institution_id, user_id=user_id)
        agg_rows = db.execute(
            sa.select(
                qualifying.c.model_id,
                sa.func.coalesce(sa.func.sum(qualifying.c.monthly_limit), 0),
            ).group_by(qualifying.c.model_id)
        ).all()
        totals_by_model = {model_id: int(total or 0) for model_id, total in agg_rows}

    contributions_by_model: dict[UUID, list[schemas.GroupContributionOut]] = defaultdict(list)
    if qualifying_group_ids and usable_models:
        usable_model_ids = [model.id for model, _ in usable_models]
        contrib_rows = db.execute(
            sa.select(QtaGroupModelQuota, AccountGroup, QtaQuotaGroup)
            .join(
                QtaQuotaGroup,
                sa.and_(
                    QtaQuotaGroup.group_id == QtaGroupModelQuota.group_id,
                    QtaQuotaGroup.institution_id == QtaGroupModelQuota.institution_id,
                ),
            )
            .join(
                AccountGroup,
                sa.and_(
                    AccountGroup.id == QtaQuotaGroup.group_id,
                    AccountGroup.institution_id == QtaQuotaGroup.institution_id,
                    AccountGroup.kind == QtaQuotaGroup.group_kind,
                ),
            )
            .where(
                QtaGroupModelQuota.institution_id == institution_id,
                QtaGroupModelQuota.group_id.in_(qualifying_group_ids),
                QtaGroupModelQuota.model_id.in_(usable_model_ids),
            )
            .order_by(AccountGroup.code, AccountGroup.id)
        ).all()
        for quota, group, registry in contrib_rows:
            contributes = quota.monthly_limit if (quota.enabled and quota.monthly_limit > 0) else 0
            contributions_by_model[quota.model_id].append(
                schemas.GroupContributionOut(
                    group_id=group.id,
                    code=group.code,
                    name=group.name,
                    kind=group.kind,
                    origin=registry.origin,
                    enabled=quota.enabled,
                    monthly_limit=quota.monthly_limit,
                    contributes=contributes,
                )
            )

    model_items: list[schemas.ModelEntitlementOut] = []
    grand_total = 0
    for model, provider in usable_models:
        base_entitlement = totals_by_model.get(model.id, 0)
        grand_total += base_entitlement
        decision = access.evaluate_access_rule(
            user_exists=True,
            user_state=user_state,
            model_usable=True,
            provider_type=provider.provider_type,
            active_suspension=active_susp,
            base_entitlement=base_entitlement,
        )
        model_items.append(
            schemas.ModelEntitlementOut(
                model_id=model.id,
                display_name=model.display_name,
                technical_id=model.technical_id,
                provider_type=provider.provider_type,
                base_entitlement=base_entitlement,
                contributions=contributions_by_model.get(model.id, []),
                access=schemas.ModelAccessOut(
                    allowed=decision.allowed,
                    reason=decision.reason,
                ),
            )
        )

    return ComputedEntitlements(
        quota_status=quota_status,
        suspension=suspension_projection,
        memberships=memberships,
        models=model_items,
        base_entitlement_total=grand_total,
    )


def allocated_for_month(db: Session, institution_id: UUID) -> int:
    """Compute live institutional monthly allocation in one SQL aggregate (PD-Q1, C1, C2).

    Sums ``monthly_limit`` from ``_qualifying_quota_rows(institution_id)`` across every
    ``ACTIVE`` user, active membership, enrolled active group, enabled quota row, and
    usable MDL model (model and provider active) — expressed in ``đơn vị hạn mức``.

    Phase 5 CRT net grants will join through this function so FR-QTA-011 protects both
    group base entitlements and ad-hoc individual grants in one place.
    """
    qualifying = _qualifying_quota_rows(institution_id)
    total = db.scalar(sa.select(sa.func.coalesce(sa.func.sum(qualifying.c.monthly_limit), 0)))
    return int(total or 0)
