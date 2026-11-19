"""Migration URL is separate from runtime URL and never written to alembic.ini."""

import asyncio

from alembic import context
from insightrag.core.config import Settings
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

settings = Settings()
secret = settings.migration_database_url or settings.database_url
if secret is None:
    raise RuntimeError("Migration database configuration is required")
url = secret.get_secret_value()


def migrate(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=None, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():  # type: ignore[no-untyped-def]
    engine = create_async_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=url, target_metadata=None, literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
