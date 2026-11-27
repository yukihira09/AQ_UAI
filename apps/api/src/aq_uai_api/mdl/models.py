"""MDL persistence (M2). Mirrors migration ``0004_mdl_schema`` exactly.

Tenant isolation: every table carries ``institution_id`` and every reference uses a
composite foreign key ``(institution_id, <id>)``, so a row can never point at a
provider, model or user of another institution.

Immutability and append-only history are enforced by column-level grants in
``db/provision.py`` (the runtime login has no UPDATE on immutable columns, no UPDATE
on history tables and no DELETE anywhere), not by application convention.

Deliberately absent until its decision is taken (additive later, see
MDL_OPEN_DECISIONS): ``risk_basis_reference`` (D6). Routing ``decision_reference`` (D13)
was added in M5 (migration 0006). Agreement withdrawal (D5) is a separate append-only table (0005). No column may hold a prompt,
temperature or template (FR-MDL-040).
"""

from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from aq_uai_api.db.base import Base
from aq_uai_api.db.identity import UUIDPrimaryKey
from aq_uai_api.mdl.credentials import KEY_ID_PATTERN, MAX_SECRET_BYTES, NONCE_BYTES, TAG_BYTES

PROVIDER_TYPES = ("EXTERNAL", "INTERNAL")
API_STYLES = ("OPENAI_COMPATIBLE", "OPENAI_COMPATIBLE_V2")  # V2 added in M5 (0006)
AUTH_SCHEMES = ("BEARER", "HEADER_KEY", "NONE")
AGREEMENT_BASES = ("NO_TRAINING_COMMITMENT", "SCHOOL_WRITTEN_AUTHORIZATION")
RISK_LEVELS = ("HIGH", "MEDIUM", "LOW")
TEST_STATUSES = ("RUNNING", "PASSED", "FAILED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _trimmed(column: str) -> str:
    return f"{column} <> '' AND {column} !~ '^[[:space:]]|[[:space:]]$'"


def _user_fk(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["institution_id", column], ["users.institution_id", "users.id"], name=name
    )


def _timestamp() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class MdlProvider(UUIDPrimaryKey, Base):
    __tablename__ = "mdl_providers"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_providers_institution"
        ),
        sa.UniqueConstraint("institution_id", "id", name="uq_mdl_providers_institution_id"),
        sa.UniqueConstraint(
            "institution_id", "id", "provider_type", name="uq_mdl_providers_institution_id_type"
        ),
        sa.Index(
            "uq_mdl_providers_institution_name",
            "institution_id",
            sa.text("lower(name)"),
            unique=True,
        ),
        sa.CheckConstraint(_trimmed("name"), name="ck_mdl_providers_name"),
        sa.CheckConstraint(_in("provider_type", PROVIDER_TYPES), name="ck_mdl_providers_type"),
        sa.CheckConstraint(_in("api_style", API_STYLES), name="ck_mdl_providers_api_style"),
        sa.CheckConstraint(_in("auth_scheme", AUTH_SCHEMES), name="ck_mdl_providers_auth_scheme"),
        sa.CheckConstraint(
            """endpoint COLLATE "C" ~ '^https?://[^/?#@[:space:]]+([/?#]|$)' AND endpoint !~ '[[:space:]]'""",
            name="ck_mdl_providers_endpoint",
        ),
        sa.CheckConstraint(
            "(auth_scheme = 'HEADER_KEY') = (auth_header_name IS NOT NULL)",
            name="ck_mdl_providers_header_name_presence",
        ),
        sa.CheckConstraint(
            """auth_header_name COLLATE "C" ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$'""",
            name="ck_mdl_providers_header_name",
        ),
        sa.CheckConstraint("connection_version >= 1", name="ck_mdl_providers_connection_version"),
    )

    institution_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(sa.String(255))
    provider_type: Mapped[str] = mapped_column(sa.String(8))
    api_style: Mapped[str] = mapped_column(sa.String(32))
    endpoint: Mapped[str] = mapped_column(sa.String(2048))
    auth_scheme: Mapped[str] = mapped_column(sa.String(16))
    auth_header_name: Mapped[str | None] = mapped_column(sa.String(64))
    active: Mapped[bool] = mapped_column(server_default=sa.true())
    connection_version: Mapped[int] = mapped_column(server_default=sa.text("1"))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class MdlProviderCredential(Base):
    """One sealed secret per provider. Rotation overwrites it and bumps the version.

    Never map this class into a response model. ``credential_version`` starts at 1
    and is part of the AES-GCM associated data.
    """

    __tablename__ = "mdl_provider_credentials"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id"],
            ["mdl_providers.institution_id", "mdl_providers.id"],
            name="fk_mdl_provider_credentials_provider",
        ),
        _user_fk("updated_by", "fk_mdl_provider_credentials_updated_by"),
        sa.CheckConstraint(
            f"octet_length(nonce) = {NONCE_BYTES}", name="ck_mdl_provider_credentials_nonce"
        ),
        sa.CheckConstraint(
            f"octet_length(ciphertext) BETWEEN {TAG_BYTES + 1} AND {MAX_SECRET_BYTES + TAG_BYTES}",
            name="ck_mdl_provider_credentials_ciphertext",
        ),
        sa.CheckConstraint(
            f"""key_id COLLATE "C" ~ '^{KEY_ID_PATTERN}$'""",
            name="ck_mdl_provider_credentials_key_id",
        ),
        sa.CheckConstraint(
            "credential_version >= 1", name="ck_mdl_provider_credentials_version"
        ),
    )

    provider_id: Mapped[UUID] = mapped_column(primary_key=True)
    institution_id: Mapped[UUID]
    ciphertext: Mapped[bytes] = mapped_column(sa.LargeBinary)
    nonce: Mapped[bytes] = mapped_column(sa.LargeBinary)
    key_id: Mapped[str] = mapped_column(sa.String(32))
    credential_version: Mapped[int] = mapped_column(server_default=sa.text("1"))
    updated_by: Mapped[UUID]
    updated_at: Mapped[datetime] = _timestamp()

    def __repr__(self) -> str:
        return (
            f"MdlProviderCredential(provider_id={self.provider_id!r}, "
            f"key_id={self.key_id!r}, credential_version={self.credential_version!r})"
        )


