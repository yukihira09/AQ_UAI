"""Protected QTA writes (Phase 4, Stages Q2–Q4): sync, specialist groups, quotas, budgets, kill-switch & reset.

Every write executes inside the shared ``protected`` transaction (session, exact Origin,
CSRF, transaction-time ``qta.manage`` re-authorization) and records its typed audit event
(plus any ``qta_events`` ledger row) in the same transaction so audit failure rolls back
the mutation.

AI-specialist group lifecycle writes delegate directly to ``directory.service`` inner
functions (``create_group_in_tx``, ``update_group_in_tx``, ``set_group_active_in_tx``,
``set_membership_in_tx``) rather than duplicating directory write logic or audit actions.
"""

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.service import database_lock
from aq_uai_api.authorization.policy import ActorAuthority, require_group_management
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.authorization.writes import WriteContext, institution_key, protected, record
from aq_uai_api.db import audit
from aq_uai_api.db.identity import AccountGroup, GroupMembership, User
from aq_uai_api.directory import schemas as dir_schemas
from aq_uai_api.directory import service as dir_service
from aq_uai_api.directory.queries import one
from aq_uai_api.mdl.models import MdlModel, MdlProvider
from aq_uai_api.qta import access, entitlements, periods, queries, reset, schemas
from aq_uai_api.qta.models import (
    QtaBudgetRevision,
    QtaEvent,
    QtaGroupModelQuota,
    QtaGroupSyncRun,
    QtaQuotaGroup,
    QtaSuspension,
    QtaSuspensionRestoration,
)

QTA_SYNC_NAMESPACE = 52000
QTA_BUDGET_NAMESPACE = 52001
QTA_SUSPENSION_NAMESPACE = access.QTA_SUSPENSION_NAMESPACE
QTA_RESET_NAMESPACE = reset.QTA_RESET_NAMESPACE


def _manager(authority: ActorAuthority) -> UUID:
    authority.require_institution(P.QTA_MANAGE, authority.institution_id)
    return authority.institution_id


