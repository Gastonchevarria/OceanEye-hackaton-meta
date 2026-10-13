"""
Capa de base de datos async — PostgreSQL + TimescaleDB (Supabase Compatible)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
) if DATABASE_URL else None

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
) if engine else None


class Base(DeclarativeBase):
    pass


async def get_db():
    if not AsyncSessionLocal:
        raise RuntimeError("Database engine not configured")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
