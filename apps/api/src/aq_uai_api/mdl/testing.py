"""Real, quota-free connection test (M4: FR-MDL-020, FR-MDL-030 gate).

Request flow (architecture section 5):

1. **Transaction 1** (shared ``protected`` write path): re-authorize ``mdl.manage``,
   lock provider (shared) then model (exclusive), check the gates, close abandoned
   ``RUNNING`` rows, apply the cooldown, decrypt the credential into memory and insert
   a ``RUNNING`` row holding the provider's connection and credential versions. Commit.
2. **Network**, outside every database transaction and lock: one request through
   ``mdl.egress`` (SSRF policy, pinning, no redirects, no retries, bounded size and
   time). The outcome is reduced to a fixed code; the body is discarded.
3. **Transaction 2**: re-authorize, lock the same rows in the same order, and finish
   the row once. If the provider's versions changed meanwhile the result is recorded
   as ``STALE_CONFIGURATION`` instead of PASSED. The audit event is written here.

If transaction 2 cannot re-authorize (the tester lost the role or the session ended),
the row is closed as ``ABORTED`` without an audit actor and the error is returned. Any
row left ``RUNNING`` by a crash is closed as ``EXPIRED`` by the next test of the model.

Quota: nothing here, or in any module this imports, reads or writes quota or credit
data (FR-MDL-020 AC3; static test ``test_mdl_code_has_no_quota_or_credit_path``).
Secrets: plaintext lives only in local variables of this module and in the outgoing
header; it is never logged, stored, audited or placed in an exception.
"""

import ssl
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import UUID

import httpcore
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.auth.service import database_lock
from aq_uai_api.authorization import writes
from aq_uai_api.authorization.policy import ActorAuthority
from aq_uai_api.authorization.policy import PermissionCode as P
from aq_uai_api.authorization.writes import WriteContext, institution_key, protected, record
from aq_uai_api.db import audit
from aq_uai_api.directory.queries import one
from aq_uai_api.mdl import egress, queries, schemas
from aq_uai_api.mdl.adapters import Outcome, adapter_for
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    CredentialKeysUnavailable,
    CredentialUnreadable,
    SealedCredential,
    endpoint_origin,
    load_key_ring,
)
from aq_uai_api.mdl.models import MdlConnectionTest, MdlModel, MdlProvider, MdlProviderCredential

# D4 cost control: one test per model and configuration per cooldown window; at most
# MAX_RUNNING_PER_INSTITUTION tests in flight per institution, counted in PostgreSQL so the
# limit holds across API workers and processes (M5 review); plus a per-process cap that
# protects worker threads (each test holds one for at most egress.TOTAL_TIMEOUT).
COOLDOWN_SECONDS = 30
MAX_RUNNING_PER_INSTITUTION = 4
MAX_CONCURRENT_TESTS = 4
_IN_FLIGHT = threading.BoundedSemaphore(MAX_CONCURRENT_TESTS)
TEST_CAP_NAMESPACE = 51002


@dataclass(frozen=True)
class _Prepared:
    """State carried from transaction 1 to the network call and transaction 2."""

    test_id: UUID
    model_id: UUID
    provider_id: UUID
    provider_type: str
    endpoint: str
    api_style: str
    auth_scheme: str
    auth_header_name: str | None
    technical_id: str
    connection_version: int
    credential_version: int | None
    secret: SecretStr | None = field(repr=False)
    policy: egress.EgressPolicy = field(repr=False)
    charges_acknowledged: bool = False


def _manager(authority: ActorAuthority) -> UUID:
    authority.require_institution(P.MDL_MANAGE, authority.institution_id)
    return authority.institution_id


def _locked_pair(db: Session, tenant: UUID, model_id: UUID) -> tuple[MdlProvider, MdlModel]:
    """Lock order (section 7): provider rows before model rows."""
    model = one(db, queries.model_query(tenant).where(MdlModel.id == model_id))
    provider = one(
        db,
        queries.provider_query(tenant)
        .where(MdlProvider.id == model.provider_id)
        .with_for_update(read=True),
    )
    model = one(
        db,
        queries.model_query(tenant)
        .where(MdlModel.id == model_id)
        .with_for_update()
        .execution_options(populate_existing=True),
    )
    return provider, model


def _open_secret(
    db: Session, context: WriteContext, provider: MdlProvider
) -> tuple[SecretStr | None, int | None]:
    if provider.auth_scheme not in queries.SECRET_SCHEMES:
        return None, None
    credential = db.scalar(
        sa.select(MdlProviderCredential)
        .where(MdlProviderCredential.provider_id == provider.id)
        .with_for_update(read=True)
    )
    if credential is None:
        raise DomainError(ErrorCode.MDL_CREDENTIAL_REQUIRED)
    try:
        keys = load_key_ring(context.settings)
        secret = keys.open(
            SealedCredential(bytes(credential.ciphertext), bytes(credential.nonce), credential.key_id),
            CredentialBinding(
                institution_id=provider.institution_id,
                provider_id=provider.id,
                endpoint_origin=endpoint_origin(provider.endpoint),
                credential_version=credential.credential_version,
            ),
        )
    except (CredentialKeysUnavailable, CredentialUnreadable):
        raise DomainError(ErrorCode.MDL_CREDENTIAL_UNAVAILABLE) from None
    return secret, credential.credential_version