def _load_specialist_for_qta(
    db: Session, authority: ActorAuthority, group_id: UUID, *, lock: bool = False
) -> AccountGroup:
    """Resolve an enrolled AI_SPECIALIST group for QTA mutation.

    - Missing / other institution -> 404 NOT_FOUND.
    - SYSTEM or AUTHORIZATION when caller lacks directory/authorization permission -> 403 FORBIDDEN.
    - Non-AI_SPECIALIST (e.g., dual-role caller on SYSTEM) or unenrolled group -> 422 QTA_GROUP_NOT_ELIGIBLE.
    """
    tenant = authority.institution_id
    stmt = sa.select(AccountGroup).where(
        AccountGroup.institution_id == tenant,
        AccountGroup.id == group_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    group = one(db, stmt)
    require_group_management(authority, group.institution_id, group.kind)
    registry = db.scalar(
        sa.select(QtaQuotaGroup).where(
            QtaQuotaGroup.institution_id == tenant,
            QtaQuotaGroup.group_id == group.id,
        )
    )
    if group.kind != "AI_SPECIALIST" or registry is None:
        raise DomainError(ErrorCode.QTA_GROUP_NOT_ELIGIBLE)
    return group


def sync_groups(context: WriteContext) -> schemas.SyncRunOut:
    """Reconcile QTA registry with Phase 2 directory groups (FR-QTA-020, RULE-QTA-05).

    Serialized per institution with ``QTA_SYNC_NAMESPACE``.
    - Enrolls active SYSTEM groups not yet in ``qta_quota_groups`` (origin='SYNC').
    - Enrolls active AI_SPECIALIST groups created outside QTA (origin='SPECIALIST').
    - Marks enrolled SYSTEM groups inactive/missing in directory ``in_directory=false``
      without deleting rows or quotas; restores ``in_directory=true`` if active again.
    - Never modifies existing ``origin='SPECIALIST'`` rows or any quota row.
    - Ignores ``AUTHORIZATION`` groups completely.
    """
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        database_lock(db, QTA_SYNC_NAMESPACE, institution_key(tenant), shared=False)

        dir_groups = list(
            db.scalars(
                sa.select(AccountGroup)
                .where(
                    AccountGroup.institution_id == tenant,
                    AccountGroup.kind.in_(("SYSTEM", "AI_SPECIALIST")),
                )
                .order_by(AccountGroup.id)
            ).all()
        )
        dir_by_id = {group.id: group for group in dir_groups}

        existing = list(
            db.scalars(
                sa.select(QtaQuotaGroup)
                .where(QtaQuotaGroup.institution_id == tenant)
                .order_by(QtaQuotaGroup.group_id)
                .with_for_update()
            ).all()
        )
        reg_by_id = {row.group_id: row for row in existing}

        now = datetime.now(UTC)
        groups_added = 0
        groups_retired = 0

        for group in dir_groups:
            if group.id in reg_by_id or not group.active:
                continue
            if group.kind == "SYSTEM":
                db.add(
                    QtaQuotaGroup(
                        institution_id=tenant,
                        group_id=group.id,
                        group_kind="SYSTEM",
                        origin="SYNC",
                        in_directory=True,
                        enrolled_by=authority.actor_id,
                        last_synced_at=now,
                    )
                )
                groups_added += 1
            elif group.kind == "AI_SPECIALIST":
                db.add(
                    QtaQuotaGroup(
                        institution_id=tenant,
                        group_id=group.id,
                        group_kind="AI_SPECIALIST",
                        origin="SPECIALIST",
                        in_directory=True,
                        enrolled_by=authority.actor_id,
                        last_synced_at=now,
                    )
                )
                groups_added += 1

        for reg in existing:
            if reg.origin != "SYNC":
                continue
            dir_group = dir_by_id.get(reg.group_id)
            currently_active = dir_group is not None and dir_group.active
            if reg.in_directory and not currently_active:
                reg.in_directory = False
                groups_retired += 1
            elif not reg.in_directory and currently_active:
                reg.in_directory = True
            reg.last_synced_at = now

        db.flush()

        system_group_count = int(
            db.scalar(
                sa.select(sa.func.count())
                .select_from(QtaQuotaGroup)
                .join(
                    AccountGroup,
                    sa.and_(
                        AccountGroup.id == QtaQuotaGroup.group_id,
                        AccountGroup.institution_id == QtaQuotaGroup.institution_id,
                    ),
                )
                .where(
                    QtaQuotaGroup.institution_id == tenant,
                    QtaQuotaGroup.origin == "SYNC",
                    QtaQuotaGroup.in_directory.is_(True),
                    AccountGroup.active.is_(True),
                )
            )
            or 0
        )
        specialist_group_count = int(
            db.scalar(
                sa.select(sa.func.count())
                .select_from(QtaQuotaGroup)
                .join(
                    AccountGroup,
                    sa.and_(
                        AccountGroup.id == QtaQuotaGroup.group_id,
                        AccountGroup.institution_id == QtaQuotaGroup.institution_id,
                    ),
                )
                .where(
                    QtaQuotaGroup.institution_id == tenant,
                    QtaQuotaGroup.origin == "SPECIALIST",
                    AccountGroup.active.is_(True),
                )
            )
            or 0
        )
        active_member_count = int(
            db.scalar(
                sa.select(sa.func.count(sa.distinct(GroupMembership.user_id)))
                .select_from(GroupMembership)
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
                    ),
                )
                .join(
                    User,
                    sa.and_(
                        User.id == GroupMembership.user_id,
                        User.institution_id == GroupMembership.institution_id,
                    ),
                )
                .where(
                    GroupMembership.institution_id == tenant,
                    GroupMembership.active.is_(True),
                    QtaQuotaGroup.in_directory.is_(True),
                    AccountGroup.active.is_(True),
                    User.state == "ACTIVE",
                )
            )
            or 0
        )

        run = QtaGroupSyncRun(
            institution_id=tenant,
            system_group_count=system_group_count,
            active_member_count=active_member_count,
            specialist_group_count=specialist_group_count,
            groups_added=groups_added,
            groups_retired=groups_retired,
            synced_by=authority.actor_id,
        )
        db.add(run)
        db.flush()

        record(
            db,
            context,
            authority,
            audit.AuditAction.QTA_GROUPS_SYNCED,
            run.id,
            audit.GroupsSynced(
                system_group_count=system_group_count,
                active_member_count=active_member_count,
                specialist_group_count=specialist_group_count,
                groups_added=groups_added,
                groups_retired=groups_retired,
            ),
        )
        return schemas.SyncRunOut.model_validate(run)


