"""Register API models and run Alembic with the migration service's settings."""

from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine, pool

from aq_uai_api.core.config import get_settings
from aq_uai_api.db import identity, models  # noqa: F401 - register ORM tables
from aq_uai_api.db.base import Base
from aq_uai_api.mdl import models as mdl_models  # noqa: F401 - register MDL tables
from aq_uai_api.qta import models as qta_models  # noqa: F401 - register QTA tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


try:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
except CommandError:
    # Alembic reports pending schema operations as a CommandError. Avoid its raw details.
    raise CommandError("Alembic could not complete the requested operation.") from None
except Exception:
    # Driver diagnostics can contain values even when SQLAlchemy hides bind parameters.
    raise CommandError(
        "Migration failed. Check database access and the requested revision."
    ) from None
