"""
Fetcher usando football-data.org (free tier, sem limite diário, temporada atual).
Cadastro gratuito em: https://www.football-data.org/client/register
"""
import json
import os
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = "https://api.football-data.org/v4"

# Mapeamento: nosso api_id interno → código da competição no football-data.org
# Competições disponíveis no plano gratuito
LEAGUE_MAP = {
    2:  "CL",   # UEFA Champions League
    3:  "EL",   # UEFA Europa League
    71: "BSA",  # Brasileirão Série A
    73: "CB",   # Copa do Brasil
}

# Libertadores (13) e Sul-Americana (11) não estão disponíveis no plano free
# Serão ignoradas silenciosamente

# Nomes dos times que rastreamos de perto (como aparecem na football-data.org)
TRACKED_NAMES = {
    # Brasileiros (nomes como aparecem no football-data.org)
    "São Paulo FC",
    "Santos FC",
    "SC Corinthians Paulista",
    "SE Palmeiras",
    "CR Flamengo",
    # Europeus
    "FC Barcelona",
    "Manchester City FC",
    "FC Bayern München",
}


def _headers() -> dict:
    return {"X-Auth-Token": API_KEY}


async def _get(client: httpx.AsyncClient, path: str, params: dict = {}) -> dict:
    r = await client.get(
        f"{BASE_URL}{path}", params=params,
        headers=_headers(), timeout=20
    )
    r.raise_for_status()
    return r.json()


def _is_tracked(name: str) -> bool:
    name_lower = name.lower()
    return any(t.lower() in name_lower or name_lower in t.lower() for t in TRACKED_NAMES)


# ------------------------------------------------------------------
# Upserts
# ------------------------------------------------------------------

async def _upsert_team_fd(db: AsyncSession, team: dict) -> int:
    """
    football-data.org usa IDs diferentes do API-Football.
    Usamos prefixo 9000000+ para não colidir com seeds antigos.
    """
    api_id = 9_000_000 + int(team["id"])
    result = await db.execute(
        text("""
            INSERT INTO teams (api_id, name, sport, logo_url, tracked)
            VALUES (:api_id, :name, 'football', :logo, :tracked)
            ON CONFLICT (api_id) DO UPDATE SET
                name     = EXCLUDED.name,
                logo_url = COALESCE(EXCLUDED.logo_url, teams.logo_url),
                tracked  = EXCLUDED.tracked
            RETURNING id
        """),
        {
            "api_id":  api_id,
            "name":    team.get("name") or team.get("shortName", ""),
            "logo":    team.get("crest"),
            "tracked": _is_tracked(team.get("name", "") or team.get("shortName", "")),
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


def _parse_status(fd_status: str) -> str:
    """Converte status do football-data.org para nosso padrão."""
    return {
        "SCHEDULED":    "NS",
        "TIMED":        "NS",
        "IN_PLAY":      "1H",
        "PAUSED":       "HT",
        "FINISHED":     "FT",
        "POSTPONED":    "PST",
        "CANCELLED":    "CANC",
        "SUSPENDED":    "CANC",
    }.get(fd_status, "NS")


# ------------------------------------------------------------------
# Fetch de fixtures por liga
# ------------------------------------------------------------------

async def fetch_fixtures_for_league(db: AsyncSession, league_api_id: int) -> int:
    code = LEAGUE_MAP.get(league_api_id)
    if not code:
        return 0  # competição não disponível no plano free

    internal_league_id = await _league_internal_id(db, league_api_id)
    if not internal_league_id:
        return 0

    now = datetime.now(timezone.utc)
    date_from = now.strftime("%Y-%m-%d")
    date_to   = (now + timedelta(days=21)).strftime("%Y-%m-%d")

    try:
        async with httpx.AsyncClient() as client:
            data = await _get(
                client,
                f"/competitions/{code}/matches",
                {"status": "SCHEDULED,IN_PLAY,PAUSED,TIMED", "dateFrom": date_from, "dateTo": date_to},
            )
    except httpx.HTTPStatusError as e:
        print(f"[fixtures] {code}: HTTP {e.response.status_code}")
        return 0

    saved = 0
    season_year = datetime.now(timezone.utc).year

    for m in data.get("matches", []):
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})

        if not home.get("id") or not away.get("id"):
            continue

        home_id = await _upsert_team_fd(db, home)
        away_id = await _upsert_team_fd(db, away)

        scheduled = datetime.fromisoformat(
            m["utcDate"].replace("Z", "+00:00")
        ).replace(tzinfo=None)

        score = m.get("score", {}).get("fullTime", {})
        season_obj = m.get("season", {})
        try:
            season_year = int((season_obj.get("startDate") or str(now.year))[:4])
        except Exception:
            pass

        api_id = 8_000_000 + int(m["id"])

        await db.execute(
            text("""
                INSERT INTO matches
                    (api_id, sport, league_id, home_team_id, away_team_id,
                     scheduled_at, status, home_score, away_score,
                     season, broadcast, broadcast_src, fetched_at)
                VALUES
                    (:api_id, 'football', :league_id, :home_id, :away_id,
                     :sched, :status, :hs, :as_,
                     :season, CAST(:broadcast AS JSONB), 'api', NOW())
                ON CONFLICT (api_id) DO UPDATE SET
                    status       = EXCLUDED.status,
                    home_score   = EXCLUDED.home_score,
                    away_score   = EXCLUDED.away_score,
                    scheduled_at = EXCLUDED.scheduled_at,
                    fetched_at   = NOW()
            """),
            {
                "api_id":    api_id,
                "league_id": internal_league_id,
                "home_id":   home_id,
                "away_id":   away_id,
                "sched":     scheduled,
                "status":    _parse_status(m.get("status", "SCHEDULED")),
                "hs":        score.get("home"),
                "as_":       score.get("away"),
                "season":    season_year,
                "broadcast": json.dumps([]),
            },
        )
        saved += 1

    await db.commit()
    return saved