def create_specialist_group(
    context: WriteContext, payload: schemas.CreateSpecialistGroup
) -> schemas.QtaGroupOut:
    """Create an AI_SPECIALIST group via directory.service and enroll in QTA (FR-QTA-022)."""
    with protected(context, changes_authority=True) as (db, authority):
        tenant = _manager(authority)
        try:
            group = dir_service.create_group_in_tx(
                db,
                authority,
                context,
                dir_schemas.CreateGroup(
                    code=payload.code,
                    name=payload.name,
                    kind="AI_SPECIALIST",
                ),
            )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DomainError(ErrorCode.QTA_DUPLICATE) from None
            raise
        db.add(
            QtaQuotaGroup(
                institution_id=tenant,
                group_id=group.id,
                group_kind="AI_SPECIALIST",
                origin="SPECIALIST",
                in_directory=True,
                enrolled_by=authority.actor_id,
                last_synced_at=None,
            )
        )
        db.flush()
        return queries.group_detail_for_tenant(db, tenant, group.id)


def update_specialist_group(
    context: WriteContext, group_id: UUID, payload: schemas.UpdateSpecialistGroup
) -> schemas.QtaGroupOut:
    """Rename an enrolled AI_SPECIALIST group via directory.service."""
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        group = _load_specialist_for_qta(db, authority, group_id, lock=True)
        dir_service.update_group_in_tx(
            db,
            authority,
            context,
            group,
            dir_schemas.GroupPatch(name=payload.name),
        )
        db.flush()
        return queries.group_detail_for_tenant(db, tenant, group.id)


def set_specialist_group_active(
    context: WriteContext, group_id: UUID, active: bool
) -> schemas.QtaGroupOut:
    """Activate or deactivate an enrolled AI_SPECIALIST group via directory.service."""
    with protected(context, changes_authority=True) as (db, authority):
        tenant = _manager(authority)
        group = _load_specialist_for_qta(db, authority, group_id)
        dir_service.set_group_active_in_tx(db, authority, context, group, active)
        db.flush()
        return queries.group_detail_for_tenant(db, tenant, group.id)


def set_specialist_membership(
    context: WriteContext, group_id: UUID, user_id: UUID, active: bool
) -> dir_schemas.MemberOut | None:
    """Add/reactivate or deactivate a member of an enrolled AI_SPECIALIST group."""
    with protected(
        context, changes_authority=True, user_id=user_id, permission=P.QTA_MANAGE
    ) as (db, authority):
        tenant = _manager(authority)
        group = _load_specialist_for_qta(db, authority, group_id)
        user = one(
            db,
            sa.select(User).where(
                User.institution_id == tenant,
                User.id == user_id,
            ),
        )
        return dir_service.set_membership_in_tx(db, authority, context, group, user, active)


def upsert_group_quotas(
    context: WriteContext, group_id: UUID, payload: schemas.UpsertGroupQuotas
) -> schemas.QtaGroupOut:
    """Upsert per-model monthly quotas for one active enrolled group (FR-QTA-021, C1, C3).

    Never deletes unmentioned rows; audits only rows that actually changed.
    """
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        group = one(
            db,
            sa.select(AccountGroup).where(
                AccountGroup.institution_id == tenant,
                AccountGroup.id == group_id,
            ),
        )
        registry = db.scalar(
            sa.select(QtaQuotaGroup)
            .where(
                QtaQuotaGroup.institution_id == tenant,
                QtaQuotaGroup.group_id == group.id,
            )
            .with_for_update()
        )
        if registry is None or not registry.in_directory or not group.active:
            raise DomainError(ErrorCode.QTA_GROUP_NOT_ELIGIBLE)

        requested_ids = sorted({item.model_id for item in payload.quotas})
        found_models = {
            model_id: bool(usable)
            for model_id, usable in db.execute(
                sa.select(MdlModel.id, entitlements.usable_model_predicate())
                .join(
                    MdlProvider,
                    sa.and_(
                        MdlProvider.id == MdlModel.provider_id,
                        MdlProvider.institution_id == MdlModel.institution_id,
                    ),
                )
                .where(
                    MdlModel.institution_id == tenant,
                    MdlModel.id.in_(requested_ids),
                )
                .order_by(MdlModel.id)
            ).all()
        }
        for model_id in requested_ids:
            usable = found_models.get(model_id)
            if usable is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if not usable:
                raise DomainError(ErrorCode.QTA_MODEL_NOT_ELIGIBLE)

        existing = {
            row.model_id: row
            for row in db.scalars(
                sa.select(QtaGroupModelQuota)
                .where(
                    QtaGroupModelQuota.institution_id == tenant,
                    QtaGroupModelQuota.group_id == group.id,
                    QtaGroupModelQuota.model_id.in_(requested_ids),
                )
                .order_by(QtaGroupModelQuota.model_id)
                .with_for_update()
            ).all()
        }

        now = datetime.now(UTC)
        for item in payload.quotas:
            row = existing.get(item.model_id)
            if row is None:
                row = QtaGroupModelQuota(
                    institution_id=tenant,
                    group_id=group.id,
                    model_id=item.model_id,
                    enabled=item.enabled,
                    monthly_limit=item.monthly_limit,
                    warning_threshold_pct=item.warning_threshold_pct,
                    updated_by=authority.actor_id,
                )
                db.add(row)
                db.flush()
                record(
                    db,
                    context,
                    authority,
                    audit.AuditAction.QTA_GROUP_QUOTA_UPDATED,
                    row.id,
                    audit.GroupQuotaUpdated(
                        group_id=group.id,
                        model_id=item.model_id,
                        before_enabled=None,
                        after_enabled=item.enabled,
                        before_limit=None,
                        after_limit=item.monthly_limit,
                        before_warning_threshold_pct=None,
                        warning_threshold_pct=item.warning_threshold_pct,
                    ),
                )
                continue

            if (
                row.enabled == item.enabled
                and row.monthly_limit == item.monthly_limit
                and row.warning_threshold_pct == item.warning_threshold_pct
            ):
                continue

            before_enabled = row.enabled
            before_limit = row.monthly_limit
            before_threshold = row.warning_threshold_pct
            row.enabled = item.enabled
            row.monthly_limit = item.monthly_limit
            row.warning_threshold_pct = item.warning_threshold_pct
            row.updated_by = authority.actor_id
            row.updated_at = now
            db.flush()
            record(
                db,
                context,
                authority,
                audit.AuditAction.QTA_GROUP_QUOTA_UPDATED,
                row.id,
                audit.GroupQuotaUpdated(
                    group_id=group.id,
                    model_id=item.model_id,
                    before_enabled=before_enabled,
                    after_enabled=item.enabled,
                    before_limit=before_limit,
                    after_limit=item.monthly_limit,
                    before_warning_threshold_pct=before_threshold,
                    warning_threshold_pct=item.warning_threshold_pct,
                ),
            )

        return queries.group_detail_for_tenant(db, tenant, group.id)


