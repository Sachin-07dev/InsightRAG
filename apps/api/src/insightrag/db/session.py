"""One engine/pool per process; never share an AsyncSession across tasks."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from insightrag.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = (
            create_async_engine(
                settings.database_url.get_secret_value(),
                pool_size=settings.pool_size,
                max_overflow=settings.pool_max_overflow,
                pool_timeout=settings.pool_timeout_seconds,
                pool_pre_ping=True,
                connect_args={"timeout": settings.dependency_timeout_seconds, "command_timeout": 5},
                echo=False,
                hide_parameters=True,
            )
            if settings.database_url
            else None
        )
        self.sessions = (
            async_sessionmaker(self.engine, expire_on_commit=False) if self.engine else None
        )

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Rollback on error/close; business services must choose explicit commit boundaries."""
    database: Database = request.app.state.database
    if database.sessions is None:
        raise RuntimeError("Database is not configured")
    async with database.sessions() as session:
        yield session
