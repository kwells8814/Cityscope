"""Alembic environment.

Reads the database URL from the app's settings (DATABASE_URL) rather than the
ini file, so there are no secrets in the repo and migrations target whatever DB
the app itself uses. `target_metadata` points at our models so
`alembic revision --autogenerate` works.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# make the app importable
import sys
import os
sys.path.insert(0, os.getcwd())

from cityscope.config import settings          # noqa: E402
from cityscope.db.engine import _normalize_url  # noqa: E402
from cityscope.db.models import Base            # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# inject the real URL from settings
db_url = settings.database_url or "sqlite:///cityscope_local.db"
config.set_main_option("sqlalchemy.url", _normalize_url(db_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