def record_budget_revision(
    context: WriteContext, month: str, payload: schemas.SetMonthlyBudget
) -> schemas.MonthlyBudgetOut:
    """Append an immutable monthly budget revision (FR-QTA-010, FR-QTA-011, INV-18, PD-Q1/PD-Q4).

    Serialized per institution with ``QTA_BUDGET_NAMESPACE``. Rejects reducing ``total_limit``
    below live ``allocated_for_month`` with ``409 QTA_BUDGET_BELOW_ALLOCATED`` and exact
    ``{allocated, deficit}`` details. Never mutates or deletes prior revisions.
    """
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        resolved_month = periods.resolve_month(month, context.settings, open_only=True)
        database_lock(db, QTA_BUDGET_NAMESPACE, institution_key(tenant), shared=False)

        allocated = entitlements.allocated_for_month(db, tenant)
        if payload.total_limit < allocated:
            raise DomainError(
                ErrorCode.QTA_BUDGET_BELOW_ALLOCATED,
                {"allocated": allocated, "deficit": allocated - payload.total_limit},
            )

        previous = db.scalar(
            sa.select(QtaBudgetRevision)
            .where(
                QtaBudgetRevision.institution_id == tenant,
                QtaBudgetRevision.period_month == resolved_month,
            )
            .order_by(QtaBudgetRevision.revision.desc())
            .limit(1)
        )
        next_revision = (previous.revision + 1) if previous is not None else 1

        row = QtaBudgetRevision(
            institution_id=tenant,
            period_month=resolved_month,
            revision=next_revision,
            total_limit=payload.total_limit,
            decision_number=payload.decision_number,
            decision_date=payload.decision_date,
            recorded_by=authority.actor_id,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DomainError(ErrorCode.CONFLICT) from None
            raise

        record(
            db,
            context,
            authority,
            audit.AuditAction.QTA_MONTHLY_BUDGET_SET,
            row.id,
            audit.BudgetRevisionRecorded(
                period_month=resolved_month,
                revision=next_revision,
                before_limit=previous.total_limit if previous is not None else None,
                after_limit=row.total_limit,
                before_decision_number=(
                    previous.decision_number if previous is not None else None
                ),
                decision_number=row.decision_number,
                decision_date=row.decision_date,
            ),
        )
        return queries.budget_for_tenant(db, tenant, resolved_month, context.settings)


def suspend_user(
    context: WriteContext, user_id: UUID, payload: schemas.SuspendUser
) -> schemas.SuspensionOut:
    """Suspend an account's AI access without altering quota rules (FR-QTA-040, PD-Q2/PD-Q3).

    Lock order: institution shared lock -> sorted account locks (actor + target) via
    ``protected`` -> ``QTA_SUSPENSION_NAMESPACE`` exclusive lock. Operator ``suspended_by``
    is ALWAYS ``authority.actor_id`` (never from client input).
    """
    with protected(
        context, changes_authority=False, user_id=user_id, permission=P.QTA_MANAGE
    ) as (db, authority):
        tenant = _manager(authority)
        target = one(
            db,
            sa.select(User).where(
                User.institution_id == tenant,
                User.id == user_id,
            ),
        )
        now = periods.utc_now()
        if payload.expires_at is not None and payload.expires_at <= now:
            raise DomainError(ErrorCode.VALIDATION_FAILED)

        database_lock(db, QTA_SUSPENSION_NAMESPACE, institution_key(tenant), shared=False)
        if access.active_suspension_for_user(db, tenant, target.id, now=now) is not None:
            raise DomainError(ErrorCode.QTA_USER_ALREADY_SUSPENDED)

        row = QtaSuspension(
            institution_id=tenant,
            user_id=target.id,
            scope=payload.scope,
            reason=payload.reason,
            ordered_by=payload.ordered_by,
            expires_at=payload.expires_at,
            suspended_by=authority.actor_id,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if sqlstate == "23514" and constraint == "ck_qta_suspensions_expiry":
                raise DomainError(ErrorCode.VALIDATION_FAILED) from None
            raise

        event = QtaEvent(
            institution_id=tenant,
            period_month=periods.current_month(context.settings),
            event_type="SUSPEND",
            user_id=target.id,
            actor_id=authority.actor_id,
            summary=f"Tạm ngưng quyền dùng AI ({row.scope})",
        )
        db.add(event)
        db.flush()

        record(
            db,
            context,
            authority,
            audit.AuditAction.QTA_USER_SUSPENDED,
            row.id,
            audit.UserSuspended(
                user_id=target.id,
                scope=row.scope,
                ordered_by=row.ordered_by,
                expires_at=row.expires_at,
            ),
        )
        return access.suspension_out(row, None, now=now)


def restore_user(
    context: WriteContext, user_id: UUID, payload: schemas.RestoreUser
) -> schemas.SuspensionOut:
    """Restore an account's active AI suspension without adding quota (FR-QTA-041)."""
    with protected(
        context, changes_authority=False, user_id=user_id, permission=P.QTA_MANAGE
    ) as (db, authority):
        tenant = _manager(authority)
        target = one(
            db,
            sa.select(User).where(
                User.institution_id == tenant,
                User.id == user_id,
            ),
        )
        database_lock(db, QTA_SUSPENSION_NAMESPACE, institution_key(tenant), shared=False)
        now = periods.utc_now()
        active_susp = access.active_suspension_for_user(db, tenant, target.id, now=now)
        if active_susp is None:
            raise DomainError(ErrorCode.QTA_USER_NOT_SUSPENDED)

        restoration = QtaSuspensionRestoration(
            suspension_id=active_susp.id,
            institution_id=tenant,
            restored_by=authority.actor_id,
            note=payload.note,
        )
        db.add(restoration)
        try:
            db.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DomainError(ErrorCode.QTA_USER_NOT_SUSPENDED) from None
            raise

        event = QtaEvent(
            institution_id=tenant,
            period_month=periods.current_month(context.settings),
            event_type="RESTORE",
            user_id=target.id,
            actor_id=authority.actor_id,
            summary="Khôi phục quyền dùng AI",
        )
        db.add(event)
        db.flush()

        record(
            db,
            context,
            authority,
            audit.AuditAction.QTA_USER_RESTORED,
            active_susp.id,
            audit.UserRestored(
                user_id=target.id,
                suspension_id=active_susp.id,
            ),
        )
        return access.suspension_out(active_susp, restoration, now=now)


def simulate_monthly_reset(context: WriteContext) -> schemas.MonthlyResetOut:
    """Record a manual monthly reset marker for the current institution month only (PD-Q6)."""
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        month = periods.current_month(context.settings)
        outcome = reset.record_reset(
            db,
            tenant,
            month,
            "MANUAL_SIMULATION",
            authority.actor_id,
            context.request_id,
        )
        if not outcome.recorded:
            raise DomainError(ErrorCode.QTA_RESET_ALREADY_EXECUTED)
        return queries.monthly_reset_out(outcome.reset)
