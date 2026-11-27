"""Provider credential sealing with AES-256-GCM and bound associated data (D14).

What: a stored provider secret is encrypted with AES-256-GCM (the maintained
``cryptography`` library) under a key that lives only in the API process
environment, never in PostgreSQL. Each ciphertext is bound by its associated data
(AAD) to the tenant, the provider, the endpoint origin, the credential version and
the key ID. A database-level change to any of those makes decryption fail closed.

Why: RULE-MDL-04 and FR-MDL-010 require the secret to be stored safely and never
shown again. Binding the endpoint origin means a database tamper cannot redirect a
stored secret to another host; binding the provider and tenant stops ciphertext
from being copied between rows.

How to verify: ``tests/unit/test_m2_credentials.py`` (round trip, tamper, wrong
key, wrong AAD, rotation, redaction) and ``tests/integration/test_m2_mdl_schema.py``
(sealed values stored by the runtime login and opened again).

Rules for callers: plaintext is returned only as ``SecretStr``; exceptions carry
fixed messages with no key, plaintext, ciphertext or endpoint; nothing here logs.
"""

import base64
import binascii
import os
import re
import struct
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from aq_uai_api.core.config import Settings, get_settings

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # 96-bit random nonce, the GCM recommendation
TAG_BYTES = 16
MAX_SECRET_BYTES = 4096
KEY_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,31}"
_KEY_ID = re.compile(KEY_ID_PATTERN)
_AAD_PURPOSE = b"aq-uai/mdl/provider-credential/v1"
_PLACEHOLDER_MARKER = "CHANGE_THIS"
_DEFAULT_PORTS = {"http": 80, "https": 443}


class CredentialKeysUnavailable(Exception):
    """The key ring is missing or invalid. Maps to MDL_CREDENTIAL_UNAVAILABLE (503)."""

    def __init__(self) -> None:
        super().__init__("The MDL credential key ring is not configured correctly.")


class CredentialUnreadable(Exception):
    """A stored credential cannot be opened: unknown key, wrong binding or tampering."""

    def __init__(self) -> None:
        super().__init__("The stored credential cannot be decrypted with the configured keys.")


class InvalidCredentialValue(ValueError):
    """The submitted secret is empty, too long or contains control characters."""

    def __init__(self) -> None:
        super().__init__("The credential must be 1-4096 bytes of printable text.")


class InvalidEndpoint(ValueError):
    """The endpoint has no usable http(s) origin. Full egress checks belong to M4."""

    def __init__(self) -> None:
        super().__init__("The endpoint must be an absolute http or https URL without userinfo.")


def endpoint_origin(endpoint: str) -> str:
    """Return the canonical ``scheme://host[:port]`` origin used in the AAD.

    Scheme and host are lower-cased, a trailing dot is removed and the default port
    is omitted, so equivalent spellings produce the same binding. Userinfo is
    rejected so a credential can never be embedded in the endpoint.
    """
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise InvalidEndpoint() from None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".")
    if (
        scheme not in _DEFAULT_PORTS
        or not host
        or "@" in parts.netloc
        or parts.username is not None
        or parts.password is not None
    ):
        raise InvalidEndpoint()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    suffix = "" if port in (None, _DEFAULT_PORTS[scheme]) else f":{port}"
    return f"{scheme}://{host}{suffix}"


@dataclass(frozen=True)
class CredentialBinding:
    """Everything a ciphertext is bound to, apart from the key ID."""

    institution_id: UUID
    provider_id: UUID
    endpoint_origin: str
    credential_version: int

    def associated_data(self, key_id: str) -> bytes:
        # Length-prefixed fields make the encoding unambiguous (no delimiter tricks).
        fields = (
            _AAD_PURPOSE,
            str(self.institution_id).encode(),
            str(self.provider_id).encode(),
            self.endpoint_origin.encode(),
            str(self.credential_version).encode(),
            key_id.encode(),
        )
        return b"".join(struct.pack(">I", len(value)) + value for value in fields)


@dataclass(frozen=True)
class SealedCredential:
    """The three values stored in ``mdl_provider_credentials``. Never sent to clients."""

    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    key_id: str