async def fetch_all_leagues_fixtures(db: AsyncSession) -> dict:
    results = {}
    for lid in LEAGUE_MAP:
        try:
            n = await fetch_fixtures_for_league(db, lid)
            print(f"[fixtures] league {lid}: {n} jogos")
            results[lid] = n
        except Exception as e:
            print(f"[fixtures] erro league {lid}: {e}")
            results[lid] = -1
    return results


# ------------------------------------------------------------------
# Standings
# ------------------------------------------------------------------

async def fetch_standings(db: AsyncSession, league_api_id: int) -> int:
    code = LEAGUE_MAP.get(league_api_id)
    if not code:
        return 0

    internal_league_id = await _league_internal_id(db, league_api_id)
    if not internal_league_id:
        return 0

    try:
        async with httpx.AsyncClient() as client:
            data = await _get(client, f"/competitions/{code}/standings")
    except httpx.HTTPStatusError as e:
        print(f"[standings] {code}: HTTP {e.response.status_code}")
        return 0

    season_year = datetime.now(timezone.utc).year
    try:
        season_year = int(data.get("season", {}).get("startDate", "")[:4] or season_year)
    except Exception:
        pass

    saved = 0
    for group in data.get("standings", []):
        if group.get("type") != "TOTAL":
            continue
        for entry in group.get("table", []):
            team_id = await _upsert_team_fd(db, entry["team"])
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
                    "lid":    internal_league_id,
                    "tid":    team_id,
                    "season": season_year,
                    "pos":    entry["position"],
                    "p":      entry.get("playedGames", 0),
                    "w":      entry.get("won", 0),
                    "d":      entry.get("draw", 0),
                    "l":      entry.get("lost", 0),
                    "gf":     entry.get("goalsFor", 0),
                    "ga":     entry.get("goalsAgainst", 0),
                    "pts":    entry.get("points", 0),
                    "form":   entry.get("form"),
                },
            )
            saved += 1
    await db.commit()
    return saved


async def fetch_all_standings(db: AsyncSession) -> dict:
    results = {}
    for lid in LEAGUE_MAP:
        try:
            n = await fetch_standings(db, lid)
            results[lid] = n
        except Exception as e:
            print(f"[standings] erro league {lid}: {e}")
            results[lid] = -1
    return results
