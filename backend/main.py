import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy import text

from database import init_db, SessionLocal
from scheduler import start_scheduler
from routers import matches, standings

load_dotenv()


async def _initial_sync_if_empty():
    """Se o banco estiver vazio (ex: primeiro boot, DB limpo), roda sync inicial."""
    from services.football_api import fetch_all_leagues_fixtures, fetch_all_standings
    from services.nba_service import fetch_celtics_schedule

    async with SessionLocal() as db:
        r = await db.execute(text("SELECT COUNT(*) FROM matches"))
        count = r.scalar() or 0
        if count > 0:
            print(f"[startup] banco já tem {count} jogos, pulando sync inicial")
            return
        print("[startup] banco vazio — disparando sync inicial em background")
        try:
            await fetch_all_leagues_fixtures(db)
            await fetch_all_standings(db)
            await fetch_celtics_schedule(db)
        except Exception as e:
            print(f"[startup] falha no sync inicial: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    asyncio.create_task(_initial_sync_if_empty())
    yield


app = FastAPI(title="Sports Hub API", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router,   prefix="/api/v1")
app.include_router(standings.router, prefix="/api/v1")


@app.get("/api/v1/health")
@app.head("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/admin/sync")
async def manual_sync(target: str = "all"):
    from services.football_api import fetch_all_leagues_fixtures, fetch_all_standings
    from services.nba_service import fetch_celtics_schedule
    from services.scraper import enrich_broadcasts

    summary = {}
    async with SessionLocal() as db:
        if target in ("all", "fixtures"):
            summary["fixtures"] = await fetch_all_leagues_fixtures(db)
        if target in ("all", "standings"):
            summary["standings"] = await fetch_all_standings(db)
        if target in ("all", "nba"):
            try:
                summary["nba"] = await fetch_celtics_schedule(db)
            except Exception as e:
                summary["nba"] = f"erro: {e}"
        if target in ("all", "scraper"):
            try:
                summary["scraper"] = await enrich_broadcasts(db)
            except Exception as e:
                summary["scraper"] = f"erro: {e}"
    return summary
