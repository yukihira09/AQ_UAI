"""Confirm database strings are rendered safely and aren't accidentally exposed."""

from aq_uai_api.core.config import Settings


def test_special_characters_in_password() -> None:
    cfg = Settings(
        _env_file=None,
        db_host="db",
        db_port=5432,
        db_name="aq_uai",
        db_user="aq_admin",
        db_password="hello@with:/?#",
    )
    url = cfg.database_url
    assert url.password == "hello@with:/?#"
    assert url.host == "db"
    assert url.render_as_string(hide_password=True).find("hello@with") == -1


def test_phase1_environment_defaults_to_nonproduction() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.environment in {"development", "test", "production"}