class MdlProviderAgreement(UUIDPrimaryKey, Base):
    """Append-only DPA evidence (FR-MDL-030): basis plus document number, external only."""

    __tablename__ = "mdl_provider_agreements"
    __table_args__ = (
        # provider_type is copied and pinned to EXTERNAL; the composite key makes the
        # database refuse an agreement on an internal provider.
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id", "provider_type"],
            [
                "mdl_providers.institution_id",
                "mdl_providers.id",
                "mdl_providers.provider_type",
            ],
            name="fk_mdl_provider_agreements_provider",
        ),
        _user_fk("recorded_by", "fk_mdl_provider_agreements_recorded_by"),
        sa.CheckConstraint(
            "provider_type = 'EXTERNAL'", name="ck_mdl_provider_agreements_external"
        ),
        sa.CheckConstraint(_in("basis", AGREEMENT_BASES), name="ck_mdl_provider_agreements_basis"),
        sa.CheckConstraint(
            _trimmed("document_number"), name="ck_mdl_provider_agreements_document_number"
        ),
        sa.UniqueConstraint(
            "institution_id", "id", name="uq_mdl_provider_agreements_institution_id"
        ),
        sa.Index(
            "ix_mdl_provider_agreements_provider_recorded",
            "institution_id",
            "provider_id",
            "recorded_at",
        ),
    )

    institution_id: Mapped[UUID]
    provider_id: Mapped[UUID]
    provider_type: Mapped[str] = mapped_column(sa.String(8))
    basis: Mapped[str] = mapped_column(sa.String(32))
    document_number: Mapped[str] = mapped_column(sa.String(128))
    signed_on: Mapped[date | None]
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = _timestamp()


