"""Read-side QTA queries and projections (Phase 4, Stages Q2–Q4).

Group/model/budget/event/reset routes require GLOBAL ``qta.read``; user lookup and user
suspension history routes accept GLOBAL or exact-UNIT ``qta.read`` scoped via
``scope.predicate(User.institution_id, User.primary_unit_id)``.
Reads MDL tables (``mdl_models``, ``mdl_providers``) read-only; ``mdl/`` never imports ``qta/``.
"""

from collections import defaultdict
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.core.config import Settings
from aq_uai_api.db.identity import AccountGroup, GroupMembership, User
from aq_uai_api.directory import queries as dir_queries
from aq_uai_api.directory import schemas as dir_schemas
from aq_uai_api.directory.queries import one, page
from aq_uai_api.directory.schemas import Page, PageParams, SearchParams
from aq_uai_api.mdl.models import MdlModel, MdlProvider
from aq_uai_api.qta import access, entitlements, periods, schemas
from aq_uai_api.qta.models import (
    QtaBudgetRevision,
    QtaEvent,
    QtaGroupModelQuota,
    QtaGroupSyncRun,
    QtaMonthlyReset,
    QtaQuotaGroup,
    QtaSuspension,
    QtaSuspensionRestoration,
)


def reader(authority: ActorAuthority) -> UUID:
    authority.require_institution(P.QTA_READ, authority.institution_id)
    return authority.institution_id


def _capabilities(model: MdlModel) -> list[schemas.Capability]:
    return [
        code
        for code, enabled in (
            ("TEXT", model.supports_text),
            ("IMAGE", model.supports_image),
            ("VOICE", model.supports_voice),
        )
        if enabled
    ]


def _model_out(model: MdlModel, provider: MdlProvider) -> schemas.QtaModelOut:
    return schemas.QtaModelOut(
        id=model.id,
        institution_id=model.institution_id,
        provider_id=provider.id,
        provider_name=provider.name,
        provider_type=provider.provider_type,
        technical_id=model.technical_id,
        display_name=model.display_name,
        capabilities=_capabilities(model),
        risk_level=model.risk_level,
        active=bool(model.active and provider.active),
    )


def models(
    db: Session, authority: ActorAuthority, params: SearchParams
) -> Page[schemas.QtaModelOut]:
    tenant = reader(authority)
    statement = entitlements.usable_models_query(tenant)
    if params.q:
        statement = statement.where(
            sa.or_(
                MdlModel.display_name.icontains(params.q, autoescape=True),
                MdlModel.technical_id.icontains(params.q, autoescape=True),
                MdlProvider.name.icontains(params.q, autoescape=True),
            )
        )
    return page(
        db,
        statement.order_by(sa.func.lower(MdlModel.display_name), MdlModel.id),
        params,
        _model_out,
    )


def _active_member_counts(
    db: Session, tenant: UUID, group_ids: list[UUID]
) -> dict[UUID, int]:
    """Live count of ACTIVE users with active memberships for each listed group."""
    if not group_ids:
        return {}
    rows = db.execute(
        sa.select(GroupMembership.group_id, sa.func.count(GroupMembership.user_id))
        .join(
            User,
            sa.and_(
                User.id == GroupMembership.user_id,
                User.institution_id == GroupMembership.institution_id,
            ),
        )
        .where(
            GroupMembership.institution_id == tenant,
            GroupMembership.group_id.in_(group_ids),
            GroupMembership.active.is_(True),
            User.state == "ACTIVE",
        )
        .group_by(GroupMembership.group_id)
    ).all()
    return {group_id: int(count) for group_id, count in rows}


def _quotas_by_group(
    db: Session, tenant: UUID, group_ids: list[UUID]
) -> dict[UUID, list[schemas.GroupQuotaRuleOut]]:
    if not group_ids:
        return {}
    rows = db.execute(
        sa.select(QtaGroupModelQuota, MdlModel, MdlProvider, entitlements.usable_model_predicate())
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
            QtaGroupModelQuota.institution_id == tenant,
            QtaGroupModelQuota.group_id.in_(group_ids),
        )
        .order_by(sa.func.lower(MdlModel.display_name), MdlModel.id)
    ).all()
    grouped: dict[UUID, list[schemas.GroupQuotaRuleOut]] = defaultdict(list)
    for quota, model, provider, usable in rows:
        grouped[quota.group_id].append(
            schemas.GroupQuotaRuleOut(
                id=quota.id,
                model_id=model.id,
                model_technical_id=model.technical_id,
                model_display_name=model.display_name,
                model_active=bool(usable),
                provider_name=provider.name,
                provider_type=provider.provider_type,
                enabled=quota.enabled,
                monthly_limit=quota.monthly_limit,
                warning_threshold_pct=quota.warning_threshold_pct,
                updated_by=quota.updated_by,
                updated_at=quota.updated_at,
            )
        )
    return grouped


