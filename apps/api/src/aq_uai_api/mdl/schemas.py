"""MDL request and response contracts (M3).

Inputs forbid unknown fields, so a ``prompt``, ``temperature`` or ``template`` field
can never be accepted (FR-MDL-040) and immutable fields such as ``provider_type`` or
``technical_id`` cannot be edited. Secrets arrive only as ``SecretStr`` and no
response model has a field that could carry one (FR-MDL-010, RULE-MDL-04).
"""

from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from aq_uai_api.directory.schemas import Input, Name, PageParams, clean_text
from aq_uai_api.mdl.credentials import MAX_SECRET_BYTES, InvalidEndpoint, endpoint_origin

ProviderType = Literal["EXTERNAL", "INTERNAL"]
ApiStyle = Literal["OPENAI_COMPATIBLE", "OPENAI_COMPATIBLE_V2"]
AuthScheme = Literal["BEARER", "HEADER_KEY", "NONE"]
Capability = Literal["TEXT", "IMAGE", "VOICE"]
RiskLevel = Literal["HIGH", "MEDIUM", "LOW"]
AgreementBasis = Literal["NO_TRAINING_COMMITMENT", "SCHOOL_WRITTEN_AUTHORIZATION"]
CredentialStatus = Literal["NOT_REQUIRED", "MISSING", "STORED", "UNREADABLE"]
SECRET_SCHEMES = frozenset({"BEARER", "HEADER_KEY"})
CAPABILITY_ORDER = ("TEXT", "IMAGE", "VOICE")

# Headers that frame or route the request, or that the client sets itself. A stored
# secret must never be placed in them (request smuggling, host confusion, cookies).
FORBIDDEN_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "content-type",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "te",
        "trailer",
        "upgrade",
        "expect",
        "cookie",
        "proxy-authorization",
        "proxy-connection",
        "accept-encoding",
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-real-ip",
    }
)


def canonical_endpoint(value: str) -> str:
    """Validate the syntax and canonicalise scheme/host/port. Egress policy is M4."""
    clean_text(value)
    if any(character.isspace() for character in value):
        raise ValueError("The endpoint must not contain spaces.")
    try:
        origin = endpoint_origin(value)
    except InvalidEndpoint:
        raise ValueError("Enter an absolute http or https endpoint.") from None
    parts = urlsplit(value)
    if parts.query or parts.fragment or "?" in value or "#" in value:
        raise ValueError("The endpoint must not contain a query or fragment.")
    return origin + parts.path.rstrip("/")


def header_name(value: str) -> str:
    if value.lower() in FORBIDDEN_HEADERS:
        raise ValueError("This header cannot carry a credential.")
    return value


Endpoint = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2048),
    AfterValidator(canonical_endpoint),
]
HeaderName = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"),
    AfterValidator(header_name),
]
TechnicalId = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(clean_text),
]
DocumentNumber = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128),
    AfterValidator(clean_text),
]
Secret = Annotated[SecretStr, Field(max_length=MAX_SECRET_BYTES)]
Tokens = Annotated[int, Field(strict=True, ge=1, le=1_000_000)]


def blank_secret_is_absent(value: SecretStr | None) -> SecretStr | None:
    """FR-MDL-010: an empty secret field on edit means "keep the stored value"."""
    if value is None or not value.get_secret_value().strip():
        return None
    return value


def ordered_capabilities(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("Capabilities must be distinct.")
    return [item for item in CAPABILITY_ORDER if item in value]


class _ProviderShape(Input):
    @model_validator(mode="after")
    def header_name_matches_scheme(self):
        scheme = getattr(self, "auth_scheme", None)
        header = getattr(self, "auth_header_name", None)
        if scheme is not None and (scheme == "HEADER_KEY") != (header is not None):
            raise ValueError("A header name is required for, and only for, HEADER_KEY.")
        return self


class CreateProvider(_ProviderShape):
    name: Name
    provider_type: ProviderType
    api_style: ApiStyle = "OPENAI_COMPATIBLE"
    endpoint: Endpoint
    auth_scheme: AuthScheme
    auth_header_name: HeaderName | None = None
    secret: Secret | None = None

    @field_validator("secret")
    @classmethod
    def blank_secret_keeps_stored_value(cls, value: SecretStr | None) -> SecretStr | None:
        return blank_secret_is_absent(value)


class ProviderPatch(Input):
    """Partial edit. ``provider_type`` is immutable and therefore not accepted."""

    name: Name | None = None
    api_style: ApiStyle | None = None
    endpoint: Endpoint | None = None
    auth_scheme: AuthScheme | None = None
    auth_header_name: HeaderName | None = None
    secret: Secret | None = None

    @field_validator("secret")
    @classmethod
    def blank_secret_keeps_stored_value(cls, value: SecretStr | None) -> SecretStr | None:
        return blank_secret_is_absent(value)

    @model_validator(mode="after")
    def supplied_fields_are_meaningful(self):
        required = {"name", "api_style", "endpoint", "auth_scheme"}
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set & required
        ):
            raise ValueError("Supply at least one field; required fields cannot be null.")
        return self


