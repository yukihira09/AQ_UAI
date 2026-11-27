"""Read-side QTA queries and projections (Phase 4, Stage Q2).

Every query is restricted to the caller's institution and requires GLOBAL ``qta.read``.
Reads MDL tables (``mdl_models``, ``mdl_providers``) read-only; ``mdl/`` never imports ``qta/``.
Live memberships are read directly from Phase 2 ``group_memberships`` without duplicating rows.
"""

from collections import defaultdict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.db.identity import AccountGroup, GroupMembership, User
from aq_uai_api.directory import queries as dir_queries
from aq_uai_api.directory import schemas as dir_schemas
from aq_uai_api.directory.queries import one, page
from aq_uai_api.directory.schemas import Page, PageParams, SearchParams
from aq_uai_api.mdl.models import MdlModel, MdlProvider
from aq_uai_api.qta import schemas
from aq_uai_api.qta.models import QtaGroupModelQuota, QtaGroupSyncRun, QtaQuotaGroup


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
        active=model.active,
    )


def models(
    db: Session, authority: ActorAuthority, params: SearchParams
) -> Page[schemas.QtaModelOut]:
    tenant = reader(authority)
    statement = (
        sa.select(MdlModel, MdlProvider)
        .join(
            MdlProvider,
            sa.and_(
                MdlProvider.id == MdlModel.provider_id,
                MdlProvider.institution_id == MdlModel.institution_id,
            ),
        )
        .where(MdlModel.institution_id == tenant, MdlModel.active.is_(True))
    )
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
        sa.select(QtaGroupModelQuota, MdlModel, MdlProvider)
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
    for quota, model, provider in rows:
        grouped[quota.group_id].append(
            schemas.GroupQuotaRuleOut(
                id=quota.id,
                model_id=model.id,
                model_technical_id=model.technical_id,
                model_display_name=model.display_name,
                model_active=model.active,
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
        from aq_uai_api.api.errors import DomainError, ErrorCode

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
