"""Read-side MDL projections. Every query is restricted to the actor's institution.

Never selects ciphertext into a response: credential status is derived from the row's
existence and key ID only, so listing providers performs no decryption.
"""

from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.core.config import Settings
from aq_uai_api.directory.queries import one, page
from aq_uai_api.directory.schemas import Page, PageParams
from aq_uai_api.mdl import egress, schemas
from aq_uai_api.mdl.credentials import CredentialKeysUnavailable, KeyRing, load_key_ring
from aq_uai_api.mdl.models import (
    MdlConnectionTest,
    MdlModel,
    MdlProvider,
    MdlProviderAgreement,
    MdlProviderAgreementWithdrawal,
    MdlProviderCredential,
)


def reader(authority: ActorAuthority) -> UUID:
    authority.require_institution(P.MDL_READ, authority.institution_id)
    return authority.institution_id


def key_ring_or_none(settings: Settings) -> KeyRing | None:
    try:
        return load_key_ring(settings)
    except CredentialKeysUnavailable:
        return None


def egress_policy(settings: Settings) -> egress.EgressPolicy:
    return egress.EgressPolicy.from_setting(
        settings.mdl_egress_internal_allowlist, settings.mdl_egress_internal_ca_file
    )


def _ca_status(path: str | None) -> str:
    if path is None:
        return "NONE"
    try:
        egress.tls_context(path)
    except egress.TrustStoreUnavailable:
        return "UNREADABLE"
    return "CONFIGURED"


def status(settings: Settings) -> schemas.StatusOut:
    keys = key_ring_or_none(settings)
    policy = egress_policy(settings)
    if not policy.allowlist_valid:
        allowlist = "INVALID"
    elif policy.allowlist.empty:
        allowlist = "EMPTY"
    else:
        allowlist = "CONFIGURED"
    return schemas.StatusOut(
        credential_keys="AVAILABLE" if keys else "UNAVAILABLE",
        active_key_id=keys.active_key_id if keys else None,
        egress=schemas.EgressStatus(
            internal_allowlist=allowlist,
            internal_allowlist_entries=len(policy.allowlist),
            internal_ca=_ca_status(policy.internal_ca_file),
            timeout_seconds=egress.TOTAL_TIMEOUT,
            max_response_bytes=egress.MAX_RESPONSE_BYTES,
        ),
    )


def _agreements(provider_id: UUID):
    return (
        sa.select(MdlProviderAgreement, MdlProviderAgreementWithdrawal)
        .outerjoin(
            MdlProviderAgreementWithdrawal,
            MdlProviderAgreementWithdrawal.agreement_id == MdlProviderAgreement.id,
        )
        .where(MdlProviderAgreement.provider_id == provider_id)
        .order_by(MdlProviderAgreement.recorded_at.desc(), MdlProviderAgreement.id.desc())
    )


def agreement_in_force_id(db: Session, provider_id: UUID) -> UUID | None:
    """The most recent agreement that has not been withdrawn (FR-MDL-030, D5)."""
    return db.scalar(
        _agreements(provider_id)
        .with_only_columns(MdlProviderAgreement.id)
        .where(MdlProviderAgreementWithdrawal.agreement_id.is_(None))
        .limit(1)
    )


def agreement_out(
    agreement: MdlProviderAgreement,
    withdrawal: MdlProviderAgreementWithdrawal | None,
    in_force_id: UUID | None,
) -> schemas.AgreementOut:
    return schemas.AgreementOut(
        id=agreement.id,
        provider_id=agreement.provider_id,
        basis=agreement.basis,
        document_number=agreement.document_number,
        signed_on=agreement.signed_on,
        recorded_by=agreement.recorded_by,
        recorded_at=agreement.recorded_at,
        withdrawn_by=withdrawal.withdrawn_by if withdrawal else None,
        withdrawn_at=withdrawal.withdrawn_at if withdrawal else None,
        in_force=agreement.id == in_force_id,
    )


