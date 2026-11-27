"""MDL writes (M3): providers, credentials, agreements and models.

What: every write runs through the shared ``protected`` transaction (session, Origin,
CSRF and transaction-time ``mdl.manage`` re-check) and writes its typed audit event in
the same transaction, so a failed audit rolls the change back.

Credential rules (FR-MDL-010, D2, D14):
- a secret-bearing scheme (BEARER, HEADER_KEY) needs a secret on create;
- a blank secret on edit keeps the stored one;
- a new secret is required when the endpoint origin changes or the scheme changes to a
  secret-bearing one, so a stored secret can never be redirected to another host;
- every stored secret bumps ``credential_version``; endpoint, API style, scheme or
  header changes bump ``connection_version`` (used by M4 to decide "current test").

No network call happens here (M4), and nothing here touches quota or credit data.
"""

from uuid import UUID

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.authorization.writes import WriteContext, protected, record
from aq_uai_api.db import audit
from aq_uai_api.directory.queries import one
from aq_uai_api.mdl import egress, queries, schemas, usage
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    CredentialKeysUnavailable,
    InvalidCredentialValue,
    KeyRing,
    endpoint_origin,
    load_key_ring,
)
from aq_uai_api.mdl.models import (
    MdlModel,
    MdlProvider,
    MdlProviderAgreement,
    MdlProviderAgreementWithdrawal,
    MdlProviderCredential,
)

SECRET_SCHEMES = schemas.SECRET_SCHEMES


def _manager(authority: ActorAuthority) -> UUID:
    authority.require_institution(P.MDL_MANAGE, authority.institution_id)
    return authority.institution_id


def _keys(context: WriteContext) -> KeyRing:
    try:
        return load_key_ring(context.settings)
    except CredentialKeysUnavailable:
        raise DomainError(ErrorCode.MDL_CREDENTIAL_UNAVAILABLE) from None


def _flush(db: Session, duplicate: ErrorCode = ErrorCode.MDL_DUPLICATE) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError(duplicate) from None
        raise


def _require_https(provider_type: str, endpoint: str, auth_scheme: str) -> None:
    """Registration-time transport rule. External providers always use https; a provider
    that sends a stored secret uses https too, internal ones included (M5 review: no
    credential in clear text on any network). Full egress validation (address ranges,
    allowlist, DNS pinning) happens at connect time (``mdl.egress``)."""
    try:
        # Host forms the egress layer always refuses (Unicode, numeric, malformed) and,
        # for external providers, the fixed static rules (443, public DNS name) are
        # rejected now instead of failing every later test (M5 review of M3).
        target = egress.parse_target(endpoint)
        if provider_type == "EXTERNAL":
            egress.EgressPolicy().check_target("EXTERNAL", target)
    except egress.EgressBlocked:
        raise DomainError(ErrorCode.MDL_ENDPOINT_BLOCKED) from None
    if target.scheme != "https" and auth_scheme in SECRET_SCHEMES:
        raise DomainError(ErrorCode.MDL_ENDPOINT_BLOCKED)


def _store_secret(
    db: Session,
    keys: KeyRing,
    provider: MdlProvider,
    secret: SecretStr,
    credential: MdlProviderCredential | None,
    actor_id: UUID,
) -> int:
    version = credential.credential_version + 1 if credential else 1
    binding = CredentialBinding(
        institution_id=provider.institution_id,
        provider_id=provider.id,
        endpoint_origin=endpoint_origin(provider.endpoint),
        credential_version=version,
    )
    try:
        sealed = keys.seal(secret, binding)
    except InvalidCredentialValue:
        raise DomainError(ErrorCode.VALIDATION_FAILED) from None
    if credential is None:
        db.add(
            MdlProviderCredential(
                provider_id=provider.id,
                institution_id=provider.institution_id,
                ciphertext=sealed.ciphertext,
                nonce=sealed.nonce,
                key_id=sealed.key_id,
                credential_version=version,
                updated_by=actor_id,
            )
        )
    else:
        credential.ciphertext = sealed.ciphertext
        credential.nonce = sealed.nonce
        credential.key_id = sealed.key_id
        credential.credential_version = version
        credential.updated_by = actor_id
        credential.updated_at = sa.func.now()
    db.flush()
    return version