class MdlProviderAgreementWithdrawal(Base):
    """Append-only withdrawal of one agreement (D5, decided in M3; migration 0005).

    A separate INSERT-only table keeps agreements immutable: a withdrawal can be
    recorded once and can never be silently undone by an UPDATE.
    """

    __tablename__ = "mdl_provider_agreement_withdrawals"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "agreement_id"],
            ["mdl_provider_agreements.institution_id", "mdl_provider_agreements.id"],
            name="fk_mdl_agreement_withdrawals_agreement",
        ),
        _user_fk("withdrawn_by", "fk_mdl_agreement_withdrawals_withdrawn_by"),
    )

    agreement_id: Mapped[UUID] = mapped_column(primary_key=True)
    institution_id: Mapped[UUID]
    withdrawn_by: Mapped[UUID]
    withdrawn_at: Mapped[datetime] = _timestamp()


class MdlModel(UUIDPrimaryKey, Base):
    __tablename__ = "mdl_models"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id"],
            ["mdl_providers.institution_id", "mdl_providers.id"],
            name="fk_mdl_models_provider",
        ),
        sa.UniqueConstraint("institution_id", "id", name="uq_mdl_models_institution_id"),
        sa.UniqueConstraint("provider_id", "technical_id", name="uq_mdl_models_provider_technical"),
        sa.CheckConstraint(_trimmed("technical_id"), name="ck_mdl_models_technical_id"),
        sa.CheckConstraint(_trimmed("display_name"), name="ck_mdl_models_display_name"),
        sa.CheckConstraint(
            "supports_text OR supports_image OR supports_voice", name="ck_mdl_models_capability"
        ),
        sa.CheckConstraint(
            "max_output_tokens BETWEEN 1 AND 1000000", name="ck_mdl_models_max_output_tokens"
        ),
        sa.CheckConstraint(_in("risk_level", RISK_LEVELS), name="ck_mdl_models_risk_level"),
        sa.Index("ix_mdl_models_institution_provider", "institution_id", "provider_id"),
    )

    institution_id: Mapped[UUID]
    provider_id: Mapped[UUID]
    technical_id: Mapped[str] = mapped_column(sa.String(255))
    display_name: Mapped[str] = mapped_column(sa.String(255))
    supports_text: Mapped[bool] = mapped_column(server_default=sa.false())
    supports_image: Mapped[bool] = mapped_column(server_default=sa.false())
    supports_voice: Mapped[bool] = mapped_column(server_default=sa.false())
    max_output_tokens: Mapped[int | None]
    # NULL means "not classified". No default and no vendor-derived value (FR-MDL-031).
    risk_level: Mapped[str | None] = mapped_column(sa.String(6))
    active: Mapped[bool] = mapped_column(server_default=sa.true())
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class MdlConnectionTest(UUIDPrimaryKey, Base):
    """One connection-test attempt. No response body or secret is ever stored."""

    __tablename__ = "mdl_connection_tests"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id", "model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_connection_tests_model",
        ),
        _user_fk("started_by", "fk_mdl_connection_tests_started_by"),
        sa.CheckConstraint(_in("status", TEST_STATUSES), name="ck_mdl_connection_tests_status"),
        sa.CheckConstraint(
            "(status = 'RUNNING') = (finished_at IS NULL)",
            name="ck_mdl_connection_tests_finished",
        ),
        sa.CheckConstraint(
            "(status = 'FAILED') = (error_code IS NOT NULL)",
            name="ck_mdl_connection_tests_error_code_presence",
        ),
        sa.CheckConstraint(
            """error_code COLLATE "C" ~ '^[A-Z][A-Z_]{0,39}$'""",
            name="ck_mdl_connection_tests_error_code",
        ),
        sa.CheckConstraint(
            "http_status_class BETWEEN 1 AND 5", name="ck_mdl_connection_tests_http_class"
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_mdl_connection_tests_latency"),
        sa.CheckConstraint(
            "connection_version >= 1 AND (credential_version IS NULL OR credential_version >= 1)",
            name="ck_mdl_connection_tests_versions",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_mdl_connection_tests_order",
        ),
        # At most one test in flight per model.
        sa.Index(
            "uq_mdl_connection_tests_running",
            "model_id",
            unique=True,
            postgresql_where=sa.text("status = 'RUNNING'"),
        ),
        sa.Index(
            "ix_mdl_connection_tests_model_started", "institution_id", "model_id", "started_at"
        ),
    )

    institution_id: Mapped[UUID]
    model_id: Mapped[UUID]
    # Snapshot of the provider state the test ran against ("current test" is derived).
    connection_version: Mapped[int]
    credential_version: Mapped[int | None]
    status: Mapped[str] = mapped_column(sa.String(7), server_default="RUNNING")
    error_code: Mapped[str | None] = mapped_column(sa.String(40))
    http_status_class: Mapped[int | None] = mapped_column(sa.SmallInteger)
    latency_ms: Mapped[int | None]
    started_by: Mapped[UUID]
    started_at: Mapped[datetime] = _timestamp()
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class MdlRouting(Base):
    """Institution-wide primary/fallback singleton (D8). One row per institution."""

    __tablename__ = "mdl_routing"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_routing_institution"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "primary_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_primary_model",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "fallback_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_fallback_model",
        ),
        _user_fk("updated_by", "fk_mdl_routing_updated_by"),
        sa.CheckConstraint(
            "fallback_model_id IS NULL OR "
            "(primary_model_id IS NOT NULL AND fallback_model_id <> primary_model_id)",
            name="ck_mdl_routing_fallback",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_mdl_routing_revision"),
    )

    institution_id: Mapped[UUID] = mapped_column(primary_key=True)
    primary_model_id: Mapped[UUID | None]
    fallback_model_id: Mapped[UUID | None]
    revision: Mapped[int]
    updated_by: Mapped[UUID]
    updated_at: Mapped[datetime] = _timestamp()


