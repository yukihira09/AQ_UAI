"""Versioned MDL endpoints (M3, connection tests M4, routing M5, history M7). GET needs ``mdl.read``; every write needs ``mdl.manage``.

Writes reuse the shared protected-write path (session cookie, exact Origin, CSRF
header, transaction-time re-authorization). Responses never contain a secret.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from aq_uai_api.auth.write import WriteProof
from aq_uai_api.authorization.dependencies import read_authority, require_authenticated_write
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.writes import WriteContext
from aq_uai_api.core.config import Settings, get_settings
from aq_uai_api.db.session import get_session
from aq_uai_api.directory.schemas import Input, Page, PageParams
from aq_uai_api.mdl import history, queries, routing, schemas, service, testing

router = APIRouter(prefix="/mdl", tags=["MDL"])
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
    """State-change routes accept no fields."""


Empty = [Depends(_empty_body)]


@router.get("/status")
def status(authority: Reader, settings: Config) -> schemas.StatusOut:
    queries.reader(authority)
    return queries.status(settings)


@router.get("/providers")
def providers(
    db: DB, authority: Reader, settings: Config, params: Annotated[schemas.ProviderFilters, Query()]
) -> Page[schemas.ProviderOut]:
    return queries.providers(db, authority, params, settings)


@router.post("/providers", status_code=201)
def create_provider(payload: schemas.CreateProvider, writer: Writer) -> schemas.ProviderOut:
    return service.create_provider(writer, payload)


@router.get("/providers/{provider_id}")
def provider(
    provider_id: UUID, db: DB, authority: Reader, settings: Config
) -> schemas.ProviderOut:
    return queries.provider(db, authority, provider_id, settings)


@router.patch("/providers/{provider_id}")
def update_provider(
    provider_id: UUID, payload: schemas.ProviderPatch, writer: Writer
) -> schemas.ProviderOut:
    return service.update_provider(writer, provider_id, payload)


@router.post("/providers/{provider_id}/activate", dependencies=Empty)
def activate_provider(provider_id: UUID, writer: Writer) -> schemas.ProviderOut:
    return service.set_provider_active(writer, provider_id, True)


@router.post("/providers/{provider_id}/deactivate", dependencies=Empty)
def deactivate_provider(provider_id: UUID, writer: Writer) -> schemas.ProviderOut:
    return service.set_provider_active(writer, provider_id, False)


@router.get("/providers/{provider_id}/agreements")
def agreements(
    provider_id: UUID, db: DB, authority: Reader, params: Annotated[PageParams, Query()]
) -> Page[schemas.AgreementOut]:
    return queries.agreements(db, authority, provider_id, params)


@router.post("/providers/{provider_id}/agreements", status_code=201)
def record_agreement(
    provider_id: UUID, payload: schemas.AgreementIn, writer: Writer
) -> schemas.AgreementOut:
    return service.record_agreement(writer, provider_id, payload)


@router.post("/providers/{provider_id}/agreements/{agreement_id}/withdraw", dependencies=Empty)
def withdraw_agreement(
    provider_id: UUID, agreement_id: UUID, writer: Writer
) -> schemas.WithdrawalOut:
    return service.withdraw_agreement(writer, provider_id, agreement_id)


@router.get("/models")
def models(
    db: DB, authority: Reader, settings: Config, params: Annotated[schemas.ModelFilters, Query()]
) -> Page[schemas.ModelOut]:
    return queries.models(db, authority, params, settings)


@router.post("/models", status_code=201)
def create_model(payload: schemas.CreateModel, writer: Writer) -> schemas.ModelOut:
    return service.create_model(writer, payload)


@router.get("/models/{model_id}")
def model(model_id: UUID, db: DB, authority: Reader, settings: Config) -> schemas.ModelOut:
    return queries.model(db, authority, model_id, settings)


@router.patch("/models/{model_id}")
def update_model(model_id: UUID, payload: schemas.ModelPatch, writer: Writer) -> schemas.ModelOut:
    return service.update_model(writer, model_id, payload)


@router.post("/models/{model_id}/activate", dependencies=Empty)
def activate_model(model_id: UUID, writer: Writer) -> schemas.ModelOut:
    return service.set_model_active(writer, model_id, True)


@router.post("/models/{model_id}/deactivate", dependencies=Empty)
def deactivate_model(model_id: UUID, writer: Writer) -> schemas.ModelOut:
    return service.set_model_active(writer, model_id, False)


@router.get("/models/{model_id}/connection-tests")
def connection_tests(
    model_id: UUID, db: DB, authority: Reader, params: Annotated[PageParams, Query()]
) -> Page[schemas.ConnectionTestOut]:
    return queries.connection_tests(db, authority, model_id, params)


@router.post("/models/{model_id}/connection-tests", status_code=201)
def run_connection_test(
    model_id: UUID, writer: Writer, payload: schemas.ConnectionTestIn | None = None
) -> schemas.ConnectionTestOut:
    """Run one real test (FR-MDL-020). 201 with the stored result, PASSED or FAILED."""
    return testing.run_connection_test(writer, model_id, payload or schemas.ConnectionTestIn())


@router.get("/routing")
def get_routing(db: DB, authority: Reader, settings: Config) -> schemas.RoutingOut:
    """Configured primary/fallback, whether each may be used now, and the effective route."""
    return routing.get_routing(db, authority, settings)


@router.put("/routing")
def update_routing(payload: schemas.RoutingIn, writer: Writer) -> schemas.RoutingOut:
    """FR-MDL-021: change primary/fallback; each change writes one immutable revision."""
    return routing.update_routing(writer, payload)


@router.get("/routing/revisions")
def routing_revisions(
    db: DB, authority: Reader, params: Annotated[PageParams, Query()]
) -> Page[schemas.RoutingRevisionOut]:
    return routing.revisions(db, authority, params)


@router.get("/history")
def configuration_history(
    db: DB, authority: Reader, params: Annotated[schemas.HistoryFilters, Query()]
) -> Page[schemas.ConfigurationEventOut]:
    """Configuration changes with before/after values (M7; FRD section 6 "Should")."""
    return history.history(db, authority, params)
