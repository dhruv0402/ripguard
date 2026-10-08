from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=(settings.environment == "development"))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def set_session_maker(sm):
    global AsyncSessionLocal
    AsyncSessionLocal = sm


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Dev-only convenience; use Alembic migrations for anything beyond this project's scope."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
