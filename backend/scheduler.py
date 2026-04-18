"""
APScheduler jobs — rodam em background junto com o FastAPI.

Orçamento de API (free tier API-Football = 100 req/dia):
  - seasons cache refresh: 1 req × 6 ligas × 2x/dia = 12 req/dia
  - fixtures por liga:     6 req × 4x/dia           = 24 req/dia
  - standings por liga:    6 req × 1x/dia           =  6 req/dia
  - nba_api (sem limite)
  Total: ~42 req/dia — folga grande.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal
from services.football_api import fetch_all_leagues_fixtures, fetch_all_standings
from services.nba_service import fetch_celtics_schedule
from services.scraper import enrich_broadcasts

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


async def _job_fixtures():
    async with SessionLocal() as db:
        await fetch_all_leagues_fixtures(db)


async def _job_standings():
    async with SessionLocal() as db:
        await fetch_all_standings(db)


async def _job_nba():
    async with SessionLocal() as db:
        try:
            n = await fetch_celtics_schedule(db)
            print(f"[nba] {n} jogos salvos")
        except Exception as e:
            print(f"[nba] erro: {e}")


async def _job_scraper():
    async with SessionLocal() as db:
        try:
            n = await enrich_broadcasts(db)
            print(f"[scraper] {n} broadcasts enriquecidos")
        except Exception as e:
            print(f"[scraper] erro: {e}")


def start_scheduler():
    # Fixtures: 01h, 07h, 13h, 19h
    scheduler.add_job(_job_fixtures,  CronTrigger(hour="1,7,13,19"), id="fixtures")
    # Standings: 06:30 diário
    scheduler.add_job(_job_standings, CronTrigger(hour=6, minute=30), id="standings")
    # NBA: 08h diário
    scheduler.add_job(_job_nba,       CronTrigger(hour=8), id="nba")
    # Scraper TV (best-effort): a cada 3h
    scheduler.add_job(_job_scraper,   CronTrigger(hour="*/3"), id="scraper")
    scheduler.start()
    print("[scheduler] jobs agendados.")