def _enrolled_groups_query(tenant: UUID):
    return (
        sa.select(QtaQuotaGroup, AccountGroup)
        .join(
            AccountGroup,
            sa.and_(
                AccountGroup.id == QtaQuotaGroup.group_id,
                AccountGroup.institution_id == QtaQuotaGroup.institution_id,
                AccountGroup.kind == QtaQuotaGroup.group_kind,
            ),
        )
        .where(QtaQuotaGroup.institution_id == tenant)
    )


def _project_groups(
    db: Session, tenant: UUID, pairs: list[tuple[QtaQuotaGroup, AccountGroup]]
) -> list[schemas.QtaGroupOut]:
    ids = [group.id for _, group in pairs]
    counts = _active_member_counts(db, tenant, ids)
    quotas = _quotas_by_group(db, tenant, ids)
    return [
        schemas.QtaGroupOut(
            id=group.id,
            institution_id=group.institution_id,
            code=group.code,
            name=group.name,
            kind=group.kind,
            origin=reg.origin,
            active=group.active,
            in_directory=reg.in_directory,
            enrolled_by=reg.enrolled_by,
            enrolled_at=reg.enrolled_at,
            last_synced_at=reg.last_synced_at,
            active_member_count=counts.get(group.id, 0),
            quotas=quotas.get(group.id, []),
        )
        for reg, group in pairs
    ]


def groups(
    db: Session, authority: ActorAuthority, params: schemas.QtaGroupFilters
) -> Page[schemas.QtaGroupOut]:
    tenant = reader(authority)
    statement = _enrolled_groups_query(tenant)
    if params.q:
        statement = statement.where(
            sa.or_(
                AccountGroup.code.icontains(params.q, autoescape=True),
                AccountGroup.name.icontains(params.q, autoescape=True),
            )
        )
    if params.kind is not None:
        statement = statement.where(QtaQuotaGroup.group_kind == params.kind)
    if params.origin is not None:
        statement = statement.where(QtaQuotaGroup.origin == params.origin)
    if params.active is not None:
        statement = statement.where(AccountGroup.active == params.active)
    if params.in_directory is not None:
        statement = statement.where(QtaQuotaGroup.in_directory == params.in_directory)
    total = db.scalar(sa.select(sa.func.count()).select_from(statement.subquery()))
    ordered = statement.order_by(AccountGroup.code, AccountGroup.id)
    pairs = list(db.execute(ordered.offset(params.offset).limit(params.limit)).all())
    return Page(
        items=_project_groups(db, tenant, pairs),
        total=int(total or 0),
        limit=params.limit,
        offset=params.offset,
    )


def group_detail_for_tenant(db: Session, tenant: UUID, group_id: UUID) -> schemas.QtaGroupOut:
    row = db.execute(
        _enrolled_groups_query(tenant).where(QtaQuotaGroup.group_id == group_id)
    ).one_or_none()
    if row is None:
        raise DomainError(ErrorCode.NOT_FOUND)
    return _project_groups(db, tenant, [row])[0]


def group_detail(db: Session, authority: ActorAuthority, group_id: UUID) -> schemas.QtaGroupOut:
    tenant = reader(authority)
    return group_detail_for_tenant(db, tenant, group_id)


def group_members(
    db: Session,
    authority: ActorAuthority,
    group_id: UUID,
    params: dir_schemas.MemberFilters,
) -> Page[dir_schemas.MemberOut]:
    tenant = reader(authority)
    one(
        db,
        sa.select(QtaQuotaGroup.group_id).where(
            QtaQuotaGroup.institution_id == tenant,
            QtaQuotaGroup.group_id == group_id,
        ),
    )
    query = dir_queries.membership_query(tenant).where(GroupMembership.group_id == group_id)
    if params.active is not None:
        query = query.where(GroupMembership.active == params.active)
    if params.q:
        query = query.where(
            sa.or_(
                User.display_name.icontains(params.q, autoescape=True),
                User.username.icontains(params.q, autoescape=True),
                User.institutional_code.icontains(params.q, autoescape=True),
            )
        )
    return page(db, query.order_by(User.username, User.id), params, dir_queries.member_out)