def _validated_secret(secret: SecretStr | str) -> bytes:
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if not isinstance(value, str):
        raise InvalidCredentialValue()
    encoded = value.encode()
    if (
        not 0 < len(encoded) <= MAX_SECRET_BYTES
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        # Control characters (including CR/LF) could later split an HTTP header.
        raise InvalidCredentialValue()
    return encoded


def _decode_key(material: str) -> bytes:
    try:
        key = base64.b64decode(material.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise CredentialKeysUnavailable() from None
    if len(key) != KEY_BYTES or len(set(key)) == 1:
        raise CredentialKeysUnavailable()
    return key


class KeyRing:
    """Parsed keys. One active key encrypts; every listed key may decrypt."""

    __slots__ = ("_ciphers", "_active_key_id")

    def __init__(self, keys: dict[str, bytes], active_key_id: str):
        if (
            active_key_id not in keys
            or len(set(keys.values())) != len(keys)
            or not all(
                isinstance(key_id, str)
                and _KEY_ID.fullmatch(key_id)
                and isinstance(key, bytes)
                and len(key) == KEY_BYTES
                and len(set(key)) > 1
                for key_id, key in keys.items()
            )
        ):
            raise CredentialKeysUnavailable()
        self._ciphers = {key_id: AESGCM(key) for key_id, key in keys.items()}
        self._active_key_id = active_key_id

    @classmethod
    def parse(cls, raw: str, active_key_id: str) -> "KeyRing":
        """Parse ``key_id:base64(32 bytes)`` entries separated by commas."""
        if not raw.strip() or _PLACEHOLDER_MARKER in raw or _PLACEHOLDER_MARKER in active_key_id:
            raise CredentialKeysUnavailable()
        keys: dict[str, bytes] = {}
        for entry in raw.split(","):
            key_id, separator, material = entry.strip().partition(":")
            if not separator or not _KEY_ID.fullmatch(key_id) or key_id in keys:
                raise CredentialKeysUnavailable()
            keys[key_id] = _decode_key(material)
        return cls(keys, active_key_id)

    def __repr__(self) -> str:
        return f"KeyRing(active_key_id={self._active_key_id!r}, keys={len(self._ciphers)})"

    def __reduce__(self):
        raise TypeError("KeyRing cannot be serialized.")

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @property
    def key_ids(self) -> frozenset[str]:
        return frozenset(self._ciphers)

    def seal(self, secret: SecretStr | str, binding: CredentialBinding) -> SealedCredential:
        plaintext = _validated_secret(secret)
        key_id = self._active_key_id
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = self._ciphers[key_id].encrypt(
            nonce, plaintext, binding.associated_data(key_id)
        )
        return SealedCredential(ciphertext=ciphertext, nonce=nonce, key_id=key_id)

    def open(self, sealed: SealedCredential, binding: CredentialBinding) -> SecretStr:
        cipher = self._ciphers.get(sealed.key_id)
        if cipher is None or len(sealed.nonce) != NONCE_BYTES:
            raise CredentialUnreadable()
        try:
            plaintext = cipher.decrypt(
                sealed.nonce, sealed.ciphertext, binding.associated_data(sealed.key_id)
            )
        except InvalidTag:
            raise CredentialUnreadable() from None
        try:
            return SecretStr(plaintext.decode())
        except UnicodeDecodeError:
            raise CredentialUnreadable() from None

    def needs_rewrap(self, sealed: SealedCredential) -> bool:
        return sealed.key_id != self._active_key_id

    def rewrap(self, sealed: SealedCredential, binding: CredentialBinding) -> SealedCredential:
        """Re-encrypt under the active key, keeping the binding and credential version.

        Used for key rotation: add a new key, make it active, rewrap each stored
        credential, then remove the old key only after every row uses the new one.
        """
        if not self.needs_rewrap(sealed):
            return sealed
        return self.seal(self.open(sealed, binding), binding)


def load_key_ring(settings: Settings | None = None) -> KeyRing:
    """Build the key ring from settings. Raises ``CredentialKeysUnavailable`` if unusable."""
    settings = settings or get_settings()
    return KeyRing.parse(
        settings.mdl_credential_keys.get_secret_value(),
        settings.mdl_credential_active_key_id.strip(),
    )
