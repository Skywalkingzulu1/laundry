import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ----------------------------------------------------------------------
# add your model's MetaData object here
# for 'autogenerate' support
# ----------------------------------------------------------------------
# Import the Base metadata from the application models
from app.models import Base  # noqa: E402

target_metadata = Base.metadata

# ----------------------------------------------------------------------
# Database URL handling
# ----------------------------------------------------------------------
def get_url() -> str:
    """
    Retrieve the database URL. Preference order:
    1. ALEMBIC_DATABASE_URL env var
    2. sqlalchemy.url from alembic.ini
    """
    return os.getenv("ALEMBIC_DATABASE_URL", config.get_main_option("sqlalchemy.url"))

# ----------------------------------------------------------------------
# Async engine creation helpers
# ----------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())