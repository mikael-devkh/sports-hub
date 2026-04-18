"""
Fetcher para NBA usando nba_api (lib oficial não-oficial, sem chave necessária).
Boston Celtics team_id = 1610612738
"""
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from nba_api.stats.endpoints import teamgamelog, leaguestandingsv3
from nba_api.stats.static import teams as nba_teams_static

CELTICS_ID = 1610612738
NBA_LEAGUE_API_ID = 12  # nosso api_id interno para NBA


async def _nba_internal_team_id(db: AsyncSession, nba_id: int) -> int | None:
    r = await db.execute(text("SELECT id FROM teams WHERE api_id = :aid"), {"aid": nba_id})
    row = r.fetchone()
    return row[0] if row else None


async def _nba_league_id(db: AsyncSession) -> int | None:
    r = await db.execute(
        text("SELECT id FROM leagues WHERE api_id = :aid"), {"aid": NBA_LEAGUE_API_ID}
    )
    row = r.fetchone()
    return row[0] if row else None


async def fetch_celtics_schedule(db: AsyncSession, season: str = "2024-25"):
    """
    nba_api é síncrono; chamamos em thread para não bloquear o event loop.
    Salva os próximos jogos (últimos 10 do log + próximos pela schedule).
    """
    import asyncio

    def _sync_fetch():
        gl = teamgamelog.TeamGameLog(team_id=CELTICS_ID, season=season)
        return gl.get_data_frames()[0]

    df = await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)

    league_id = await _nba_league_id(db)
    team_id   = await _nba_internal_team_id(db, CELTICS_ID)
    if not league_id or not team_id:
        return 0

    saved = 0
    for _, row in df.iterrows():
        game_date = datetime.strptime(str(row["GAME_DATE"]), "%b %d, %Y").replace(
            tzinfo=timezone.utc
        )
        matchup: str = row["MATCHUP"]  # ex: "BOS vs. MIA" ou "BOS @ MIA"
        is_home = "vs." in matchup
        opp_abbr = matchup.split()[-1]

        all_nba = nba_teams_static.get_teams()
        opp = next((t for t in all_nba if t["abbreviation"] == opp_abbr), None)
        opp_nba_id = opp["id"] if opp else None

        # Upsert adversário
        if opp_nba_id:
            r = await db.execute(
                text("SELECT id FROM teams WHERE api_id = :aid"), {"aid": opp_nba_id}
            )
            opp_row = r.fetchone()
            if not opp_row:
                r2 = await db.execute(
                    text("""INSERT INTO teams (api_id, name, short_name, sport, country, tracked)
                            VALUES (:aid, :name, :abbr, 'basketball', 'USA', FALSE)
                            ON CONFLICT (api_id) DO UPDATE SET name = EXCLUDED.name
                            RETURNING id"""),
                    {"aid": opp_nba_id, "name": opp["full_name"], "abbr": opp_abbr},
                )
                opp_internal = r2.scalar()
            else:
                opp_internal = opp_row[0]
        else:
            opp_internal = team_id  # fallback

        home_id = team_id      if is_home else opp_internal
        away_id = opp_internal if is_home else team_id
        wl      = row.get("WL", "")
        status  = "FT" if wl in ("W", "L") else "NS"

        synthetic_api_id = int(f"9{CELTICS_ID}{abs(hash(str(row['GAME_DATE']) + opp_abbr)) % 100000}")

        await db.execute(
            text("""
                INSERT INTO matches
                    (api_id, sport, league_id, home_team_id, away_team_id,
                     scheduled_at, status, season, broadcast, fetched_at)
                VALUES (:aid, 'basketball', :lid, :home, :away,
                        :sched, :status, :season, :broadcast, NOW())
                ON CONFLICT(api_id) DO UPDATE SET
                    status     = excluded.status,
                    fetched_at = CURRENT_TIMESTAMP
            """),
            {
                "aid":    synthetic_api_id,
                "lid":    league_id,
                "home":   home_id,
                "away":   away_id,
                "sched":  game_date,
                "status": status,
                "season": 2025,
                "broadcast": ["NBA League Pass"],
            },
        )
        saved += 1

    await db.commit()
    return saved