def sync_runs(
    db: Session, authority: ActorAuthority, params: PageParams
) -> Page[schemas.SyncRunOut]:
    tenant = reader(authority)
    statement = (
        sa.select(QtaGroupSyncRun)
        .where(QtaGroupSyncRun.institution_id == tenant)
        .order_by(QtaGroupSyncRun.synced_at.desc(), QtaGroupSyncRun.id.desc())
    )
    return page(db, statement, params, schemas.SyncRunOut.model_validate)


def _scoped_user_query(authority: ActorAuthority):
    scope = authority.scope_for(P.QTA_READ)
    return sa.select(User).where(scope.predicate(User.institution_id, User.primary_unit_id))


def users(
    db: Session, authority: ActorAuthority, params: SearchParams
) -> Page[schemas.QtaUserOut]:
    """List users visible within the caller's GLOBAL or exact-UNIT qta.read scope (zero N+1)."""
    authority.require_permission(P.QTA_READ)
    query = _scoped_user_query(authority)
    if params.q:
        query = query.where(
            sa.or_(
                User.username.icontains(params.q, autoescape=True),
                User.display_name.icontains(params.q, autoescape=True),
                User.institutional_code.icontains(params.q, autoescape=True),
            )
        )
    total = db.scalar(sa.select(sa.func.count()).select_from(query.subquery()))
    ordered = query.order_by(User.username, User.id)
    user_rows = list(db.scalars(ordered.offset(params.offset).limit(params.limit)).all())
    active_suspensions = access.active_suspensions_for(
        db, authority.institution_id, [row.id for row in user_rows]
    )
    items = [
        schemas.QtaUserOut(
            id=row.id,
            username=row.username,
            display_name=row.display_name,
            institutional_code=row.institutional_code,
            primary_unit_id=row.primary_unit_id,
            state=row.state,
            quota_status="SUSPENDED" if row.id in active_suspensions else "ACTIVE",
        )
        for row in user_rows
    ]
    return Page(items=items, total=int(total or 0), limit=params.limit, offset=params.offset)


def user_entitlements(
    db: Session,
    authority: ActorAuthority,
    user_id: UUID,
    params: schemas.MonthQuery,
    settings: Settings,
) -> schemas.UserEntitlementsOut:
    """Personal additive entitlement & kill-switch lookup for an open month."""
    authority.require_permission(P.QTA_READ)
    resolved_month = periods.resolve_month(params.month, settings, open_only=True)
    user = one(db, _scoped_user_query(authority).where(User.id == user_id))
    computed = entitlements.compute_user_entitlements(db, user.institution_id, user.id)
    return schemas.UserEntitlementsOut(
        user=schemas.QtaUserSummaryOut.model_validate(user),
        month=periods.format_month(resolved_month),
        quota_status=computed.quota_status,
        suspension=computed.suspension,
        memberships=computed.memberships,
        models=computed.models,
        base_entitlement_total=computed.base_entitlement_total,
    )


def user_suspensions(
    db: Session,
    authority: ActorAuthority,
    user_id: UUID,
    params: PageParams,
) -> Page[schemas.SuspensionOut]:
    """List suspension history for one user (GLOBAL or exact-UNIT qta.read, newest first)."""
    authority.require_permission(P.QTA_READ)
    user = one(db, _scoped_user_query(authority).where(User.id == user_id))
    now = periods.utc_now()
    statement = (
        sa.select(QtaSuspension, QtaSuspensionRestoration)
        .outerjoin(
            QtaSuspensionRestoration,
            sa.and_(
                QtaSuspensionRestoration.suspension_id == QtaSuspension.id,
                QtaSuspensionRestoration.institution_id == QtaSuspension.institution_id,
            ),
        )
        .where(
            QtaSuspension.institution_id == user.institution_id,
            QtaSuspension.user_id == user.id,
        )
        .order_by(QtaSuspension.suspended_at.desc(), QtaSuspension.id.desc())
    )
    return page(
        db,
        statement,
        params,
        lambda susp, rest: access.suspension_out(susp, rest, now=now),
    )


