"""Password verification, opaque session tokens, and browser-origin policy."""

import hashlib
import hmac
import re
import secrets
from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.core.config import Settings

COOKIE_NAME = "aq_uai_session"
CSRF_HEADER = "X-CSRF-Token"
SESSION_SECONDS = 8 * 60 * 60
PASSWORD_MIN = 12
PASSWORD_MAX = 128
USERNAME_MAX = 64
_USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_HEX_KEY = re.compile(r"[0-9a-fA-F]{64}", re.ASCII)
_CSRF = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16, type=Type.ID
)


def normalize_username(value: str) -> str | None:
    stripped = value.strip()
    canonical = stripped.lower()
    if stripped.isascii() and _USERNAME.fullmatch(canonical):
        return canonical
    return None


def hash_password(password: str) -> str:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise ValueError("Use a password of 12 to 128 characters.")
    return _HASHER.hash(password)


@lru_cache
def _dummy_hash() -> str:
    return _HASHER.hash(secrets.token_urlsafe(32))


def verify_password(stored_hash: str | None, password: str) -> bool:
    candidate = stored_hash if stored_hash and stored_hash.startswith("$argon2id$") else None
    try:
        return _HASHER.verify(candidate or _dummy_hash(), password) and candidate is not None
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str | None) -> bytes | None:
    if token is None or not _TOKEN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


def csrf_token(token: str) -> str:
    return hmac.digest(token.encode("ascii"), b"aq-uai:session-csrf:v1", "sha256").hex()


def validate_csrf(token: str, submitted: list[str]) -> None:
    if (
        len(submitted) != 1
        or not _CSRF.fullmatch(submitted[0])
        or not hmac.compare_digest(csrf_token(token), submitted[0])
    ):
        raise DomainError(ErrorCode.FORBIDDEN)


def require_origin(settings: Settings, origins: list[str]) -> bool:
    """Return the cookie Secure flag for the explicitly configured browser origin."""
    configured = settings.auth_origin
    try:
        url = urlsplit(configured)
        port = url.port
    except ValueError:
        raise DomainError(ErrorCode.SERVICE_UNAVAILABLE) from None

    host = url.hostname
    if (
        not host
        or url.username is not None
        or url.path
        or url.query
        or url.fragment
        or not re.fullmatch(r"[a-z0-9.-]+", host)
        or host.rstrip(".") == "localhost"
        or "*" in configured
        or port == 0
        or configured != f"{url.scheme}://{url.netloc}"
        or (
            url.scheme != "https"
            and not (
                url.scheme == "http"
                and host == "admin.localhost"
                and settings.environment in {"development", "test"}
                and settings.auth_allow_http_local
            )
        )
    ):
        raise DomainError(ErrorCode.SERVICE_UNAVAILABLE)
    if origins != [configured]:
        raise DomainError(ErrorCode.FORBIDDEN)
    return url.scheme == "https"


def throttle_digest(settings: Settings, dimension: str, value: str) -> bytes:
    key = settings.auth_throttle_key
    if not _HEX_KEY.fullmatch(key):
        raise DomainError(ErrorCode.SERVICE_UNAVAILABLE)
    return hmac.digest(bytes.fromhex(key), f"aq-uai:{dimension}:{value}".encode(), "sha256")


def client_peer(settings: Settings, peer: str | None, forwarded: list[str]) -> str | None:
    """Honor nginx's single overwritten address only for an explicitly trusted socket peer."""
    if not settings.auth_trusted_proxy_ip or peer is None or len(forwarded) != 1:
        return peer
    try:
        proxy = ip_address(settings.auth_trusted_proxy_ip)
        if proxy != ip_address(peer) or not proxy.is_private or proxy.is_loopback:
            return peer
        return str(ip_address(forwarded[0]))
    except ValueError:
        return peer
