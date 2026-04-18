"""
Fetcher para API-Football (RapidAPI).
Documentação: https://www.api-football.com/documentation-v3
Limite free tier: 100 req/dia — por isso salvamos tudo no banco.
"""
import os
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = "https://v3.football.api-sports.io"

# Mapeamento league.api_id → nome legível
TRACKED_LEAGUES = {2, 3, 13, 11, 71, 73}

# Times que acompanhamos de perto (api_id da API-Football)
TRACKED_TEAMS = {356, 153, 131, 121, 127, 529, 50, 157}


def _headers() -> dict:
    return {"x-apisports-key": API_KEY}


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    r = await client.get(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------
# Upsert helpers
# ------------------------------------------------------------------

async def _upsert_team(db: AsyncSession, t: dict) -> int:
    """Insere ou atualiza time; retorna o id interno."""
    result = await db.execute(
        text("SELECT id FROM teams WHERE api_id = :api_id"),
        {"api_id": t["id"]},
    )
    row = result.fetchone()
    if row:
        await db.execute(
            text("UPDATE teams SET name=:name, logo_url=:logo WHERE api_id=:api_id"),
            {"name": t["name"], "logo": t.get("logo"), "api_id": t["id"]},
        )
        return row[0]
    result = await db.execute(
        text("""INSERT INTO teams (api_id, name, sport, logo_url, tracked)
                VALUES (:api_id, :name, 'football', :logo, :tracked)
                RETURNING id"""),
        {"api_id": t["id"], "name": t["name"], "logo": t.get("logo"),
         "tracked": t["id"] in TRACKED_TEAMS},
    )
    return result.scalar()


async def _league_internal_id(db: AsyncSession, api_league_id: int) -> int | None:
    r = await db.execute(
        text("SELECT id FROM leagues WHERE api_id = :aid"), {"aid": api_league_id}
    )
    row = r.fetchone()
    return row[0] if row else None


# ------------------------------------------------------------------
# Fetch: próximos jogos de um time
# ------------------------------------------------------------------

async def fetch_fixtures_for_team(db: AsyncSession, team_api_id: int, season: int = 2025):
    """
    Busca os jogos dos próximos 7 dias de um time específico e salva no banco.
    Exemplo de chamada: await fetch_fixtures_for_team(db, 356)  # São Paulo
    """
    now = datetime.now(timezone.utc)
    params = {
        "team":   team_api_id,
        "season": season,
        "from":   now.strftime("%Y-%m-%d"),
        "to":     (now + timedelta(days=7)).strftime("%Y-%m-%d"),
        "timezone": "America/Sao_Paulo",
    }

    async with httpx.AsyncClient() as client:
        data = await _get(client, "/fixtures", params)

    saved = 0
    for f in data.get("response", []):
        fix      = f["fixture"]
        league_d = f["league"]
        teams    = f["teams"]
        goals    = f["goals"]
        broadcast_list = [
            b["channel"] for b in f.get("broadcasts", []) if b.get("channel")
        ]

        # Ignora competições que não rastreamos
        if league_d["id"] not in TRACKED_LEAGUES:
            continue

        league_id = await _league_internal_id(db, league_d["id"])
        if not league_id:
            continue

        home_id = await _upsert_team(db, teams["home"])
        away_id = await _upsert_team(db, teams["away"])

        scheduled = datetime.fromisoformat(fix["date"].replace("Z", "+00:00")).replace(tzinfo=None)

        await db.execute(
            text("""
                INSERT INTO matches
                    (api_id, sport, league_id, home_team_id, away_team_id,
                     scheduled_at, venue, status, home_score, away_score,
                     season, broadcast, broadcast_src, fetched_at)
                VALUES
                    (:api_id, 'football', :league_id, :home_id, :away_id,
                     :sched, :venue, :status, :hs, :as_, :season,
                     :broadcast, 'api', CURRENT_TIMESTAMP)
                ON CONFLICT(api_id) DO UPDATE SET
                    status       = excluded.status,
                    home_score   = excluded.home_score,
                    away_score   = excluded.away_score,
                    broadcast    = CASE WHEN excluded.broadcast != '[]'
                                        THEN excluded.broadcast
                                        ELSE matches.broadcast END,
                    fetched_at   = CURRENT_TIMESTAMP
            """),
            {
                "api_id":    fix["id"],
                "league_id": league_id,
                "home_id":   home_id,
                "away_id":   away_id,
                "sched":     scheduled,
                "venue":     fix.get("venue", {}).get("name"),
                "status":    fix["status"]["short"],
                "hs":        goals.get("home"),
                "as_":       goals.get("away"),
                "season":    season,
                "broadcast": broadcast_list,
            },
        )
        saved += 1

    await db.commit()
    return saved


# ------------------------------------------------------------------
# Fetch: classificação de um campeonato
# ------------------------------------------------------------------

async def fetch_standings(db: AsyncSession, league_api_id: int, season: int = 2025):
    params = {"league": league_api_id, "season": season}
    async with httpx.AsyncClient() as client:
        data = await _get(client, "/standings", params)

    for league_block in data.get("response", []):
        for group in league_block.get("league", {}).get("standings", []):
            for entry in group:
                team_id  = await _upsert_team(db, entry["team"])
                league_id = await _league_internal_id(db, league_api_id)
                if not league_id:
                    continue
                all_stats = entry["all"]
                goals     = all_stats.get("goals", {})
                await db.execute(
                    text("""
                        INSERT INTO standings
                            (league_id, team_id, season, position, played,
                             won, drawn, lost, goals_for, goals_against,
                             points, form, updated_at)
                        VALUES
                            (:lid, :tid, :season, :pos, :p,
                             :w, :d, :l, :gf, :ga,
                             :pts, :form, CURRENT_TIMESTAMP)
                        ON CONFLICT(league_id, team_id, season) DO UPDATE SET
                            position      = excluded.position,
                            played        = excluded.played,
                            won           = excluded.won,
                            drawn         = excluded.drawn,
                            lost          = excluded.lost,
                            goals_for     = excluded.goals_for,
                            goals_against = excluded.goals_against,
                            points        = excluded.points,
                            form          = excluded.form,
                            updated_at    = CURRENT_TIMESTAMP
                    """),
                    {
                        "lid":    league_id,
                        "tid":    team_id,
                        "season": season,
                        "pos":    entry["rank"],
                        "p":      all_stats.get("played", 0),
                        "w":      all_stats.get("win", 0),
                        "d":      all_stats.get("draw", 0),
                        "l":      all_stats.get("lose", 0),
                        "gf":     goals.get("for", 0),
                        "ga":     goals.get("against", 0),
                        "pts":    entry.get("points", 0),
                        "form":   entry.get("form"),
                    },
                )

    await db.commit()
