"""Versioned QTA endpoints (Phase 4, Stages Q2–Q4).

GET endpoints require ``qta.read`` (GLOBAL for institutional resources; GLOBAL or exact-UNIT
for user lookup and user suspension history); every write requires direct GLOBAL ``qta.manage``
through the shared protected-write path (session cookie, exact Origin, CSRF header,
transaction-time re-authorization, same-transaction typed audit).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from aq_uai_api.auth.write import WriteProof
from aq_uai_api.authorization.dependencies import read_authority, require_authenticated_write
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.writes import WriteContext
from aq_uai_api.core.config import Settings, get_settings
from aq_uai_api.db.session import get_session
from aq_uai_api.directory.schemas import (
    Input,
    MemberFilters,
    MemberOut,
    Page,
    PageParams,
    SearchParams,
)
from aq_uai_api.qta import queries, schemas, service

router = APIRouter(prefix="/qta", tags=["QTA"])
DB = Annotated[Session, Depends(get_session)]
Reader = Annotated[ActorAuthority, Depends(read_authority)]
Config = Annotated[Settings, Depends(get_settings)]


def _write_context(
    request: Request,
    proof: Annotated[WriteProof, Depends(require_authenticated_write)],
    settings: Config,
) -> WriteContext:
    return WriteContext(proof, settings, UUID(request.state.request_id))


Writer = Annotated[WriteContext, Depends(_write_context)]


def _empty_body(payload: Input | None = None) -> None:
    """State-change, sync, and manual reset routes accept no body fields."""


Empty = [Depends(_empty_body)]


@router.get("/models")
def list_models(
    db: DB, authority: Reader, params: Annotated[SearchParams, Query()]
) -> Page[schemas.QtaModelOut]:
    return queries.models(db, authority, params)


@router.get("/groups")
def list_groups(
    db: DB, authority: Reader, params: Annotated[schemas.QtaGroupFilters, Query()]
) -> Page[schemas.QtaGroupOut]:
    return queries.groups(db, authority, params)


@router.post("/groups", status_code=201)
def create_specialist_group(
    payload: schemas.CreateSpecialistGroup, writer: Writer
) -> schemas.QtaGroupOut:
    return service.create_specialist_group(writer, payload)


@router.post("/groups/sync", dependencies=Empty)
def sync_groups(writer: Writer) -> schemas.SyncRunOut:
    return service.sync_groups(writer)


@router.get("/groups/sync-runs")
def list_sync_runs(
    db: DB, authority: Reader, params: Annotated[PageParams, Query()]
) -> Page[schemas.SyncRunOut]:
    return queries.sync_runs(db, authority, params)


@router.get("/groups/{group_id}")
def group_detail(group_id: UUID, db: DB, authority: Reader) -> schemas.QtaGroupOut:
    return queries.group_detail(db, authority, group_id)


@router.patch("/groups/{group_id}")
def update_specialist_group(
    group_id: UUID, payload: schemas.UpdateSpecialistGroup, writer: Writer
) -> schemas.QtaGroupOut:
    return service.update_specialist_group(writer, group_id, payload)


@router.post("/groups/{group_id}/activate", dependencies=Empty)
def activate_specialist_group(group_id: UUID, writer: Writer) -> schemas.QtaGroupOut:
    return service.set_specialist_group_active(writer, group_id, True)


@router.post("/groups/{group_id}/deactivate", dependencies=Empty)
def deactivate_specialist_group(group_id: UUID, writer: Writer) -> schemas.QtaGroupOut:
    return service.set_specialist_group_active(writer, group_id, False)


@router.get("/groups/{group_id}/members")
def list_group_members(
    group_id: UUID,
    db: DB,
    authority: Reader,
    params: Annotated[MemberFilters, Query()],
) -> Page[MemberOut]:
    return queries.group_members(db, authority, group_id, params)


@router.put("/groups/{group_id}/members/{user_id}", dependencies=Empty)
def add_specialist_member(group_id: UUID, user_id: UUID, writer: Writer) -> MemberOut:
    result = service.set_specialist_membership(writer, group_id, user_id, True)
    assert result is not None
    return result


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=204,
    dependencies=Empty,
)
def remove_specialist_member(group_id: UUID, user_id: UUID, writer: Writer) -> Response:
    service.set_specialist_membership(writer, group_id, user_id, False)
    return Response(status_code=204)


@router.put("/groups/{group_id}/quotas")
def upsert_group_quotas(
    group_id: UUID, payload: schemas.UpsertGroupQuotas, writer: Writer
) -> schemas.QtaGroupOut:
    return service.upsert_group_quotas(writer, group_id, payload)


@router.get("/users")
def list_users(
    db: DB, authority: Reader, params: Annotated[SearchParams, Query()]
) -> Page[schemas.QtaUserOut]:
    return queries.users(db, authority, params)


@router.get("/users/{user_id}/entitlements")
def user_entitlements(
    user_id: UUID,
    db: DB,
    authority: Reader,
    settings: Config,
    params: Annotated[schemas.MonthQuery, Query()],
) -> schemas.UserEntitlementsOut:
    return queries.user_entitlements(db, authority, user_id, params, settings)


@router.get("/users/{user_id}/suspensions")
def list_user_suspensions(
    user_id: UUID,
    db: DB,
    authority: Reader,
    params: Annotated[PageParams, Query()],
) -> Page[schemas.SuspensionOut]:
    return queries.user_suspensions(db, authority, user_id, params)


@router.post("/users/{user_id}/suspensions", status_code=201)
def suspend_user(
    user_id: UUID, payload: schemas.SuspendUser, writer: Writer
) -> schemas.SuspensionOut:
    return service.suspend_user(writer, user_id, payload)


@router.post("/users/{user_id}/restore")
def restore_user(
    user_id: UUID,
    writer: Writer,
    payload: Annotated[schemas.RestoreUser | None, Body()] = None,
) -> schemas.SuspensionOut:
    return service.restore_user(writer, user_id, payload or schemas.RestoreUser())


@router.get("/budgets")
def get_monthly_budget(
    db: DB,
    authority: Reader,
    settings: Config,
    params: Annotated[schemas.MonthQuery, Query()],
) -> schemas.MonthlyBudgetOut:
    return queries.budget(db, authority, params, settings)


@router.put("/budgets/{month}")
def set_monthly_budget(
    month: str, payload: schemas.SetMonthlyBudget, writer: Writer
) -> schemas.MonthlyBudgetOut:
    return service.record_budget_revision(writer, month, payload)


@router.get("/events")
def list_events(
    db: DB,
    authority: Reader,
    settings: Config,
    params: Annotated[schemas.QtaEventFilters, Query()],
) -> Page[schemas.QtaEventOut]:
    return queries.events(db, authority, params, settings)


@router.get("/monthly-resets")
def list_monthly_resets(
    db: DB,
    authority: Reader,
    settings: Config,
    params: Annotated[PageParams, Query()],
) -> schemas.MonthlyResetsOut:
    return queries.monthly_resets(db, authority, params, settings)


@router.post("/monthly-resets", status_code=201, dependencies=Empty)
def simulate_monthly_reset(writer: Writer) -> schemas.MonthlyResetOut:
    return service.simulate_monthly_reset(writer)