def budget_for_tenant(
    db: Session, tenant: UUID, resolved_month: date, settings: Settings
) -> schemas.MonthlyBudgetOut:
    revision_rows = list(
        db.scalars(
            sa.select(QtaBudgetRevision)
            .where(
                QtaBudgetRevision.institution_id == tenant,
                QtaBudgetRevision.period_month == resolved_month,
            )
            .order_by(QtaBudgetRevision.revision.desc())
        ).all()
    )
    revisions = [schemas.BudgetRevisionOut.model_validate(row) for row in revision_rows]
    current = revisions[0] if revisions else None
    recorded = current is not None

    if periods.is_open_month(resolved_month, settings):
        allocation_status: schemas.AllocationStatus = "LIVE"
        allocated: int | None = entitlements.allocated_for_month(db, tenant)
        if current is not None:
            remaining: int | None = max(0, current.total_limit - allocated)
            over_allocated: int | None = max(0, allocated - current.total_limit)
        else:
            remaining = None
            over_allocated = None
    else:
        allocation_status = "NOT_SNAPSHOTTED"
        allocated = None
        remaining = None
        over_allocated = None

    return schemas.MonthlyBudgetOut(
        month=periods.format_month(resolved_month),
        status="RECORDED" if recorded else "NOT_RECORDED",
        status_label="Đã ghi nhận" if recorded else "chưa ghi nhận",
        current=current,
        revisions=revisions,
        allocation_status=allocation_status,
        allocated=allocated,
        remaining=remaining,
        over_allocated=over_allocated,
    )


def budget(
    db: Session,
    authority: ActorAuthority,
    params: schemas.MonthQuery,
    settings: Settings,
) -> schemas.MonthlyBudgetOut:
    """Read institutional monthly budget revisions and allocation status (GLOBAL qta.read only)."""
    tenant = reader(authority)
    resolved_month = periods.resolve_month(params.month, settings, open_only=False)
    return budget_for_tenant(db, tenant, resolved_month, settings)


def _event_out(row: QtaEvent) -> schemas.QtaEventOut:
    return schemas.QtaEventOut(
        id=row.id,
        month=periods.format_month(row.period_month),
        event_type=row.event_type,
        user_id=row.user_id,
        actor_id=row.actor_id,
        summary=row.summary,
        occurred_at=row.occurred_at,
    )


def events(
    db: Session,
    authority: ActorAuthority,
    params: schemas.QtaEventFilters,
    settings: Settings,
) -> Page[schemas.QtaEventOut]:
    """List append-only QTA events for a calendar month (GLOBAL qta.read, newest first)."""
    tenant = reader(authority)
    resolved_month = periods.resolve_month(params.month, settings, open_only=False)
    statement = sa.select(QtaEvent).where(
        QtaEvent.institution_id == tenant,
        QtaEvent.period_month == resolved_month,
    )
    if params.event_type is not None:
        statement = statement.where(QtaEvent.event_type == params.event_type)
    if params.user_id is not None:
        statement = statement.where(QtaEvent.user_id == params.user_id)
    return page(
        db,
        statement.order_by(QtaEvent.occurred_at.desc(), QtaEvent.id.desc()),
        params,
        _event_out,
    )


def monthly_reset_out(row: QtaMonthlyReset) -> schemas.MonthlyResetOut:
    return schemas.MonthlyResetOut(
        id=row.id,
        month=periods.format_month(row.period_month),
        trigger_mode=row.trigger_mode,
        triggered_by=row.triggered_by,
        executed_at=row.executed_at,
    )


def monthly_resets(
    db: Session,
    authority: ActorAuthority,
    params: PageParams,
    settings: Settings,
) -> schemas.MonthlyResetsOut:
    """List monthly reset history newest-first plus current month status (GLOBAL qta.read)."""
    tenant = reader(authority)
    cur_month = periods.current_month(settings)
    cur_row = db.scalar(
        sa.select(QtaMonthlyReset).where(
            QtaMonthlyReset.institution_id == tenant,
            QtaMonthlyReset.period_month == cur_month,
        )
    )
    current = schemas.CurrentMonthlyResetOut(
        month=periods.format_month(cur_month),
        status="COMPLETED" if cur_row is not None else "PENDING",
        reset=monthly_reset_out(cur_row) if cur_row is not None else None,
    )

    statement = (
        sa.select(QtaMonthlyReset)
        .where(QtaMonthlyReset.institution_id == tenant)
        .order_by(
            QtaMonthlyReset.period_month.desc(),
            QtaMonthlyReset.executed_at.desc(),
            QtaMonthlyReset.id.desc(),
        )
    )
    paged = page(db, statement, params, monthly_reset_out)
    return schemas.MonthlyResetsOut(
        current=current,
        items=paged.items,
        total=paged.total,
        limit=paged.limit,
        offset=paged.offset,
    )
