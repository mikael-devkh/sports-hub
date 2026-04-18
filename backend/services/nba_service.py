"""
Fetcher NBA usando nba_api + NBA schedule API pública.
Busca jogos passados E futuros dos Celtics.
"""
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from nba_api.stats.static import teams as nba_teams_static

CELTICS_ID     = 1610612738
NBA_LEAGUE_API_ID = 12


def _current_nba_season() -> str:
    """Retorna a season string correta (ex: '2025-26') baseado na data atual."""
    now = datetime.utcnow()
    # Temporada NBA começa em outubro; antes de outubro, ainda é a temporada anterior
    if now.month >= 10:
        return f"{now.year}-{str(now.year + 1)[-2:]}"
    else:
        return f"{now.year - 1}-{str(now.year)[-2:]}"


async def _nba_league_id(db: AsyncSession) -> int | None:
    r = await db.execute(
        text("SELECT id FROM leagues WHERE api_id = :aid"), {"aid": NBA_LEAGUE_API_ID}
    )
    row = r.fetchone()
    return row[0] if row else None


async def _upsert_nba_team(db: AsyncSession, nba_id: int, full_name: str, abbr: str) -> int:
    r = await db.execute(
        text("""
            INSERT INTO teams (api_id, name, short_name, sport, country, tracked)
            VALUES (:aid, :name, :abbr, 'basketball', 'USA', :tracked)
            ON CONFLICT (api_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """),
        {"aid": nba_id, "name": full_name, "abbr": abbr,
         "tracked": nba_id == CELTICS_ID},
    )
    return r.scalar()


async def fetch_celtics_schedule(db: AsyncSession) -> int:
    """
    Busca schedule dos Celtics via NBA CDN (sem autenticação).
    Cobre passado + futuro da temporada atual.
    """
    season_str = _current_nba_season()           # ex: "2025-26"
    season_yr  = season_str[:4]                  # ex: "2025"
    season_db  = int(season_yr)

    # NBA CDN schedule endpoint (público, sem API key)
    url = f"https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_{season_yr}.json"

    def _sync_fetch():
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())

    try:
        data = await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)
    except Exception as e:
        print(f"[nba] falha ao buscar schedule CDN: {e}")
        return 0

    all_teams = {t["id"]: t for t in nba_teams_static.get_teams()}
    league_id = await _nba_league_id(db)
    if not league_id:
        return 0

    # Garante que Celtics existe no banco
    celtics_info = all_teams.get(CELTICS_ID, {})
    celtics_internal = await _upsert_nba_team(
        db, CELTICS_ID,
        celtics_info.get("full_name", "Boston Celtics"),
        celtics_info.get("abbreviation", "BOS"),
    )

    now = datetime.utcnow()
    window_from = now - timedelta(days=3)
    window_to   = now + timedelta(days=21)

    saved = 0
    game_dates = data.get("leagueSchedule", {}).get("gameDates", [])

    for gd in game_dates:
        try:
            game_date = datetime.strptime(gd["gameDate"], "%m/%d/%Y %H:%M:%S")
        except Exception:
            continue

        if not (window_from <= game_date <= window_to):
            continue

        for g in gd.get("games", []):
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})
            home_id_nba = home.get("teamId")
            away_id_nba = away.get("teamId")

            if home_id_nba != CELTICS_ID and away_id_nba != CELTICS_ID:
                continue

            # Upsert adversário
            opp_nba_id = away_id_nba if home_id_nba == CELTICS_ID else home_id_nba
            opp_info   = all_teams.get(opp_nba_id, {})
            opp_internal = await _upsert_nba_team(
                db, opp_nba_id,
                opp_info.get("full_name", f"Team {opp_nba_id}"),
                opp_info.get("abbreviation", "???"),
            )

            home_internal = celtics_internal if home_id_nba == CELTICS_ID else opp_internal
            away_internal = opp_internal     if home_id_nba == CELTICS_ID else celtics_internal

            status_raw = g.get("gameStatus", 1)
            status = "FT" if status_raw == 3 else ("1H" if status_raw == 2 else "NS")

            hs = home.get("score") if status_raw >= 2 else None
            as_ = away.get("score") if status_raw >= 2 else None

            api_id = 7_000_000 + int(g.get("gameId", 0) or 0)

            await db.execute(
                text("""
                    INSERT INTO matches
                        (api_id, sport, league_id, home_team_id, away_team_id,
                         scheduled_at, status, home_score, away_score,
                         season, broadcast, fetched_at)
                    VALUES (:aid, 'basketball', :lid, :home, :away,
                            :sched, :status, :hs, :as_, :season,
                            CAST(:broadcast AS JSONB), NOW())
                    ON CONFLICT (api_id) DO UPDATE SET
                        status     = EXCLUDED.status,
                        home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score,
                        fetched_at = NOW()
                """),
                {
                    "aid":       api_id,
                    "lid":       league_id,
                    "home":      home_internal,
                    "away":      away_internal,
                    "sched":     game_date,
                    "status":    status,
                    "hs":        hs,
                    "as_":       as_,
                    "season":    season_db,
                    "broadcast": json.dumps(["NBA League Pass", "ESPN"]),
                },
            )
            saved += 1

    await db.commit()
    return saved
