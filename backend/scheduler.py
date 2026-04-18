"""
APScheduler jobs — rodam em background junto com o FastAPI.
Rate budget API-Football free tier: 100 req/dia.
  - 5 times BR  × fetch_fixtures = 5 req  → a cada 6h  (20/dia)
  - 6 leagues × fetch_standings  = 6 req  → 1x/dia     ( 6/dia)
  - scraper GE: sem limite de API          → a cada 2h
  Total: ~26 req/dia — bem dentro do limite.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal
from services.football_api import (
    fetch_fixtures_for_team,
    fetch_standings,
    TRACKED_TEAMS,
    TRACKED_LEAGUES,
)
from services.nba_service import fetch_celtics_schedule
from services.scraper import enrich_broadcasts

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


async def _job_fixtures():
    async with SessionLocal() as db:
        for team_id in TRACKED_TEAMS:
            try:
                n = await fetch_fixtures_for_team(db, team_id)
                print(f"[fixtures] team {team_id} → {n} jogos salvos")
            except Exception as e:
                print(f"[fixtures] erro team {team_id}: {e}")


async def _job_standings():
    async with SessionLocal() as db:
        for league_id in TRACKED_LEAGUES:
            try:
                await fetch_standings(db, league_id)
                print(f"[standings] league {league_id} atualizada")
            except Exception as e:
                print(f"[standings] erro league {league_id}: {e}")


async def _job_nba():
    async with SessionLocal() as db:
        n = await fetch_celtics_schedule(db)
        print(f"[nba] {n} jogos salvos")


async def _job_scraper():
    async with SessionLocal() as db:
        n = await enrich_broadcasts(db)
        print(f"[scraper] {n} broadcasts enriquecidos")


def start_scheduler():
    # Fixtures: 07:00, 13:00, 19:00, 01:00 (4x/dia)
    scheduler.add_job(_job_fixtures,  CronTrigger(hour="1,7,13,19"), id="fixtures")
    # Classificações: 06:30 diário
    scheduler.add_job(_job_standings, CronTrigger(hour=6, minute=30), id="standings")
    # NBA: 08:00 diário
    scheduler.add_job(_job_nba,       CronTrigger(hour=8), id="nba")
    # Scraper TV: a cada 2 horas
    scheduler.add_job(_job_scraper,   CronTrigger(hour="*/2"), id="scraper")
    scheduler.start()
    print("[scheduler] jobs agendados.")
