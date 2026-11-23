"""Versioned directory and audit endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from aq_uai_api.auth.write import WriteProof
from aq_uai_api.authorization.dependencies import read_authority, require_authenticated_write
from aq_uai_api.authorization.policy import ActorAuthority, GrantSubject
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.core.config import Settings, get_settings
from aq_uai_api.db.identity import AccountGroup, AuditEvent, Unit, User
from aq_uai_api.db.session import get_session
from aq_uai_api.directory import queries, schemas, service

router = APIRouter(tags=["Directory"])
DB = Annotated[Session, Depends(get_session)]
Reader = Annotated[ActorAuthority, Depends(read_authority)]


def _write_context(
    request: Request,
    proof: Annotated[WriteProof, Depends(require_authenticated_write)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> service.WriteContext:
    return service.WriteContext(proof, settings, UUID(request.state.request_id))


Writer = Annotated[service.WriteContext, Depends(_write_context)]


def _empty_mutation_body(payload: schemas.Input | None = None) -> None:
    """Validate optional empty bodies and reject unexpected mutation fields."""


@router.get("/users")
def users(
    db: DB, authority: Reader, params: Annotated[schemas.UserFilters, Query()]
) -> schemas.Page[schemas.UserOut]:
    return queries.users(db, authority, params)


@router.get("/users/{user_id}")
def user_detail(user_id: UUID, db: DB, authority: Reader) -> schemas.UserOut:
    authority.require_permission(P.DIRECTORY_READ)
    return schemas.UserOut.model_validate(
        queries.one(db, queries.user_query(authority).where(User.id == user_id))
    )


@router.post("/users", status_code=201)
def create_user(payload: schemas.CreateUser, writer: Writer) -> schemas.UserOut:
    return service.create_user(writer, payload)


@router.patch("/users/{user_id}/profile")
def update_profile(user_id: UUID, payload: schemas.ProfilePatch, writer: Writer) -> schemas.UserOut:
    return service.update_profile(writer, user_id, payload)


@router.patch("/users/{user_id}/identity")
def update_identity(
    user_id: UUID, payload: schemas.IdentityPatch, writer: Writer
) -> schemas.UserOut:
    return service.update_identity(writer, user_id, payload)


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: UUID, writer: Writer, payload: schemas.Activation | None = None
) -> schemas.UserOut:
    return service.set_user_state(
        writer, user_id, "ACTIVE", payload.temporary_password if payload else None
    )


@router.post("/users/{user_id}/disable", dependencies=[Depends(_empty_mutation_body)])
def disable_user(user_id: UUID, writer: Writer) -> schemas.UserOut:
    return service.set_user_state(writer, user_id, "DISABLED")


@router.post("/users/{user_id}/transfer")
def transfer_user(user_id: UUID, payload: schemas.Transfer, writer: Writer) -> schemas.UserOut:
    return service.transfer(writer, user_id, payload)


@router.get("/units")
def units(
    db: DB, authority: Reader, params: Annotated[schemas.UnitFilters, Query()]
) -> schemas.Page[schemas.UnitOut]:
    return queries.units(db, authority, params)


@router.get("/units/{unit_id}")
def unit_detail(unit_id: UUID, db: DB, authority: Reader) -> schemas.UnitOut:
    authority.require_permission(P.DIRECTORY_READ)
    return schemas.UnitOut.model_validate(
        queries.one(db, queries.unit_query(authority).where(Unit.id == unit_id))
    )


@router.post("/units", status_code=201)
def create_unit(payload: schemas.CreateUnit, writer: Writer) -> schemas.UnitOut:
    return service.create_unit(writer, payload)


@router.patch("/units/{unit_id}")
def update_unit(unit_id: UUID, payload: schemas.UnitPatch, writer: Writer) -> schemas.UnitOut:
    return service.update_unit(writer, unit_id, payload)


@router.post("/units/{unit_id}/activate", dependencies=[Depends(_empty_mutation_body)])
def activate_unit(unit_id: UUID, writer: Writer) -> schemas.UnitOut:
    return service.set_unit_active(writer, unit_id, True)


@router.post("/units/{unit_id}/deactivate", dependencies=[Depends(_empty_mutation_body)])
def deactivate_unit(unit_id: UUID, writer: Writer) -> schemas.UnitOut:
    return service.set_unit_active(writer, unit_id, False)


@router.get("/groups")
def groups(
    db: DB, authority: Reader, params: Annotated[schemas.GroupFilters, Query()]
) -> schemas.Page[schemas.GroupOut]:
    return queries.groups(db, authority, params)


@router.get("/groups/{group_id}")
def group_detail(group_id: UUID, db: DB, authority: Reader) -> schemas.GroupOut:
    authority.require_institution(P.DIRECTORY_READ, authority.institution_id)
    return schemas.GroupOut.model_validate(
        queries.one(db, queries.group_query(authority).where(AccountGroup.id == group_id))
    )


@router.post("/groups", status_code=201)
def create_group(payload: schemas.CreateGroup, writer: Writer) -> schemas.GroupOut:
    return service.create_group(writer, payload)


@router.patch("/groups/{group_id}")
def update_group(group_id: UUID, payload: schemas.GroupPatch, writer: Writer) -> schemas.GroupOut:
    return service.update_group(writer, group_id, payload)


@router.post("/groups/{group_id}/activate", dependencies=[Depends(_empty_mutation_body)])
def activate_group(group_id: UUID, writer: Writer) -> schemas.GroupOut:
    return service.set_group_active(writer, group_id, True)


@router.post("/groups/{group_id}/deactivate", dependencies=[Depends(_empty_mutation_body)])
def deactivate_group(group_id: UUID, writer: Writer) -> schemas.GroupOut:
    return service.set_group_active(writer, group_id, False)


@router.get("/groups/{group_id}/members")
def members(
    group_id: UUID, db: DB, authority: Reader, params: Annotated[schemas.MemberFilters, Query()]
) -> schemas.Page[schemas.MemberOut]:
    return queries.members(db, authority, group_id, params)


@router.put("/groups/{group_id}/members/{user_id}", dependencies=[Depends(_empty_mutation_body)])
def add_member(group_id: UUID, user_id: UUID, writer: Writer) -> schemas.MemberOut:
    return service.set_membership(writer, group_id, user_id, True)


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=204,
    dependencies=[Depends(_empty_mutation_body)],
)
def remove_member(group_id: UUID, user_id: UUID, writer: Writer) -> Response:
    service.set_membership(writer, group_id, user_id, False)
    return Response(status_code=204)


@router.get("/roles")
def roles(
    db: DB, authority: Reader, params: Annotated[schemas.SearchParams, Query()]
) -> schemas.Page[schemas.RoleOut]:
    return queries.roles(db, authority, params)


@router.get("/users/{user_id}/role-assignments")
def user_assignments(
    user_id: UUID, db: DB, authority: Reader, params: Annotated[schemas.AssignmentFilters, Query()]
) -> schemas.Page[schemas.AssignmentOut]:
    return queries.assignments(db, authority, GrantSubject.USER, user_id, params)


@router.post("/users/{user_id}/role-assignments", status_code=201)
def create_user_assignment(
    user_id: UUID, payload: schemas.CreateAssignment, writer: Writer
) -> schemas.AssignmentOut:
    return service.create_assignment(writer, GrantSubject.USER, user_id, payload)


@router.delete(
    "/users/{user_id}/role-assignments/{grant_id}",
    status_code=204,
    dependencies=[Depends(_empty_mutation_body)],
)
def remove_user_assignment(user_id: UUID, grant_id: UUID, writer: Writer) -> Response:
    service.remove_assignment(writer, GrantSubject.USER, user_id, grant_id)
    return Response(status_code=204)


@router.get("/groups/{group_id}/role-assignments")
def group_assignments(
    group_id: UUID, db: DB, authority: Reader, params: Annotated[schemas.AssignmentFilters, Query()]
) -> schemas.Page[schemas.AssignmentOut]:
    return queries.assignments(db, authority, GrantSubject.GROUP, group_id, params)


@router.post("/groups/{group_id}/role-assignments", status_code=201)
def create_group_assignment(
    group_id: UUID, payload: schemas.CreateAssignment, writer: Writer
) -> schemas.AssignmentOut:
    return service.create_assignment(writer, GrantSubject.GROUP, group_id, payload)


@router.delete(
    "/groups/{group_id}/role-assignments/{grant_id}",
    status_code=204,
    dependencies=[Depends(_empty_mutation_body)],
)
def remove_group_assignment(group_id: UUID, grant_id: UUID, writer: Writer) -> Response:
    service.remove_assignment(writer, GrantSubject.GROUP, group_id, grant_id)
    return Response(status_code=204)


@router.get("/audit-events")
def audit_events(
    db: DB, authority: Reader, params: Annotated[schemas.AuditFilters, Query()]
) -> schemas.Page[schemas.AuditOut]:
    return queries.audit_events(db, authority, params)


@router.get("/audit-events/{event_id}")
def audit_detail(event_id: UUID, db: DB, authority: Reader) -> schemas.AuditOut:
    return queries.audit_out(
        queries.one(db, queries.audit_query(authority).where(AuditEvent.id == event_id))
    )


@router.get("/directory/capabilities")
def capabilities(authority: Reader) -> schemas.Capabilities:
    return queries.capabilities(authority)
