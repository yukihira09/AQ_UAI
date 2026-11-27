"""Create the MDL provider, credential, agreement, model, test and routing tables.

Revision ID: 0004_mdl_schema
Revises: 0003_mdl_access_catalog
Create Date: 2026-11-25

Additive only: seven new, empty tables; no existing table or row changes and no seed
data (FR-MDL-031 AC2). Every reference is a composite (institution_id, id) foreign
key. Runtime grants (no DELETE anywhere; history INSERT-only; immutable columns not
updatable) are applied by ``aq_uai_api.db.provision.apply_runtime_privileges``.
Credential ciphertext only: the encryption key never reaches the database.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_mdl_schema"
down_revision = "0003_mdl_access_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mdl_providers",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=8), nullable=False),
        sa.Column("api_style", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("auth_scheme", sa.String(length=16), nullable=False),
        sa.Column("auth_header_name", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("connection_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(auth_scheme = 'HEADER_KEY') = (auth_header_name IS NOT NULL)",
            name="ck_mdl_providers_header_name_presence",
        ),
        sa.CheckConstraint("api_style IN ('OPENAI_COMPATIBLE')", name="ck_mdl_providers_api_style"),
        sa.CheckConstraint(
            "auth_scheme IN ('BEARER', 'HEADER_KEY', 'NONE')", name="ck_mdl_providers_auth_scheme"
        ),
        sa.CheckConstraint(
            "name <> '' AND name !~ '^[[:space:]]|[[:space:]]$'", name="ck_mdl_providers_name"
        ),
        sa.CheckConstraint(
            "provider_type IN ('EXTERNAL', 'INTERNAL')", name="ck_mdl_providers_type"
        ),
        sa.CheckConstraint(
            "auth_header_name COLLATE \"C\" ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$'",
            name="ck_mdl_providers_header_name",
        ),
        sa.CheckConstraint("connection_version >= 1", name="ck_mdl_providers_connection_version"),
        sa.CheckConstraint(
            "endpoint COLLATE \"C\" ~ '^https?://[^/?#@[:space:]]+([/?#]|$)' AND endpoint !~ '[[:space:]]'",
            name="ck_mdl_providers_endpoint",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_providers_institution"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id", "id", "provider_type", name="uq_mdl_providers_institution_id_type"
        ),
        sa.UniqueConstraint("institution_id", "id", name="uq_mdl_providers_institution_id"),
    )
    op.create_index(
        "uq_mdl_providers_institution_name",
        "mdl_providers",
        ["institution_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "mdl_models",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("technical_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("supports_text", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_image", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_voice", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=6), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "display_name <> '' AND display_name !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_mdl_models_display_name",
        ),
        sa.CheckConstraint(
            "risk_level IN ('HIGH', 'MEDIUM', 'LOW')", name="ck_mdl_models_risk_level"
        ),
        sa.CheckConstraint(
            "technical_id <> '' AND technical_id !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_mdl_models_technical_id",
        ),
        sa.CheckConstraint(
            "max_output_tokens BETWEEN 1 AND 1000000", name="ck_mdl_models_max_output_tokens"
        ),
        sa.CheckConstraint(
            "supports_text OR supports_image OR supports_voice", name="ck_mdl_models_capability"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id"],
            ["mdl_providers.institution_id", "mdl_providers.id"],
            name="fk_mdl_models_provider",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("institution_id", "id", name="uq_mdl_models_institution_id"),
        sa.UniqueConstraint("provider_id", "technical_id", name="uq_mdl_models_provider_technical"),
    )
    op.create_index(
        "ix_mdl_models_institution_provider",
        "mdl_models",
        ["institution_id", "provider_id"],
        unique=False,
    )
    op.create_table(
        "mdl_connection_tests",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("connection_version", sa.Integer(), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=7), server_default="RUNNING", nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("http_status_class", sa.SmallInteger(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_by", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(status = 'FAILED') = (error_code IS NOT NULL)",
            name="ck_mdl_connection_tests_error_code_presence",
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING') = (finished_at IS NULL)", name="ck_mdl_connection_tests_finished"
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'PASSED', 'FAILED')", name="ck_mdl_connection_tests_status"
        ),
        sa.CheckConstraint(
            "connection_version >= 1 AND (credential_version IS NULL OR credential_version >= 1)",
            name="ck_mdl_connection_tests_versions",
        ),
        sa.CheckConstraint(
            "error_code COLLATE \"C\" ~ '^[A-Z][A-Z_]{0,39}$'",
            name="ck_mdl_connection_tests_error_code",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="ck_mdl_connection_tests_order"
        ),
        sa.CheckConstraint(
            "http_status_class BETWEEN 1 AND 5", name="ck_mdl_connection_tests_http_class"
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_mdl_connection_tests_latency"),
        sa.ForeignKeyConstraint(
            ["institution_id", "model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_connection_tests_model",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "started_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_connection_tests_started_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mdl_connection_tests_model_started",
        "mdl_connection_tests",
        ["institution_id", "model_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "uq_mdl_connection_tests_running",
        "mdl_connection_tests",
        ["model_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_table(
        "mdl_provider_agreements",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(length=8), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("document_number", sa.String(length=128), nullable=False),
        sa.Column("signed_on", sa.Date(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "basis IN ('NO_TRAINING_COMMITMENT', 'SCHOOL_WRITTEN_AUTHORIZATION')",
            name="ck_mdl_provider_agreements_basis",
        ),
        sa.CheckConstraint(
            "document_number <> '' AND document_number !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_mdl_provider_agreements_document_number",
        ),
        sa.CheckConstraint(
            "provider_type = 'EXTERNAL'", name="ck_mdl_provider_agreements_external"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id", "provider_type"],
            ["mdl_providers.institution_id", "mdl_providers.id", "mdl_providers.provider_type"],
            name="fk_mdl_provider_agreements_provider",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "recorded_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_provider_agreements_recorded_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mdl_provider_agreements_provider_recorded",
        "mdl_provider_agreements",
        ["institution_id", "provider_id", "recorded_at"],
        unique=False,
    )
    op.create_table(
        "mdl_provider_credentials",
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(length=32), nullable=False),
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("credential_version >= 1", name="ck_mdl_provider_credentials_version"),
        sa.CheckConstraint(
            "key_id COLLATE \"C\" ~ '^[a-z0-9][a-z0-9_-]{0,31}$'",
            name="ck_mdl_provider_credentials_key_id",
        ),
        sa.CheckConstraint(
            "octet_length(ciphertext) BETWEEN 17 AND 4112",
            name="ck_mdl_provider_credentials_ciphertext",
        ),
        sa.CheckConstraint("octet_length(nonce) = 12", name="ck_mdl_provider_credentials_nonce"),
        sa.ForeignKeyConstraint(
            ["institution_id", "provider_id"],
            ["mdl_providers.institution_id", "mdl_providers.id"],
            name="fk_mdl_provider_credentials_provider",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "updated_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_provider_credentials_updated_by",
        ),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    op.create_table(
        "mdl_routing",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("primary_model_id", sa.Uuid(), nullable=True),
        sa.Column("fallback_model_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fallback_model_id IS NULL OR (primary_model_id IS NOT NULL AND fallback_model_id <> primary_model_id)",
            name="ck_mdl_routing_fallback",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_mdl_routing_revision"),
        sa.ForeignKeyConstraint(
            ["institution_id", "fallback_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_fallback_model",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "primary_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_primary_model",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "updated_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_routing_updated_by",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_routing_institution"
        ),
        sa.PrimaryKeyConstraint("institution_id"),
    )
    op.create_table(
        "mdl_routing_revisions",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("before_primary_model_id", sa.Uuid(), nullable=True),
        sa.Column("before_fallback_model_id", sa.Uuid(), nullable=True),
        sa.Column("after_primary_model_id", sa.Uuid(), nullable=True),
        sa.Column("after_fallback_model_id", sa.Uuid(), nullable=True),
        sa.Column("before_primary_name", sa.String(length=255), nullable=True),
        sa.Column("before_fallback_name", sa.String(length=255), nullable=True),
        sa.Column("after_primary_name", sa.String(length=255), nullable=True),
        sa.Column("after_fallback_name", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(before_primary_model_id IS NULL) = (before_primary_name IS NULL) AND (before_fallback_model_id IS NULL) = (before_fallback_name IS NULL) AND (after_primary_model_id IS NULL) = (after_primary_name IS NULL) AND (after_fallback_model_id IS NULL) = (after_fallback_name IS NULL)",
            name="ck_mdl_routing_revisions_snapshots",
        ),
        sa.CheckConstraint(
            "after_fallback_model_id IS NULL OR (after_primary_model_id IS NOT NULL AND after_fallback_model_id <> after_primary_model_id)",
            name="ck_mdl_routing_revisions_after_fallback",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_mdl_routing_revisions_revision"),
        sa.ForeignKeyConstraint(
            ["institution_id", "after_fallback_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_revisions_after_fallback",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "after_primary_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_revisions_after_primary",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "before_fallback_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_revisions_before_fallback",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "before_primary_model_id"],
            ["mdl_models.institution_id", "mdl_models.id"],
            name="fk_mdl_routing_revisions_before_primary",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "changed_by"],
            ["users.institution_id", "users.id"],
            name="fk_mdl_routing_revisions_changed_by",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name="fk_mdl_routing_revisions_institution"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id", "revision", name="uq_mdl_routing_revisions_institution_revision"
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the MDL schema would destroy append-only routing history and sealed "
        "credentials. Restore a verified pre-0004 backup to a separate database instead."
    )