def _expire_abandoned(db: Session, model_id: UUID) -> None:
    db.execute(
        sa.update(MdlConnectionTest)
        .where(
            MdlConnectionTest.model_id == model_id,
            MdlConnectionTest.status == "RUNNING",
            MdlConnectionTest.started_at <= queries.running_cutoff(),
        )
        .values(status="FAILED", error_code="EXPIRED", finished_at=sa.func.clock_timestamp())
    )


def _start(
    context: WriteContext, model_id: UUID, payload: schemas.ConnectionTestIn
) -> _Prepared:
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        provider, model = _locked_pair(db, tenant, model_id)
        if not model.active or not provider.active:
            raise DomainError(ErrorCode.MDL_NOT_ELIGIBLE)
        if not model.supports_text:
            raise DomainError(ErrorCode.MDL_TEST_UNSUPPORTED)  # D3: text only
        if provider.provider_type == "EXTERNAL":
            # FR-MDL-030 / RULE-MDL-02: no external call without an agreement in force.
            if queries.agreement_in_force_id(db, provider.id) is None:
                raise DomainError(ErrorCode.MDL_DPA_REQUIRED)
            if not payload.acknowledge_provider_charges:
                raise DomainError(ErrorCode.MDL_CHARGES_NOT_ACKNOWLEDGED)  # D4
        _expire_abandoned(db, model.id)
        # Serialize the institution-wide count, then check it (all workers share it).
        database_lock(db, TEST_CAP_NAMESPACE, institution_key(tenant))
        running = db.scalar(
            sa.select(sa.func.count())
            .select_from(MdlConnectionTest)
            .where(
                MdlConnectionTest.institution_id == tenant,
                MdlConnectionTest.status == "RUNNING",
                MdlConnectionTest.started_at > queries.running_cutoff(),
                MdlConnectionTest.model_id != model.id,
            )
        )
        if running >= MAX_RUNNING_PER_INSTITUTION:
            raise DomainError(ErrorCode.RATE_LIMITED)
        latest = db.execute(
            sa.select(
                MdlConnectionTest.status,
                MdlConnectionTest.connection_version,
                MdlConnectionTest.credential_version,
                (
                    MdlConnectionTest.started_at
                    > sa.func.now() - sa.literal(timedelta(seconds=COOLDOWN_SECONDS))
                ).label("recent"),
            )
            .where(MdlConnectionTest.model_id == model.id)
            .order_by(MdlConnectionTest.started_at.desc(), MdlConnectionTest.id.desc())
            .limit(1)
        ).first()
        if latest is not None and latest.status == "RUNNING":
            raise DomainError(ErrorCode.MDL_TEST_IN_PROGRESS)
        # The cooldown limits repeated calls against one configuration; after a change
        # that bumps a version (new endpoint, new secret) the administrator may retest.
        same_configuration = latest is not None and (
            latest.connection_version,
            latest.credential_version,
        ) == (provider.connection_version, queries.present_credential_version(db, provider))
        if same_configuration and latest.recent:
            raise DomainError(ErrorCode.MDL_TEST_COOLDOWN)
        secret, credential_version = _open_secret(db, context, provider)
        # Explicit column list: the runtime grant allows INSERT of the snapshot columns
        # only, so a new row can only ever start as RUNNING (db/provision.py).
        try:
            test_id = db.execute(
                sa.insert(MdlConnectionTest)
                .values(
                    institution_id=tenant,
                    model_id=model.id,
                    connection_version=provider.connection_version,
                    credential_version=credential_version,
                    started_by=authority.actor_id,
                )
                .returning(MdlConnectionTest.id)
            ).scalar_one()
        except IntegrityError as exc:  # the one-RUNNING-per-model index
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DomainError(ErrorCode.MDL_TEST_IN_PROGRESS) from None
            raise
        return _Prepared(
            test_id=test_id,
            model_id=model.id,
            provider_id=provider.id,
            provider_type=provider.provider_type,
            endpoint=provider.endpoint,
            api_style=provider.api_style,
            auth_scheme=provider.auth_scheme,
            auth_header_name=provider.auth_header_name,
            technical_id=model.technical_id,
            connection_version=provider.connection_version,
            credential_version=credential_version,
            secret=secret,
            policy=queries.egress_policy(context.settings),
            charges_acknowledged=payload.acknowledge_provider_charges,
        )


def _tls_failure(exc: BaseException) -> bool:
    seen = exc
    for _ in range(5):
        if isinstance(seen, ssl.SSLError):
            return True
        if seen.__cause__ is None and seen.__context__ is None:
            return False
        seen = seen.__cause__ or seen.__context__
    return False


