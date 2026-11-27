"""Process configuration. Database credentials are never sent to clients or logs."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AQ_UAI_", extra="ignore")

    environment: str = "development"
    db_host: str = "localhost"
    db_port: int = Field(default=55432, ge=1, le=65535)
    db_name: str = "aq_uai"
    db_user: str = "aq_uai_runtime"
    db_password: str = Field(default="", repr=False)
    auth_origin: str = ""
    auth_allow_http_local: bool = False
    auth_trusted_proxy_ip: str = ""
    auth_throttle_key: str = Field(default="", repr=False)
    # MDL credential key ring (D14). Supplied to the api service only, never to
    # provision/migrate. Parsed lazily by aq_uai_api.mdl.credentials so that a
    # missing or invalid value never prevents startup or changes /ready.
    mdl_credential_keys: SecretStr = Field(default=SecretStr(""), repr=False)
    mdl_credential_active_key_id: str = ""
    # M4 egress policy: hosts and CIDRs that INTERNAL providers may reach, set by the
    # operator only (never through the UI). Empty means no internal provider can be
    # tested. Parsed by aq_uai_api.mdl.egress; an invalid value blocks internal tests.
    mdl_egress_internal_allowlist: str = ""
    # M5 review: optional PEM CA bundle (a path inside the api container) trusted in
    # addition to the system store, for INTERNAL https providers only.
    mdl_egress_internal_ca_file: str = ""

    @property
    def database_url(self) -> URL:
        """SQLAlchemy URL.create safely handles special characters in passwords."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
