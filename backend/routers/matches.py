from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timezone, timedelta

from database import get_db

router = APIRouter(prefix="/matches", tags=["matches"])


def _row_to_match(row) -> dict:
    return {
        "id":           row.id,
        "sport":        row.sport,
        "league":       {"id": row.league_id, "name": row.league_name, "logo": row.league_logo},
        "home_team":    {"id": row.home_id,   "name": row.home_name,   "logo": row.home_logo},
        "away_team":    {"id": row.away_id,   "name": row.away_name,   "logo": row.away_logo},
        "scheduled_at": row.scheduled_at,
        "venue":        row.venue,
        "status":       row.status,
        "score": {
            "home": row.home_score,
            "away": row.away_score,
        },
        "broadcast":    row.broadcast or [],
    }


_MATCH_SELECT = """
    SELECT
        m.id,  m.sport,  m.league_id,  m.venue,
        m.status, m.home_score, m.away_score,
        m.scheduled_at, m.broadcast,
        l.name  AS league_name,  l.logo_url AS league_logo,
        ht.id   AS home_id,  ht.name AS home_name,  ht.logo_url AS home_logo,
        at.id   AS away_id,  at.name AS away_name,  at.logo_url AS away_logo
    FROM matches m
    JOIN leagues l  ON l.id = m.league_id
    JOIN teams   ht ON ht.id = m.home_team_id
    JOIN teams   at ON at.id = m.away_team_id
"""


@router.get("/upcoming")
async def upcoming_matches(
    days: int = Query(7, ge=1, le=30, description="Janela em dias a partir de agora"),
    sport: str | None = Query(None, description="'football' ou 'basketball'"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna jogos dos próximos N dias dos times/campeonatos rastreados.
    Filtro: apenas jogos onde ao menos um time tem tracked=1.
    """
    now = datetime.utcnow()
    end = now + timedelta(days=days)

    filters = ["m.scheduled_at BETWEEN :now AND :end", "m.status = 'NS'",
               "(ht.tracked = TRUE OR at.tracked = TRUE)"]
    params: dict = {"now": now, "end": end}

    if sport:
        filters.append("m.sport = :sport")
        params["sport"] = sport

    where = " AND ".join(filters)
    sql = text(f"{_MATCH_SELECT} WHERE {where} ORDER BY m.scheduled_at ASC")
    result = await db.execute(sql, params)
    rows = result.fetchall()
    return [_row_to_match(r) for r in rows]


@router.get("/live")
async def live_matches(db: AsyncSession = Depends(get_db)):
    """Jogos em andamento agora."""
    sql = text(f"{_MATCH_SELECT} WHERE m.status IN ('1H','HT','2H','ET','BT','P') ORDER BY m.scheduled_at")
    result = await db.execute(sql)
    return [_row_to_match(r) for r in result.fetchall()]


@router.get("/recent")
async def recent_matches(
    days: int = Query(3, ge=1, le=14),
    db: AsyncSession = Depends(get_db),
):
    """Últimos resultados."""
    since = datetime.utcnow() - timedelta(days=days)
    sql = text(
        f"{_MATCH_SELECT} WHERE m.status = 'FT' AND m.scheduled_at >= :since "
        "AND (ht.tracked = TRUE OR at.tracked = TRUE) ORDER BY m.scheduled_at DESC"
    )
    result = await db.execute(sql, {"since": since})
    return [_row_to_match(r) for r in result.fetchall()]
