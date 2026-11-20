"""Phase-1 diagnostics. These routes never expose database credentials."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from aq_uai_api import __version__
from aq_uai_api.api.errors import DiagnosticUnavailable
from aq_uai_api.db.models import AppMetadata
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.db.session import get_session

router = APIRouter(tags=["Phase 1 — System"])
DB = Annotated[Session, Depends(get_session)]


class LiveResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    database: str


class SystemInfoResponse(BaseModel):
    name: str
    milestone: str
    source: str


@router.get("/health", response_model=LiveResponse, summary="Process liveness (no DB needed)")
def health() -> LiveResponse:
    return LiveResponse(status="ok", service="AQ EduUAI API", version=__version__)


@router.get("/ready", response_model=ReadyResponse, summary="Database/migration readiness")
def ready(db: DB) -> ReadyResponse:
    try:
        revisions = db.scalars(text("SELECT version_num FROM public.alembic_version")).all()
        if revisions != [REQUIRED_SCHEMA_REVISION] or db.get(AppMetadata, "milestone") is None:
            raise DiagnosticUnavailable()
    except SQLAlchemyError:
        raise DiagnosticUnavailable() from None
    return ReadyResponse(status="ready", database="connected")


@router.get(
    "/system/info",
    response_model=SystemInfoResponse,
    summary="Read the Phase-1 seed data from PostgreSQL",
)
def system_info(db: DB) -> SystemInfoResponse:
    try:
        name_record = db.get(AppMetadata, "name")
        milestone_record = db.get(AppMetadata, "milestone")
    except SQLAlchemyError:
        raise DiagnosticUnavailable() from None
    if name_record is None or milestone_record is None:
        raise DiagnosticUnavailable()
    return SystemInfoResponse(
        name=name_record.value,
        milestone=milestone_record.value,
        source="postgresql",
    )