def _provider_fields(provider: MdlProvider) -> audit.ProviderFields:
    return audit.ProviderFields(
        name=provider.name,
        api_style=provider.api_style,
        endpoint_origin=endpoint_origin(provider.endpoint),
        auth_scheme=provider.auth_scheme,
        auth_header_name=provider.auth_header_name,
    )


def _locked_provider(db: Session, tenant: UUID, provider_id: UUID) -> MdlProvider:
    return one(
        db, queries.provider_query(tenant).where(MdlProvider.id == provider_id).with_for_update()
    )


def _locked_credential(db: Session, provider_id: UUID) -> MdlProviderCredential | None:
    return db.scalar(
        sa.select(MdlProviderCredential)
        .where(MdlProviderCredential.provider_id == provider_id)
        .with_for_update()
    )


def create_provider(context: WriteContext, payload: schemas.CreateProvider) -> schemas.ProviderOut:
    needs_secret = payload.auth_scheme in SECRET_SCHEMES
    if payload.secret is not None and not needs_secret:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        _require_https(payload.provider_type, payload.endpoint, payload.auth_scheme)
        if needs_secret and payload.secret is None:
            raise DomainError(ErrorCode.MDL_CREDENTIAL_REQUIRED)
        keys = _keys(context) if needs_secret else queries.key_ring_or_none(context.settings)
        provider = MdlProvider(
            institution_id=tenant,
            name=payload.name,
            provider_type=payload.provider_type,
            api_style=payload.api_style,
            endpoint=payload.endpoint,
            auth_scheme=payload.auth_scheme,
            auth_header_name=payload.auth_header_name,
        )
        db.add(provider)
        _flush(db)
        if needs_secret:
            _store_secret(db, keys, provider, payload.secret, None, authority.actor_id)
        record(
            db,
            context,
            authority,
            audit.AuditAction.MDL_PROVIDER_CREATED,
            provider.id,
            audit.ProviderCreated(
                **_provider_fields(provider).model_dump(),
                provider_type=provider.provider_type,
                has_credential=needs_secret,
            ),
        )
        return queries.provider_out(db, provider, keys)


def update_provider(
    context: WriteContext, provider_id: UUID, payload: schemas.ProviderPatch
) -> schemas.ProviderOut:
    changes = payload.model_dump(exclude_unset=True, exclude={"secret"})
    secret = payload.secret
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        provider = _locked_provider(db, tenant, provider_id)
        credential = _locked_credential(db, provider.id)

        scheme = changes.get("auth_scheme", provider.auth_scheme)
        if scheme == "HEADER_KEY":
            header = changes.get("auth_header_name", provider.auth_header_name)
            if header is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
        elif changes.get("auth_header_name") is not None:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        else:
            header = None
        endpoint = changes.get("endpoint", provider.endpoint)
        _require_https(provider.provider_type, endpoint, scheme)
        if secret is not None and scheme not in SECRET_SCHEMES:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        origin_changed = endpoint_origin(endpoint) != endpoint_origin(provider.endpoint)
        scheme_changed = scheme != provider.auth_scheme
        if (
            scheme in SECRET_SCHEMES
            and secret is None
            and (credential is None or origin_changed or scheme_changed)
        ):
            raise DomainError(ErrorCode.MDL_CREDENTIAL_REQUIRED)
        keys = _keys(context) if secret is not None else queries.key_ring_or_none(context.settings)

        before = _provider_fields(provider)
        endpoint_changed = endpoint != provider.endpoint
        material = (
            endpoint_changed
            or scheme_changed
            or header != provider.auth_header_name
            or changes.get("api_style", provider.api_style) != provider.api_style
        )
        provider.name = changes.get("name", provider.name)
        provider.api_style = changes.get("api_style", provider.api_style)
        provider.endpoint = endpoint
        provider.auth_scheme = scheme
        provider.auth_header_name = header
        after = _provider_fields(provider)
        if material:
            provider.connection_version += 1
        if material or before != after:
            provider.updated_at = sa.func.now()
            _flush(db)
            db.refresh(provider)
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_PROVIDER_UPDATED,
                provider.id,
                audit.ProviderChange(
                    before=before,
                    after=after,
                    endpoint_changed=endpoint_changed,
                    connection_version=provider.connection_version,
                ),
            )
        if secret is not None:
            version = _store_secret(db, keys, provider, secret, credential, authority.actor_id)
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_PROVIDER_CREDENTIAL_ROTATED,
                provider.id,
                audit.CredentialRotated(credential_version=version),
            )
        return queries.provider_out(db, provider, keys)