class MdlRoutingRevision(UUIDPrimaryKey, Base):
    """Append-only routing history (FR-MDL-021): who, when, before and after.

    Display names are snapshots so history stays readable after a model is renamed.
    """

    __tablename__ = "mdl_routing_revisions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_routing_revisions_institution"
        ),
        _user_fk("changed_by", "fk_mdl_routing_revisions_changed_by"),
        *(
            sa.ForeignKeyConstraint(
                ["institution_id", column],
                ["mdl_models.institution_id", "mdl_models.id"],
                name=f"fk_mdl_routing_revisions_{column.removesuffix('_model_id')}",
            )
            for column in (
                "before_primary_model_id",
                "before_fallback_model_id",
                "after_primary_model_id",
                "after_fallback_model_id",
            )
        ),
        sa.UniqueConstraint(
            "institution_id", "revision", name="uq_mdl_routing_revisions_institution_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_mdl_routing_revisions_revision"),
        sa.CheckConstraint(
            "(before_primary_model_id IS NULL) = (before_primary_name IS NULL) "
            "AND (before_fallback_model_id IS NULL) = (before_fallback_name IS NULL) "
            "AND (after_primary_model_id IS NULL) = (after_primary_name IS NULL) "
            "AND (after_fallback_model_id IS NULL) = (after_fallback_name IS NULL)",
            name="ck_mdl_routing_revisions_snapshots",
        ),
        sa.CheckConstraint(
            "after_fallback_model_id IS NULL OR (after_primary_model_id IS NOT NULL "
            "AND after_fallback_model_id <> after_primary_model_id)",
            name="ck_mdl_routing_revisions_after_fallback",
        ),
        sa.CheckConstraint(
            _trimmed("decision_reference"), name="ck_mdl_routing_revisions_decision_reference"
        ),
    )

    institution_id: Mapped[UUID]
    revision: Mapped[int]
    before_primary_model_id: Mapped[UUID | None]
    before_fallback_model_id: Mapped[UUID | None]
    after_primary_model_id: Mapped[UUID | None]
    after_fallback_model_id: Mapped[UUID | None]
    before_primary_name: Mapped[str | None] = mapped_column(sa.String(255))
    before_fallback_name: Mapped[str | None] = mapped_column(sa.String(255))
    after_primary_name: Mapped[str | None] = mapped_column(sa.String(255))
    after_fallback_name: Mapped[str | None] = mapped_column(sa.String(255))
    # D13 (M5): optional number of the school's decision document (actor phụ: the Board
    # decides outside the system and its document number is recorded here).
    decision_reference: Mapped[str | None] = mapped_column(sa.String(128))
    changed_by: Mapped[UUID]
    changed_at: Mapped[datetime] = _timestamp()