class AgreementIn(Input):
    basis: AgreementBasis
    document_number: DocumentNumber
    signed_on: date | None = None


class CreateModel(Input):
    provider_id: UUID
    technical_id: TechnicalId
    display_name: Name
    capabilities: list[Capability] = Field(min_length=1, max_length=3)
    max_output_tokens: Tokens | None = None
    risk_level: RiskLevel | None = None

    @field_validator("capabilities")
    @classmethod
    def distinct_capabilities(cls, value: list[str]) -> list[str]:
        return ordered_capabilities(value)


class ModelPatch(Input):
    """Partial edit. ``technical_id`` and ``provider_id`` are immutable."""

    display_name: Name | None = None
    capabilities: list[Capability] | None = Field(default=None, min_length=1, max_length=3)
    max_output_tokens: Tokens | None = None  # explicit null clears the limit
    risk_level: RiskLevel | None = None  # explicit null means "not classified"

    @field_validator("capabilities")
    @classmethod
    def distinct_capabilities(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else ordered_capabilities(value)

    @model_validator(mode="after")
    def supplied_fields_are_meaningful(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None
            for field in self.model_fields_set & {"display_name", "capabilities"}
        ):
            raise ValueError("Supply at least one field; required fields cannot be null.")
        return self


class ProviderFilters(PageParams):
    active: bool | None = None
    provider_type: ProviderType | None = None


class ModelFilters(PageParams):
    provider_id: UUID | None = None
    active: bool | None = None
    risk_level: RiskLevel | Literal["UNCLASSIFIED"] | None = None
    # M5: only models that may be selected now (FR-MDL-021 AC1: the selection list).
    routing_eligible: bool | None = None


DecisionReference = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128),
    AfterValidator(clean_text),
]


class RoutingIn(Input):
    """``PUT /routing``. Optimistic concurrency: send the revision you last read (0 when
    routing was never configured); a different current revision gives 409.

    A slot whose model is unchanged is kept as it is, even if that model is no longer
    usable (route persistence, D9); every *new* slot value must be eligible now.
    """

    expected_revision: Annotated[int, Field(strict=True, ge=0)]
    primary_model_id: UUID | None
    fallback_model_id: UUID | None = None
    decision_reference: DecisionReference | None = None  # D13, optional

    @model_validator(mode="after")
    def fallback_needs_primary(self):
        if self.fallback_model_id is not None and self.primary_model_id is None:
            raise ValueError("A fallback model needs a primary model.")
        return self


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgreementOut(Output):
    id: UUID
    provider_id: UUID
    basis: AgreementBasis
    document_number: str
    signed_on: date | None
    recorded_by: UUID
    recorded_at: datetime
    withdrawn_by: UUID | None
    withdrawn_at: datetime | None
    in_force: bool


class WithdrawalOut(Output):
    agreement: AgreementOut
    # Routing slots that use this provider's models. Withdrawal does not clear them
    # (D5); it invalidates future eligibility and the UI must warn (M5/M6).
    affected_routing: list[str]


class ProviderOut(Output):
    id: UUID
    name: str
    provider_type: ProviderType
    api_style: ApiStyle
    endpoint: str
    auth_scheme: AuthScheme
    auth_header_name: str | None
    active: bool
    connection_version: int
    has_credential: bool
    credential_status: CredentialStatus
    credential_updated_at: datetime | None
    agreement_in_force: AgreementOut | None
    created_at: datetime
    updated_at: datetime


class ConnectionTestIn(Input):
    """Body of ``POST /models/{id}/connection-tests``.

    D4: an external provider may bill the school's API account for the test even though
    no AQ EduUAI allowance is used. The client must show that notice and send ``true``
    here before an external provider is called. Internal providers do not need it.
    """

    acknowledge_provider_charges: Annotated[bool, Field(strict=True)] = False


TestStatus = Literal["RUNNING", "PASSED", "FAILED"]


