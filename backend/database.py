import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

# Neon fornece URL no formato psycopg2:
#   postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require
# asyncpg não entende ?sslmode= — precisamos remover e passar ssl via connect_args.
_raw = os.environ["DATABASE_URL"]
if _raw.startswith("postgres://"):
    _raw = _raw.replace("postgres://", "postgresql://", 1)

parts = urlsplit(_raw)
query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
_clean_url = urlunsplit(parts._replace(query="&".join(f"{k}={v}" for k, v in query)))
DB_URL = _clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)

_ssl_ctx = ssl.create_default_context()

engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    connect_args={"ssl": _ssl_ctx},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def init_db():
    schema_path = Path(__file__).parent.parent / "schema.sql"
    raw = schema_path.read_text(encoding="utf-8")

    # Remove linhas de comentário preservando o SQL ao redor
    cleaned_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    statements = [s.strip() for s in cleaned.split(";") if s.strip()]

    async with engine.begin() as conn:
        for stmt in statements:
            # exec_driver_sql: passa SQL cru sem parsing de :parametros
            await conn.exec_driver_sql(stmt)

        # Migrações idempotentes para tabelas antigas
        await conn.exec_driver_sql(
            "ALTER TABLE matches  ALTER COLUMN api_id TYPE BIGINT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE leagues  ALTER COLUMN api_id TYPE BIGINT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE teams    ALTER COLUMN api_id TYPE BIGINT"
        )