def set_provider_active(
    context: WriteContext, provider_id: UUID, active: bool
) -> schemas.ProviderOut:
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        routing = usage.lock_routing(db, tenant)  # lock order: routing before providers
        provider = _locked_provider(db, tenant, provider_id)
        if provider.active != active:
            if not active:
                used_in = usage.provider_used_in(db, routing, provider.id)
                if used_in:
                    raise DomainError(ErrorCode.MDL_MODEL_IN_USE, {"used_in": used_in})
            provider.active = active
            provider.updated_at = sa.func.now()
            _flush(db)
            db.refresh(provider)
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_PROVIDER_STATE_CHANGED,
                provider.id,
                audit.ActiveChange(before=not active, after=active),
            )
        return queries.provider_out(db, provider, queries.key_ring_or_none(context.settings))


def record_agreement(
    context: WriteContext, provider_id: UUID, payload: schemas.AgreementIn
) -> schemas.AgreementOut:
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        provider = _locked_provider(db, tenant, provider_id)
        if provider.provider_type != "EXTERNAL":
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        agreement = MdlProviderAgreement(
            institution_id=tenant,
            provider_id=provider.id,
            provider_type=provider.provider_type,
            basis=payload.basis,
            document_number=payload.document_number,
            signed_on=payload.signed_on,
            recorded_by=authority.actor_id,
        )
        db.add(agreement)
        _flush(db)
        db.refresh(agreement)
        record(
            db,
            context,
            authority,
            audit.AuditAction.MDL_AGREEMENT_RECORDED,
            agreement.id,
            audit.AgreementRecorded(
                provider_id=provider.id,
                basis=agreement.basis,
                document_number=agreement.document_number,
                signed_on=agreement.signed_on,
            ),
        )
        return queries.agreement_out(
            agreement, None, queries.agreement_in_force_id(db, provider.id)
        )


def withdraw_agreement(
    context: WriteContext, provider_id: UUID, agreement_id: UUID
) -> schemas.WithdrawalOut:
    """D5: allowed even when a model is routed; reports the affected routing slots."""
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        routing = usage.lock_routing(db, tenant)
        provider = _locked_provider(db, tenant, provider_id)
        agreement = one(
            db,
            sa.select(MdlProviderAgreement).where(
                MdlProviderAgreement.id == agreement_id,
                MdlProviderAgreement.provider_id == provider.id,
                MdlProviderAgreement.institution_id == tenant,
            ),
        )
        withdrawal = MdlProviderAgreementWithdrawal(
            agreement_id=agreement.id, institution_id=tenant, withdrawn_by=authority.actor_id
        )
        db.add(withdrawal)
        _flush(db, ErrorCode.CONFLICT)  # already withdrawn
        db.refresh(withdrawal)
        record(
            db,
            context,
            authority,
            audit.AuditAction.MDL_AGREEMENT_WITHDRAWN,
            agreement.id,
            audit.AgreementFields(
                provider_id=provider.id,
                basis=agreement.basis,
                document_number=agreement.document_number,
            ),
        )
        in_force = queries.agreement_in_force_id(db, provider.id)
        return schemas.WithdrawalOut(
            agreement=queries.agreement_out(agreement, withdrawal, in_force),
            affected_routing=usage.provider_used_in(db, routing, provider.id),
        )


