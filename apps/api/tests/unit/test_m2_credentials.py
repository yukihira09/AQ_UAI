"""M2: AES-256-GCM credential sealing with bound associated data (D14, RULE-MDL-04)."""

import base64
import logging
import os
import pickle
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from aq_uai_api.core.config import Settings
from aq_uai_api.mdl import credentials
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    CredentialKeysUnavailable,
    CredentialUnreadable,
    InvalidCredentialValue,
    InvalidEndpoint,
    KeyRing,
    SealedCredential,
    endpoint_origin,
    load_key_ring,
)

SECRET = "sk-canary-7d1f0b8e-never-log-this"


def key(fill: int | None = None) -> tuple[bytes, str]:
    raw = bytes(range(fill, fill + 32)) if fill is not None else os.urandom(32)
    return raw, base64.b64encode(raw).decode()


K1_RAW, K1 = key(1)
K2_RAW, K2 = key(100)


@pytest.fixture
def binding():
    return CredentialBinding(
        institution_id=uuid4(),
        provider_id=uuid4(),
        endpoint_origin="https://api.example.test",
        credential_version=1,
    )


def ring(entries: str, active: str) -> KeyRing:
    return KeyRing.parse(entries, active)


def test_round_trip_returns_a_masked_secret_and_stores_no_plaintext(binding):
    keys = ring(f"k1:{K1}", "k1")
    sealed = keys.seal(SECRET, binding)
    assert sealed.key_id == "k1" and len(sealed.nonce) == 12
    assert len(sealed.ciphertext) == len(SECRET.encode()) + 16
    assert SECRET.encode() not in sealed.ciphertext
    opened = keys.open(sealed, binding)
    assert isinstance(opened, SecretStr) and opened.get_secret_value() == SECRET
    assert SECRET not in repr(opened) and SECRET not in str(opened)
    assert keys.open(keys.seal(SecretStr(SECRET), binding), binding).get_secret_value() == SECRET


def test_every_seal_uses_a_fresh_nonce(binding):
    keys = ring(f"k1:{K1}", "k1")
    sealed = [keys.seal(SECRET, binding) for _ in range(50)]
    assert len({item.nonce for item in sealed}) == 50
    assert len({item.ciphertext for item in sealed}) == 50


@pytest.mark.parametrize("target", ["ciphertext", "nonce", "tag", "truncate"])
def test_tampering_fails_closed(binding, target):
    keys = ring(f"k1:{K1}", "k1")
    sealed = keys.seal(SECRET, binding)
    if target == "ciphertext":
        changed = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
        sealed = replace(sealed, ciphertext=changed)
    elif target == "tag":
        sealed = replace(sealed, ciphertext=sealed.ciphertext[:-1] + bytes([sealed.ciphertext[-1] ^ 1]))
    elif target == "nonce":
        sealed = replace(sealed, nonce=bytes([sealed.nonce[0] ^ 1]) + sealed.nonce[1:])
    else:
        sealed = replace(sealed, ciphertext=sealed.ciphertext[:-1])
    with pytest.raises(CredentialUnreadable) as caught:
        keys.open(sealed, binding)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_wrong_key_and_unknown_key_id_fail_closed(binding):
    sealed = ring(f"k1:{K1}", "k1").seal(SECRET, binding)
    with pytest.raises(CredentialUnreadable):
        ring(f"k1:{K2}", "k1").open(sealed, binding)  # same ID, different material
    with pytest.raises(CredentialUnreadable):
        ring(f"k2:{K2}", "k2").open(sealed, binding)  # ID not in the ring
    with pytest.raises(CredentialUnreadable):
        ring(f"k1:{K1}", "k1").open(replace(sealed, nonce=b"short"), binding)


@pytest.mark.parametrize(
    "change",
    [
        {"institution_id": uuid4()},
        {"provider_id": uuid4()},
        {"endpoint_origin": "https://attacker.example.test"},
        {"endpoint_origin": "https://api.example.test:8443"},
        {"credential_version": 2},
    ],
    ids=["tenant", "provider", "host", "port", "version"],
)
def test_each_bound_field_is_enforced(binding, change):
    keys = ring(f"k1:{K1}", "k1")
    sealed = keys.seal(SECRET, binding)
    with pytest.raises(CredentialUnreadable):
        keys.open(sealed, replace(binding, **change))


def test_key_id_is_bound_so_a_relabelled_row_fails(binding):
    # Even if the same key material were reachable under another ID, the label is in the AAD.
    sealed = ring(f"k1:{K1}", "k1").seal(SECRET, binding)
    relabelled = replace(sealed, key_id="k2")
    with pytest.raises(CredentialUnreadable):
        KeyRing({"k1": K1_RAW, "k2": K2_RAW}, "k1").open(relabelled, binding)