def _exchange(prepared: _Prepared) -> tuple[Outcome, int]:
    """Run the request. Never raises; returns a fixed outcome and the latency in ms."""
    started = time.monotonic()
    try:
        adapter = adapter_for(prepared.api_style)
        request = adapter.build(
            prepared.technical_id,
            prepared.auth_scheme,
            prepared.auth_header_name,
            prepared.secret,
        )
        result = egress.post(
            prepared.policy,
            prepared.provider_type,
            prepared.endpoint,
            request.suffix,
            request.headers,
            request.body,
            sends_credential=prepared.secret is not None,
        )
        del request
        outcome = adapter.classify(result)
        del result  # the provider's body is discarded, never stored
    except egress.EgressBlocked:
        outcome = Outcome("FAILED", "ENDPOINT_BLOCKED")
    except (egress.EgressTimeout, httpcore.TimeoutException):
        outcome = Outcome("FAILED", "TIMEOUT")
    except egress.ResolutionFailed:
        outcome = Outcome("FAILED", "DNS_FAILED")
    except egress.TrustStoreUnavailable:
        outcome = Outcome("FAILED", "TLS_ERROR")
    except egress.ResponseTooLarge:
        outcome = Outcome("FAILED", "RESPONSE_TOO_LARGE", 2)
    except httpcore.ConnectError as exc:
        outcome = Outcome("FAILED", "TLS_ERROR" if _tls_failure(exc) else "NETWORK_ERROR")
    except httpcore.RemoteProtocolError:
        outcome = Outcome("FAILED", "BAD_RESPONSE")
    except httpcore.NetworkError:
        outcome = Outcome("FAILED", "NETWORK_ERROR")
    except Exception:  # noqa: BLE001 - never leak details; the row must still finish
        outcome = Outcome("FAILED", "TEST_ERROR")
    latency_ms = max(0, round((time.monotonic() - started) * 1000))
    return outcome, latency_ms


def _abandon(test_id: UUID) -> None:
    """Close our own RUNNING row when transaction 2 cannot run (no audit actor)."""
    try:
        with writes.write_transaction() as db:  # the same seam protected() uses
            db.execute(
                sa.update(MdlConnectionTest)
                .where(MdlConnectionTest.id == test_id, MdlConnectionTest.status == "RUNNING")
                .values(
                    status="FAILED", error_code="ABORTED", finished_at=sa.func.clock_timestamp()
                )
            )
    except Exception:  # noqa: BLE001 - the expiry rule closes the row later
        pass


def _finish(
    context: WriteContext, prepared: _Prepared, outcome: Outcome, latency_ms: int
) -> schemas.ConnectionTestOut:
    with protected(context, changes_authority=False) as (db, authority):
        tenant = _manager(authority)
        provider, model = _locked_pair(db, tenant, prepared.model_id)
        credential_version = queries.present_credential_version(db, provider)
        if (
            provider.connection_version != prepared.connection_version
            or credential_version != prepared.credential_version
        ):
            # The result describes a configuration that no longer exists.
            outcome = Outcome("FAILED", "STALE_CONFIGURATION", outcome.http_status_class)
        finished = db.execute(
            sa.update(MdlConnectionTest)
            .where(
                MdlConnectionTest.id == prepared.test_id,
                MdlConnectionTest.status == "RUNNING",
            )
            .values(
                status=outcome.status,
                error_code=outcome.error_code,
                http_status_class=outcome.http_status_class,
                latency_ms=latency_ms,
                finished_at=sa.func.clock_timestamp(),
            )
            .returning(MdlConnectionTest.id)
        ).first()
        test = db.scalar(
            sa.select(MdlConnectionTest)
            .where(MdlConnectionTest.id == prepared.test_id)
            .execution_options(populate_existing=True)
        )
        if finished is not None:
            record(
                db,
                context,
                authority,
                audit.AuditAction.MDL_MODEL_CONNECTION_TESTED,
                model.id,
                audit.ConnectionTested(
                    test_id=test.id,
                    status=outcome.status,
                    error_code=outcome.error_code,
                    http_status_class=outcome.http_status_class,
                    latency_ms=latency_ms,
                    connection_version=test.connection_version,
                    credential_version=test.credential_version,
                    charges_acknowledged=prepared.charges_acknowledged,
                ),
            )
        return queries.connection_test_out(test, provider.connection_version, credential_version)


def run_connection_test(
    context: WriteContext, model_id: UUID, payload: schemas.ConnectionTestIn
) -> schemas.ConnectionTestOut:
    if not _IN_FLIGHT.acquire(blocking=False):
        raise DomainError(ErrorCode.RATE_LIMITED)
    try:
        prepared = _start(context, model_id, payload)
        outcome, latency_ms = _exchange(prepared)
        prepared = replace(prepared, secret=None)  # drop the plaintext reference
        try:
            return _finish(context, prepared, outcome, latency_ms)
        except BaseException:
            _abandon(prepared.test_id)
            raise
    finally:
        _IN_FLIGHT.release()

