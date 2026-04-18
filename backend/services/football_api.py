"""
Fetcher para API-Football (RapidAPI).
Auto-detecta a temporada corrente de cada liga — nunca precisa ser atualizado
manualmente por virada de ano / virada de temporada.
"""
import json
import os
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = "https://v3.football.api-sports.io"

# Ligas rastreadas (api_id da API-Football)
TRACKED_LEAGUES = {2, 3, 13, 11, 71, 73}

# Times que acompanhamos de perto
TRACKED_TEAMS = {356, 153, 131, 121, 127, 529, 50, 157}

# Cache em memória: {league_api_id: current_season_year}
_SEASON_CACHE: dict[int, int] = {}
_SEASON_CACHE_TS: datetime | None = None


def _headers() -> dict:
    return {"x-apisports-key": API_KEY}


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    r = await client.get(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------
# Auto-descoberta da temporada corrente
# ------------------------------------------------------------------

async def _refresh_current_seasons(client: httpx.AsyncClient) -> dict[int, int]:
    """
    Para cada liga rastreada, pergunta ao API-Football qual é a temporada
    atual (current=true) e guarda em cache por 12h.
    """
    global _SEASON_CACHE, _SEASON_CACHE_TS
    fresh = (
        _SEASON_CACHE_TS
        and datetime.now(timezone.utc) - _SEASON_CACHE_TS < timedelta(hours=12)
    )
    if fresh and _SEASON_CACHE:
        return _SEASON_CACHE

    cache: dict[int, int] = {}
    for lid in TRACKED_LEAGUES:
        try:
            data = await _get(client, "/leagues", {"id": lid, "current": "true"})
            for item in data.get("response", []):
                for s in item.get("seasons", []):
                    if s.get("current"):
                        cache[lid] = s["year"]
                        break
        except Exception as e:
            print(f"[season-cache] erro league {lid}: {e}")

    if cache:
        _SEASON_CACHE = cache
        _SEASON_CACHE_TS = datetime.now(timezone.utc)
    return _SEASON_CACHE


# ------------------------------------------------------------------
# Upserts
# ------------------------------------------------------------------

async def _upsert_team(db: AsyncSession, t: dict) -> int:
    result = await db.execute(
        text("""
            INSERT INTO teams (api_id, name, sport, logo_url, tracked)
            VALUES (:api_id, :name, 'football', :logo, :tracked)
            ON CONFLICT (api_id) DO UPDATE SET
                name     = EXCLUDED.name,
                logo_url = COALESCE(EXCLUDED.logo_url, teams.logo_url)
            RETURNING id
        """),
        {
            "api_id":  t["id"],
            "name":    t["name"],
            "logo":    t.get("logo"),
            "tracked": t["id"] in TRACKED_TEAMS,
        },
    )
    return result.scalar()


async def _league_internal_id(db: AsyncSession, api_league_id: int) -> int | None:
    r = await db.execute(
        text("SELECT id FROM leagues WHERE api_id = :aid"),
        {"aid": api_league_id},
    )
    row = r.fetchone()
    return row[0] if row else None


# ------------------------------------------------------------------
# Fetch por LIGA (muito mais eficiente que por time)
# ------------------------------------------------------------------

async def fetch_fixtures_for_league(db: AsyncSession, league_api_id: int) -> int:
    """
    Busca TODOS os jogos dos próximos 21 dias da liga.
    Filtra para salvar apenas jogos envolvendo times rastreados.
    Uso de API-Football: 1 requisição por liga por rodada (6 total).
    """
    async with httpx.AsyncClient() as client:
        seasons = await _refresh_current_seasons(client)
        season = seasons.get(league_api_id)
        if not season:
            print(f"[fixtures] sem season current para league {league_api_id}, pulando")
            return 0

        now = datetime.now(timezone.utc)
        params = {
            "league":   league_api_id,
            "season":   season,
            "from":     now.strftime("%Y-%m-%d"),
            "to":       (now + timedelta(days=21)).strftime("%Y-%m-%d"),
            "timezone": "America/Sao_Paulo",
        }
        data = await _get(client, "/fixtures", params)

    saved = 0
    internal_league_id = await _league_internal_id(db, league_api_id)
    if not internal_league_id:
        return 0

    for f in data.get("response", []):
        fix   = f["fixture"]
        teams = f["teams"]
        goals = f["goals"]

        # Filtra: salva apenas jogos envolvendo ao menos um time rastreado
        if teams["home"]["id"] not in TRACKED_TEAMS and teams["away"]["id"] not in TRACKED_TEAMS:
            continue

        broadcast_list = [
            b["channel"] for b in f.get("broadcasts", []) if b.get("channel")
        ]

        home_id = await _upsert_team(db, teams["home"])
        away_id = await _upsert_team(db, teams["away"])
        scheduled = datetime.fromisoformat(
            fix["date"].replace("Z", "+00:00")
        ).replace(tzinfo=None)

        await db.execute(
            text("""
                INSERT INTO matches
                    (api_id, sport, league_id, home_team_id, away_team_id,
                     scheduled_at, venue, status, home_score, away_score,
                     season, broadcast, broadcast_src, fetched_at)
                VALUES
                    (:api_id, 'football', :league_id, :home_id, :away_id,
                     :sched, :venue, :status, :hs, :as_, :season,
                     CAST(:broadcast AS JSONB), 'api', NOW())
                ON CONFLICT (api_id) DO UPDATE SET
                    status       = EXCLUDED.status,
                    home_score   = EXCLUDED.home_score,
                    away_score   = EXCLUDED.away_score,
                    scheduled_at = EXCLUDED.scheduled_at,
                    broadcast    = CASE WHEN EXCLUDED.broadcast::text != '[]'
                                        THEN EXCLUDED.broadcast
                                        ELSE matches.broadcast END,
                    fetched_at   = NOW()
            """),
            {
                "api_id":    fix["id"],
                "league_id": internal_league_id,
                "home_id":   home_id,
                "away_id":   away_id,
                "sched":     scheduled,
                "venue":     (fix.get("venue") or {}).get("name"),
                "status":    fix["status"]["short"],
                "hs":        goals.get("home"),
                "as_":       goals.get("away"),
                "season":    season,
                "broadcast": json.dumps(broadcast_list),
            },
        )
        saved += 1

    await db.commit()

    # Atualiza a temporada também na tabela leagues
    await db.execute(
        text("UPDATE leagues SET season = :s, updated_at = NOW() WHERE api_id = :aid"),
        {"s": season, "aid": league_api_id},
    )
    await db.commit()

    return saved


async def fetch_all_leagues_fixtures(db: AsyncSession) -> dict[int, int]:
    """Sincroniza todas as ligas rastreadas. Resistente a falhas individuais."""
    results = {}
    for lid in TRACKED_LEAGUES:
        try:
            n = await fetch_fixtures_for_league(db, lid)
            results[lid] = n
            print(f"[fixtures] league {lid}: {n} jogos")
        except Exception as e:
            print(f"[fixtures] erro league {lid}: {e}")
            results[lid] = -1
    return results


# ------------------------------------------------------------------
# Standings
# ------------------------------------------------------------------

async def fetch_standings(db: AsyncSession, league_api_id: int) -> int:
    async with httpx.AsyncClient() as client:
        seasons = await _refresh_current_seasons(client)
        season = seasons.get(league_api_id)
        if not season:
            return 0

        params = {"league": league_api_id, "season": season}
        data = await _get(client, "/standings", params)

    saved = 0
    for league_block in data.get("response", []):
        for group in league_block.get("league", {}).get("standings", []):
            for entry in group:
                team_id = await _upsert_team(db, entry["team"])
                league_id = await _league_internal_id(db, league_api_id)
                if not league_id:
                    continue
                all_stats = entry["all"]
                goals = all_stats.get("goals", {})
                await db.execute(
                    text("""
                        INSERT INTO standings
                            (league_id, team_id, season, position, played,
                             won, drawn, lost, goals_for, goals_against,
                             points, form, updated_at)
                        VALUES
                            (:lid, :tid, :season, :pos, :p,
                             :w, :d, :l, :gf, :ga,
                             :pts, :form, NOW())
                        ON CONFLICT (league_id, team_id, season) DO UPDATE SET
                            position      = EXCLUDED.position,
                            played        = EXCLUDED.played,
                            won           = EXCLUDED.won,
                            drawn         = EXCLUDED.drawn,
                            lost          = EXCLUDED.lost,
                            goals_for     = EXCLUDED.goals_for,
                            goals_against = EXCLUDED.goals_against,
                            points        = EXCLUDED.points,
                            form          = EXCLUDED.form,
                            updated_at    = NOW()
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
                saved += 1
    await db.commit()
    return saved


async def fetch_all_standings(db: AsyncSession) -> dict[int, int]:
    results = {}
    for lid in TRACKED_LEAGUES:
        try:
            n = await fetch_standings(db, lid)
            results[lid] = n
        except Exception as e:
            print(f"[standings] erro league {lid}: {e}")
            results[lid] = -1
    return results