class ConnectionTestOut(Output):
    """One test attempt. No provider response text, header or secret is ever stored."""

    id: UUID
    model_id: UUID
    status: TestStatus
    error_code: str | None
    http_status_class: int | None
    latency_ms: int | None
    connection_version: int
    credential_version: int | None
    # True when the snapshot matches the provider's present connection and credential
    # versions, so this result still describes the stored configuration.
    current: bool
    started_by: UUID
    started_at: datetime
    finished_at: datetime | None


class ConnectionTestState(Output):
    """Derived, never cached (architecture section 2).

    ``result``: ``PASSED``/``FAILED`` from the latest finished test that is current;
    ``OUTDATED`` when tests exist but none matches the present configuration;
    ``NOT_TESTED``; ``UNSUPPORTED`` for models without TEXT (D3: only text is tested,
    and no image or voice verification is ever claimed).
    """

    result: Literal["PASSED", "FAILED", "OUTDATED", "NOT_TESTED", "UNSUPPORTED"]
    test_id: UUID | None
    error_code: str | None
    finished_at: datetime | None
    running: bool


class RoutingEligibility(Output):
    """Whether the model could be selected as primary or fallback **now** (M5).

    ``issues`` are fixed codes: ``model_inactive``, ``provider_inactive``,
    ``text_unsupported``, ``risk_unclassified``, ``not_tested``, ``test_outdated``,
    ``test_failed``, ``dpa_missing``, ``credential_unavailable``, ``endpoint_blocked``.
    """

    eligible: bool
    issues: list[str]


class ModelOut(Output):
    id: UUID
    provider_id: UUID
    technical_id: str
    display_name: str
    capabilities: list[Capability]
    max_output_tokens: int | None
    risk_level: RiskLevel | None
    active: bool
    connection_test: ConnectionTestState
    routing: RoutingEligibility
    created_at: datetime
    updated_at: datetime


class EgressStatus(Output):
    """Policy summary for administrators. Allowlist entries are not listed."""

    external: Literal["HTTPS_PUBLIC_ONLY"] = "HTTPS_PUBLIC_ONLY"
    internal_allowlist: Literal["EMPTY", "CONFIGURED", "INVALID"]
    internal_allowlist_entries: int
    internal_ca: Literal["NONE", "CONFIGURED", "UNREADABLE"] = "NONE"
    redirects: Literal["REFUSED"] = "REFUSED"
    retries: int = 0
    timeout_seconds: float
    max_response_bytes: int


class StatusOut(Output):
    credential_keys: Literal["AVAILABLE", "UNAVAILABLE"]
    active_key_id: str | None
    egress: EgressStatus


class RoutingSlotOut(Output):
    """One configured slot. ``usable`` is the permission to send traffic to it now; it is
    evaluated on every read with the same rules as a new selection (fail closed)."""

    model_id: UUID
    display_name: str
    provider_id: UUID
    provider_name: str
    usable: bool
    issues: list[str]


class EffectiveRoute(Output):
    """What a caller may use right now: the primary if usable, else the fallback if
    usable, else nothing. Configuration is never changed automatically."""

    state: Literal["PRIMARY", "FALLBACK", "UNAVAILABLE", "NOT_CONFIGURED"]
    model_id: UUID | None


class RoutingOut(Output):
    revision: int
    primary: RoutingSlotOut | None
    fallback: RoutingSlotOut | None
    effective: EffectiveRoute
    updated_by: UUID | None
    updated_at: datetime | None


class RoutingRevisionOut(Output):
    id: UUID
    revision: int
    before_primary_model_id: UUID | None
    before_primary_name: str | None
    before_fallback_model_id: UUID | None
    before_fallback_name: str | None
    after_primary_model_id: UUID | None
    after_primary_name: str | None
    after_fallback_model_id: UUID | None
    after_fallback_name: str | None
    decision_reference: str | None
    changed_by: UUID
    changed_at: datetime


# M7 (FRD §6 "Should": configuration version history with diff). A read-only projection
# of the institution's MDL configuration audit events; ``changes`` is the action's typed,
# allowlisted payload (``db.audit.public_audit_changes``), so it can never carry a secret,
# ciphertext, full endpoint path or provider response text.
HistoryTargetType = Literal["mdl_provider", "mdl_model", "mdl_agreement", "mdl_routing_revision"]


class HistoryFilters(PageParams):
    target_type: HistoryTargetType | None = None
    target_id: UUID | None = None


class ConfigurationEventOut(Output):
    id: UUID
    action: str
    target_type: str
    target_id: UUID | None
    actor_id: UUID | None
    occurred_at: datetime
    changes: dict[str, object]
