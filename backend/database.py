import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

# Neon fornece uma URL no formato:
# postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
# Convertemos para o driver asyncpg:
_raw = os.environ["DATABASE_URL"]
if _raw.startswith("postgres://"):
    _raw = _raw.replace("postgres://", "postgresql://", 1)
DB_URL = _raw.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DB_URL, echo=False, pool_size=5, max_overflow=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def init_db():
    schema_path = Path(__file__).parent.parent / "schema.sql"
    statements = [
        s.strip()
        for s in schema_path.read_text().split(";")
        if s.strip() and not s.strip().startswith("--")
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