def agreements(
    db: Session, authority: ActorAuthority, provider_id: UUID, params: PageParams
) -> Page[schemas.AgreementOut]:
    provider = one(db, provider_query(reader(authority)).where(MdlProvider.id == provider_id))
    in_force = agreement_in_force_id(db, provider.id)
    return page(
        db,
        _agreements(provider.id),
        params,
        lambda agreement, withdrawal: agreement_out(agreement, withdrawal, in_force),
    )


def provider_query(institution_id: UUID):
    return sa.select(MdlProvider).where(MdlProvider.institution_id == institution_id)


def provider_out(db: Session, provider: MdlProvider, keys: KeyRing | None) -> schemas.ProviderOut:
    credential = db.execute(
        sa.select(MdlProviderCredential.key_id, MdlProviderCredential.updated_at).where(
            MdlProviderCredential.provider_id == provider.id
        )
    ).first()
    if provider.auth_scheme == "NONE":
        credential_status = "NOT_REQUIRED"
    elif credential is None:
        credential_status = "MISSING"
    elif keys is None or credential.key_id not in keys.key_ids:
        credential_status = "UNREADABLE"
    else:
        credential_status = "STORED"
    in_force = None
    if provider.provider_type == "EXTERNAL":
        row = db.execute(
            _agreements(provider.id)
            .where(MdlProviderAgreementWithdrawal.agreement_id.is_(None))
            .limit(1)
        ).first()
        if row is not None:
            in_force = agreement_out(row[0], row[1], row[0].id)
    secret_bearing = provider.auth_scheme != "NONE" and credential is not None
    return schemas.ProviderOut(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        api_style=provider.api_style,
        endpoint=provider.endpoint,
        auth_scheme=provider.auth_scheme,
        auth_header_name=provider.auth_header_name,
        active=provider.active,
        connection_version=provider.connection_version,
        has_credential=secret_bearing,
        credential_status=credential_status,
        credential_updated_at=credential.updated_at if secret_bearing else None,
        agreement_in_force=in_force,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def providers(
    db: Session, authority: ActorAuthority, params: schemas.ProviderFilters, settings: Settings
) -> Page[schemas.ProviderOut]:
    statement = provider_query(reader(authority))
    if params.active is not None:
        statement = statement.where(MdlProvider.active == params.active)
    if params.provider_type is not None:
        statement = statement.where(MdlProvider.provider_type == params.provider_type)
    keys = key_ring_or_none(settings)
    return page(
        db,
        statement.order_by(sa.func.lower(MdlProvider.name), MdlProvider.id),
        params,
        lambda provider: provider_out(db, provider, keys),
    )


def provider(
    db: Session, authority: ActorAuthority, provider_id: UUID, settings: Settings
) -> schemas.ProviderOut:
    row = one(db, provider_query(reader(authority)).where(MdlProvider.id == provider_id))
    return provider_out(db, row, key_ring_or_none(settings))


def capabilities(model: MdlModel) -> list[str]:
    flags = (
        ("TEXT", model.supports_text),
        ("IMAGE", model.supports_image),
        ("VOICE", model.supports_voice),
    )
    return [name for name, supported in flags if supported]


# A RUNNING row older than this was abandoned (process crash): the network phase is
# bounded by egress.TOTAL_TIMEOUT, so a live test can never be this old.
RUNNING_EXPIRY_SECONDS = 120
SECRET_SCHEMES = schemas.SECRET_SCHEMES


def present_credential_version(db: Session, provider: MdlProvider) -> int | None:
    """The credential version a test made now would use (None when no secret is sent)."""
    if provider.auth_scheme not in SECRET_SCHEMES:
        return None
    return db.scalar(
        sa.select(MdlProviderCredential.credential_version).where(
            MdlProviderCredential.provider_id == provider.id
        )
    )


def _is_current(test: MdlConnectionTest, connection_version: int, credential_version):
    return (
        test.connection_version == connection_version
        and test.credential_version == credential_version
    )


def running_cutoff():
    return sa.func.now() - sa.literal(timedelta(seconds=RUNNING_EXPIRY_SECONDS))


def connection_test_state(db: Session, model: MdlModel) -> schemas.ConnectionTestState:
    """Derive the test state from history; no cached flag can drift (section 2)."""
    provider = db.get(MdlProvider, model.provider_id)
    running = bool(
        db.scalar(
            sa.select(sa.func.count())
            .select_from(MdlConnectionTest)
            .where(
                MdlConnectionTest.model_id == model.id,
                MdlConnectionTest.status == "RUNNING",
                MdlConnectionTest.started_at > running_cutoff(),
            )
        )
    )
    if not model.supports_text:
        return schemas.ConnectionTestState(
            result="UNSUPPORTED", test_id=None, error_code=None, finished_at=None, running=False
        )
    credential_version = present_credential_version(db, provider)
    finished = (
        sa.select(MdlConnectionTest)
        .where(MdlConnectionTest.model_id == model.id, MdlConnectionTest.status != "RUNNING")
        .order_by(MdlConnectionTest.finished_at.desc(), MdlConnectionTest.id.desc())
    )
    current = db.scalar(
        finished.where(
            MdlConnectionTest.connection_version == provider.connection_version,
            MdlConnectionTest.credential_version.is_not_distinct_from(credential_version),
        ).limit(1)
    )
    if current is not None:
        return schemas.ConnectionTestState(
            result=current.status,
            test_id=current.id,
            error_code=current.error_code,
            finished_at=current.finished_at,
            running=running,
        )
    any_finished = db.scalar(finished.with_only_columns(MdlConnectionTest.id).limit(1))
    return schemas.ConnectionTestState(
        result="OUTDATED" if any_finished else "NOT_TESTED",
        test_id=None,
        error_code=None,
        finished_at=None,
        running=running,
    )


def connection_test_out(
    test: MdlConnectionTest, connection_version: int, credential_version: int | None
) -> schemas.ConnectionTestOut:
    return schemas.ConnectionTestOut(
        id=test.id,
        model_id=test.model_id,
        status=test.status,
        error_code=test.error_code,
        http_status_class=test.http_status_class,
        latency_ms=test.latency_ms,
        connection_version=test.connection_version,
        credential_version=test.credential_version,
        current=test.status != "RUNNING"
        and _is_current(test, connection_version, credential_version),
        started_by=test.started_by,
        started_at=test.started_at,
        finished_at=test.finished_at,
    )


def connection_tests(
    db: Session, authority: ActorAuthority, model_id: UUID, params: PageParams
) -> Page[schemas.ConnectionTestOut]:
    found = one(db, model_query(reader(authority)).where(MdlModel.id == model_id))
    provider = db.get(MdlProvider, found.provider_id)
    credential_version = present_credential_version(db, provider)
    statement = (
        sa.select(MdlConnectionTest)
        .where(
            MdlConnectionTest.institution_id == found.institution_id,
            MdlConnectionTest.model_id == found.id,
        )
        .order_by(MdlConnectionTest.started_at.desc(), MdlConnectionTest.id.desc())
    )
    return page(
        db,
        statement,
        params,
        lambda test: connection_test_out(test, provider.connection_version, credential_version),
    )


# Every code routing_issues can return (the contract documented on RoutingEligibility).
ROUTING_ISSUE_CODES = (
    "model_inactive",
    "provider_inactive",
    "text_unsupported",
    "risk_unclassified",
    "not_tested",
    "test_outdated",
    "test_failed",
    "dpa_missing",
    "credential_unavailable",
    "endpoint_blocked",
)
_TEST_ISSUES = {
    "FAILED": "test_failed",
    "OUTDATED": "test_outdated",
    "NOT_TESTED": "not_tested",
}


def routing_issues(
    db: Session,
    model: MdlModel,
    keys: KeyRing | None,
    policy: egress.EgressPolicy,
) -> list[str]:
    """Every reason the model may not be selected, or used, as primary/fallback now.

    One rule set (M5) serves the selection list, ``PUT /routing`` for new slot values
    and the usability of already configured slots (fail closed, D5/D9): FR-MDL-020/021
    (current PASSED test), FR-MDL-030 (agreement in force), FR-MDL-031 (risk recorded),
    plus active state, TEXT capability (D3), a readable credential and the present
    egress policy. Callers that need a consistent answer hold the routing lock and
    shared locks on the provider and model rows first.
    """
    provider = db.get(MdlProvider, model.provider_id)
    issues = []
    if not model.active:
        issues.append("model_inactive")
    if not provider.active:
        issues.append("provider_inactive")
    if not model.supports_text:
        issues.append("text_unsupported")
    if model.risk_level is None:
        issues.append("risk_unclassified")
    result = connection_test_state(db, model).result
    if result in _TEST_ISSUES:
        issues.append(_TEST_ISSUES[result])
    if provider.provider_type == "EXTERNAL" and agreement_in_force_id(db, provider.id) is None:
        issues.append("dpa_missing")
    if provider.auth_scheme in SECRET_SCHEMES:
        key_id = db.scalar(
            sa.select(MdlProviderCredential.key_id).where(
                MdlProviderCredential.provider_id == provider.id
            )
        )
        if key_id is None or keys is None or key_id not in keys.key_ids:
            issues.append("credential_unavailable")
    try:
        target = egress.parse_target(provider.endpoint)
        policy.check_target(provider.provider_type, target)
        if provider.auth_scheme in SECRET_SCHEMES and target.scheme != "https":
            raise egress.EgressBlocked()
    except egress.EgressBlocked:
        issues.append("endpoint_blocked")
    return issues


def eligibility(
    db: Session, model: MdlModel, settings: Settings
) -> schemas.RoutingEligibility:
    issues = routing_issues(db, model, key_ring_or_none(settings), egress_policy(settings))
    return schemas.RoutingEligibility(eligible=not issues, issues=issues)


def model_out(db: Session, model: MdlModel, settings: Settings) -> schemas.ModelOut:
    return schemas.ModelOut(
        id=model.id,
        provider_id=model.provider_id,
        technical_id=model.technical_id,
        display_name=model.display_name,
        capabilities=capabilities(model),
        max_output_tokens=model.max_output_tokens,
        risk_level=model.risk_level,
        active=model.active,
        connection_test=connection_test_state(db, model),
        routing=eligibility(db, model, settings),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def model_query(institution_id: UUID):
    return sa.select(MdlModel).where(MdlModel.institution_id == institution_id)


def models(
    db: Session, authority: ActorAuthority, params: schemas.ModelFilters, settings: Settings
) -> Page[schemas.ModelOut]:
    statement = model_query(reader(authority))
    if params.provider_id is not None:
        statement = statement.where(MdlModel.provider_id == params.provider_id)
    if params.active is not None:
        statement = statement.where(MdlModel.active == params.active)
    if params.risk_level == "UNCLASSIFIED":
        statement = statement.where(MdlModel.risk_level.is_(None))
    elif params.risk_level is not None:
        statement = statement.where(MdlModel.risk_level == params.risk_level)
    statement = statement.order_by(sa.func.lower(MdlModel.display_name), MdlModel.id)
    if params.routing_eligible is None:
        return page(db, statement, params, lambda found: model_out(db, found, settings))
    # Eligibility is derived (tests, agreements, keys, policy), so it is filtered in
    # Python over the institution's models. The registry is small (one row per model an
    # institution configures); the page is cut after filtering so totals stay correct.
    outputs = [model_out(db, found, settings) for found in db.scalars(statement)]
    matching = [item for item in outputs if item.routing.eligible == params.routing_eligible]
    return Page(
        items=matching[params.offset : params.offset + params.limit],
        total=len(matching),
        limit=params.limit,
        offset=params.offset,
    )


def model(
    db: Session, authority: ActorAuthority, model_id: UUID, settings: Settings
) -> schemas.ModelOut:
    found = one(db, model_query(reader(authority)).where(MdlModel.id == model_id))
    return model_out(db, found, settings)