def test_associated_data_is_unambiguous(binding):
    first = binding.associated_data("k1")
    assert first == binding.associated_data("k1")
    assert first != binding.associated_data("k10")
    # Moving a character across a field boundary changes the bytes (length prefixes).
    # Plain concatenation would give "...test" + "11" == "...test1" + "1" here.
    moved = replace(binding, endpoint_origin="https://api.example.test1", credential_version=1)
    original = replace(binding, credential_version=11)
    assert moved.associated_data("k1") != original.associated_data("k1")


def test_rotation_reads_old_rows_and_rewraps_to_the_active_key(binding):
    old_ring = ring(f"k1:{K1}", "k1")
    sealed = old_ring.seal(SECRET, binding)

    rotated = ring(f"k1:{K1},k2:{K2}", "k2")
    assert rotated.active_key_id == "k2" and rotated.key_ids == {"k1", "k2"}
    assert rotated.open(sealed, binding).get_secret_value() == SECRET  # old rows stay readable
    assert rotated.needs_rewrap(sealed)
    rewrapped = rotated.rewrap(sealed, binding)
    assert rewrapped.key_id == "k2" and rewrapped.ciphertext != sealed.ciphertext
    assert not rotated.needs_rewrap(rewrapped)
    assert rotated.rewrap(rewrapped, binding) is rewrapped  # idempotent

    # After every row is rewrapped, the old key can be retired.
    retired = ring(f"k2:{K2}", "k2")
    assert retired.open(rewrapped, binding).get_secret_value() == SECRET
    with pytest.raises(CredentialUnreadable):
        retired.open(sealed, binding)
    # A tampered row is never "rewrapped" into a valid one.
    with pytest.raises(CredentialUnreadable):
        rotated.rewrap(sealed, replace(binding, endpoint_origin="https://other.example.test"))


def test_new_seals_always_use_the_active_key(binding):
    assert ring(f"k1:{K1},k2:{K2}", "k1").seal(SECRET, binding).key_id == "k1"
    assert ring(f"k1:{K1},k2:{K2}", "k2").seal(SECRET, binding).key_id == "k2"


@pytest.mark.parametrize(
    ("entries", "active"),
    [
        ("", "k1"),
        ("   ", "k1"),
        (f"k1:{K1}", ""),
        (f"k1:{K1}", "k2"),
        ("CHANGE_THIS_KEY_ID:CHANGE_THIS_BASE64_32_BYTES", "CHANGE_THIS_KEY_ID"),
        (f"k1:{K1}", "CHANGE_THIS_KEY_ID"),
        ("k1:not-base64!!", "k1"),
        (f"k1:{base64.b64encode(b'x' * 16).decode()}", "k1"),  # AES-128 length
        (f"k1:{base64.b64encode(b'x' * 33).decode()}", "k1"),
        (f"k1:{base64.b64encode(bytes(32)).decode()}", "k1"),  # all zero bytes
        (f"k1{K1}", "k1"),  # missing separator
        (f"K1:{K1}", "K1"),  # upper-case ID
        (f"k 1:{K1}", "k 1"),
        (f"{'k' * 33}:{K1}", "k" * 33),
        (f"k1:{K1},k1:{K2}", "k1"),  # duplicate ID
        (f"k1:{K1},k2:{K1}", "k1"),  # duplicate material
        (f"k1:{K1},", "k1"),  # empty entry
    ],
)
def test_invalid_key_rings_are_rejected_without_echoing_values(entries, active):
    with pytest.raises(CredentialKeysUnavailable) as caught:
        KeyRing.parse(entries, active)
    message = str(caught.value)
    assert K1 not in message and K2 not in message and "base64" not in message.lower()
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "value",
    ["", "x" * 4097, "line\nbreak", "carriage\rreturn", "nul\x00byte", "tab\there", "del\x7f"],
)
def test_unsafe_secret_values_are_rejected_before_encryption(binding, value):
    with pytest.raises(InvalidCredentialValue) as caught:
        ring(f"k1:{K1}", "k1").seal(value, binding)
    assert value == "" or value not in str(caught.value)


def test_maximum_and_unicode_secret_values_round_trip(binding):
    keys = ring(f"k1:{K1}", "k1")
    for value in ("x" * 4096, "khóa-bí-mật-✓"):
        assert keys.open(keys.seal(value, binding), binding).get_secret_value() == value


def test_settings_and_loader_never_expose_key_material(monkeypatch):
    monkeypatch.setenv("AQ_UAI_MDL_CREDENTIAL_KEYS", f"k1:{K1},k2:{K2}")
    monkeypatch.setenv("AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID", "k2")
    settings = Settings()
    keys = load_key_ring(settings)
    assert keys.active_key_id == "k2"
    for text in (repr(settings), str(settings), repr(keys), str(settings.model_dump())):
        assert K1 not in text and K2 not in text
    with pytest.raises(TypeError):
        pickle.dumps(keys)
    sealed = keys.seal(SECRET, CredentialBinding(uuid4(), uuid4(), "https://a.test", 1))
    assert SECRET not in repr(sealed) and repr(sealed.ciphertext) not in repr(sealed)
    assert repr(sealed) == "SealedCredential(key_id='k2')"


