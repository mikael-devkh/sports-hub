import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from database import init_db
from scheduler import start_scheduler
from routers import matches, standings

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
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
async def health():
    return {"status": "ok"}


# Endpoint de trigger manual para forçar sync (útil em dev)
@app.post("/api/v1/admin/sync")
async def manual_sync(target: str = "all"):
    from database import SessionLocal
    from services.football_api import fetch_fixtures_for_team, fetch_standings, TRACKED_TEAMS, TRACKED_LEAGUES
    from services.nba_service import fetch_celtics_schedule
    from services.scraper import enrich_broadcasts

    async with SessionLocal() as db:
        if target in ("all", "fixtures"):
            for tid in TRACKED_TEAMS:
                await fetch_fixtures_for_team(db, tid)
        if target in ("all", "standings"):
            for lid in TRACKED_LEAGUES:
                await fetch_standings(db, lid)
        if target in ("all", "nba"):
            await fetch_celtics_schedule(db)
        if target in ("all", "scraper"):
            await enrich_broadcasts(db)

    return {"synced": target}
