"""Key rotation: re-encrypt stored provider credentials under the active key (D14).

What: for every credential whose ``key_id`` is not the active key, decrypt it with the
key ring and seal it again under the active key with the same binding (tenant,
provider, endpoint origin, credential version). ``credential_version`` does not change,
so connection tests stay current and routing is unaffected.

Why: key rotation is "add a key, make it active, rewrap every row, then remove the old
key". Without this command the old key could never be retired (deferred from M2/M3).

How to run (inside the ``api`` container, the only service that holds the key ring):

    docker compose ... exec api python -m aq_uai_api.db.mdl_rewrap

It prints counts only (never a key, secret or ciphertext) and exits 1 if any row could
not be opened (for example because its old key was already removed). Each row is
rewrapped in its own transaction with a row lock, and audited as the operator event
``mdl.credential_rewrapped``. Running it twice is harmless: the second run finds nothing.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from aq_uai_api.db import audit
from aq_uai_api.db.session import write_transaction
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    CredentialUnreadable,
    KeyRing,
    SealedCredential,
    endpoint_origin,
)
from aq_uai_api.mdl.models import MdlProvider, MdlProviderCredential


@dataclass
class RewrapResult:
    rewrapped: int = 0
    current: int = 0
    unreadable: int = 0


def _rewrap_one(db: Session, keys: KeyRing, provider_id: UUID, request_id: UUID) -> str:
    row = db.execute(
        sa.select(MdlProviderCredential, MdlProvider)
        .join(MdlProvider, MdlProvider.id == MdlProviderCredential.provider_id)
        .where(MdlProviderCredential.provider_id == provider_id)
        .with_for_update(of=MdlProviderCredential)
    ).first()
    if row is None:
        return "current"
    credential, provider = row
    sealed = SealedCredential(bytes(credential.ciphertext), bytes(credential.nonce), credential.key_id)
    if not keys.needs_rewrap(sealed):
        return "current"
    binding = CredentialBinding(
        institution_id=provider.institution_id,
        provider_id=provider.id,
        endpoint_origin=endpoint_origin(provider.endpoint),
        credential_version=credential.credential_version,
    )
    try:
        fresh = keys.rewrap(sealed, binding)
    except CredentialUnreadable:
        return "unreadable"
    before = credential.key_id
    credential.ciphertext, credential.nonce, credential.key_id = (
        fresh.ciphertext,
        fresh.nonce,
        fresh.key_id,
    )
    credential.updated_at = sa.func.now()
    audit.write_audit_event(
        db,
        action=audit.AuditAction.MDL_CREDENTIAL_REWRAPPED,
        request_id=request_id,
        institution_id=provider.institution_id,
        target_id=provider.id,
        changes=audit.CredentialRewrapped(
            key_id_before=before,
            key_id_after=fresh.key_id,
            credential_version=credential.credential_version,
        ),
    )
    return "rewrapped"


def rewrap_all(
    keys: KeyRing,
    transaction: Callable[[], AbstractContextManager[Session]] = write_transaction,
) -> RewrapResult:
    request_id = uuid4()
    result = RewrapResult()
    with transaction() as db:
        provider_ids = list(
            db.scalars(
                sa.select(MdlProviderCredential.provider_id).order_by(
                    MdlProviderCredential.provider_id
                )
            )
        )
    for provider_id in provider_ids:
        with transaction() as db:
            outcome = _rewrap_one(db, keys, provider_id, request_id)
        setattr(result, outcome, getattr(result, outcome) + 1)
    return result