def test_missing_keys_do_not_block_startup_or_health(monkeypatch):
    monkeypatch.delenv("AQ_UAI_MDL_CREDENTIAL_KEYS", raising=False)
    monkeypatch.delenv("AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID", raising=False)
    with pytest.raises(CredentialKeysUnavailable):
        load_key_ring(Settings())
    from aq_uai_api.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_nothing_is_logged_during_seal_open_or_failure(binding, caplog):
    caplog.set_level(logging.DEBUG)
    keys = ring(f"k1:{K1}", "k1")
    sealed = keys.seal(SECRET, binding)
    keys.open(sealed, binding)
    with pytest.raises(CredentialUnreadable):
        keys.open(sealed, replace(binding, credential_version=9))
    with pytest.raises(CredentialKeysUnavailable):
        KeyRing.parse(f"k1:{K1}", "missing")
    assert caplog.records == []


def test_module_uses_the_maintained_library_and_has_no_logging_path():
    source = Path(credentials.__file__).read_text()
    assert "from cryptography.hazmat.primitives.ciphers.aead import AESGCM" in source
    assert "import logging" not in source and "print(" not in source
    assert credentials.KEY_BYTES == 32 and credentials.NONCE_BYTES == 12


@pytest.mark.parametrize(
    ("endpoint", "origin"),
    [
        ("https://API.Example.test/v1", "https://api.example.test"),
        ("HTTPS://api.example.test:443/v1/", "https://api.example.test"),
        ("https://api.example.test.:8443/v1", "https://api.example.test:8443"),
        ("http://ollama:11434/v1", "http://ollama:11434"),
        ("http://10.0.0.5:80", "http://10.0.0.5"),
        ("https://[2001:db8::1]:8443/x", "https://[2001:db8::1]:8443"),
    ],
)
def test_endpoint_origin_is_canonical(endpoint, origin):
    assert endpoint_origin(endpoint) == origin


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "api.example.test/v1",
        "ftp://api.example.test",
        "https://user:pass@api.example.test",
        "https://user@api.example.test",
        "https://:443/v1",
        "https://api.example.test:99999",
        "https://api.example.test:port",
        "file:///etc/passwd",
    ],
)
def test_endpoint_origin_rejects_unusable_or_credential_bearing_urls(endpoint):
    with pytest.raises(InvalidEndpoint) as caught:
        endpoint_origin(endpoint)
    assert "pass" not in str(caught.value)


def test_sealed_credential_is_a_plain_value_object():
    sealed = SealedCredential(ciphertext=b"c" * 17, nonce=b"n" * 12, key_id="k1")
    assert sealed == SealedCredential(ciphertext=b"c" * 17, nonce=b"n" * 12, key_id="k1")


@pytest.mark.parametrize("operation", ["prepare", "migrate"])
@pytest.mark.parametrize(
    "variable", ["AQ_UAI_MDL_CREDENTIAL_KEYS", "AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID"]
)
def test_database_setup_refuses_to_run_with_the_key_ring(
    monkeypatch, capsys, operation, variable
):
    """D14 key custody: provision/migrate must never be handed the key ring."""
    from aq_uai_api.db import provision

    monkeypatch.setenv(variable, f"k1:{K1}")
    monkeypatch.setattr("sys.argv", ["provision", operation])
    monkeypatch.setattr(provision, "_connect", lambda *_, **__: pytest.fail("connected"))
    assert provision.main() == 1
    output = capsys.readouterr()
    assert "api service only" in output.err and K1 not in output.err + output.out


@pytest.mark.parametrize(
    "keys",
    [
        {"k1": os.urandom(16)},  # AES-128 is not accepted
        {"k1": bytes(32)},
        {"K1": os.urandom(32)},
        {"k1": "not-bytes"},
    ],
)
def test_direct_construction_enforces_the_same_rules(keys):
    with pytest.raises(CredentialKeysUnavailable):
        KeyRing(keys, next(iter(keys)))


def test_every_application_table_is_known_to_provisioning():
    """Regression: a bootstrap-restored database must remain provisionable."""
    from aq_uai_api.db import identity, models  # noqa: F401 - register tables
    from aq_uai_api.db.base import Base
    from aq_uai_api.db.provision import LEGACY_TABLES
    from aq_uai_api.mdl import models as mdl_models  # noqa: F401
    from aq_uai_api.qta import models as qta_models  # noqa: F401

    assert LEGACY_TABLES == set(Base.metadata.tables) | {"alembic_version"}