def _model_fields(model: MdlModel) -> audit.ModelFields:
    return audit.ModelFields(
        display_name=model.display_name,
        capabilities=queries.capabilities(model),
        max_output_tokens=model.max_output_tokens,
    )


def _set_capabilities(model: MdlModel, capabilities: list[str]) -> None:
    model.supports_text = "TEXT" in capabilities
    model.supports_image = "IMAGE" in capabilities
    model.supports_voice = "VOICE" in capabilities


def create_model(context: WriteContext, payload: schemas.CreateModel) -> schemas.ModelOut:
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        provider = one(
            db, queries.provider_query(tenant).where(MdlProvider.id == payload.provider_id)
        )
        model = MdlModel(
            institution_id=tenant,
            provider_id=provider.id,
            technical_id=payload.technical_id,
            display_name=payload.display_name,
            max_output_tokens=payload.max_output_tokens,
            risk_level=payload.risk_level,
        )
        _set_capabilities(model, payload.capabilities)
        db.add(model)
        _flush(db)
        db.refresh(model)
        record(
            db,
            context,
            authority,
            audit.AuditAction.MDL_MODEL_CREATED,
            model.id,
            audit.ModelCreated(
                **_model_fields(model).model_dump(),
                provider_id=provider.id,
                technical_id=model.technical_id,
                risk_level=model.risk_level,
            ),
        )
        return queries.model_out(db, model, context.settings)


def _locked_model(db: Session, tenant: UUID, model_id: UUID) -> MdlModel:
    return one(db, queries.model_query(tenant).where(MdlModel.id == model_id).with_for_update())


def update_model(
    context: WriteContext, model_id: UUID, payload: schemas.ModelPatch
) -> schemas.ModelOut:
    changes = payload.model_dump(exclude_unset=True)
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        routing = usage.lock_routing(db, tenant)  # lock order: routing before models
        model = _locked_model(db, tenant, model_id)
        before, risk_before = _model_fields(model), model.risk_level
        if "display_name" in changes:
            model.display_name = changes["display_name"]
        if "capabilities" in changes:
            _set_capabilities(model, changes["capabilities"])
        if "max_output_tokens" in changes:
            model.max_output_tokens = changes["max_output_tokens"]
        if "risk_level" in changes:
            model.risk_level = changes["risk_level"]
        after, risk_after = _model_fields(model), model.risk_level

        used_in = usage.models_used_in(routing, {model.id})
        # A routed model must stay routable: text-capable and risk-classified (FR-MDL-031).
        if used_in and risk_after is None:
            raise DomainError(ErrorCode.MDL_RISK_REQUIRED)
        if used_in and not model.supports_text:
            raise DomainError(ErrorCode.MDL_MODEL_IN_USE, {"used_in": used_in})

        if before != after or risk_before != risk_after:
            model.updated_at = sa.func.now()
            _flush(db)
            db.refresh(model)
        if before != after:
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_MODEL_UPDATED,
                model.id,
                audit.ModelChange(before=before, after=after),
            )
        if risk_before != risk_after:
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_MODEL_RISK_CHANGED,
                model.id,
                audit.RiskChange(before=risk_before, after=risk_after),
            )
        return queries.model_out(db, model, context.settings)


def set_model_active(context: WriteContext, model_id: UUID, active: bool) -> schemas.ModelOut:
    """FR-MDL-012: refuse to deactivate a model that is in use and say where."""
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        routing = usage.lock_routing(db, tenant)
        model = _locked_model(db, tenant, model_id)
        if model.active != active:
            if not active:
                used_in = usage.models_used_in(routing, {model.id})
                if used_in:
                    raise DomainError(ErrorCode.MDL_MODEL_IN_USE, {"used_in": used_in})
            model.active = active
            model.updated_at = sa.func.now()
            _flush(db)
            db.refresh(model)
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_MODEL_STATE_CHANGED,
                model.id,
                audit.ActiveChange(before=not active, after=active),
            )
        return queries.model_out(db, model, context.settings)
