"""Process configuration. Database credentials are never sent to clients or logs."""

from functools import lru_cache

from pydantic import Field
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
