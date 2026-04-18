from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from datetime import datetime

router = APIRouter(prefix="/standings", tags=["standings"])


@router.get("/{league_api_id}")
async def get_standings(
    league_api_id: int,
    season: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Se season não especificado, usa o mais recente disponível no banco
    if not season:
        r = await db.execute(
            text("SELECT MAX(s.season) FROM standings s JOIN leagues l ON l.id = s.league_id WHERE l.api_id = :lid"),
            {"lid": league_api_id},
        )
        season = r.scalar() or datetime.now().year

    sql = text("""
        SELECT
            s.position, s.played, s.won, s.drawn, s.lost,
            s.goals_for, s.goals_against,
            (s.goals_for - s.goals_against) AS goal_diff,
            s.points, s.form,
            t.name AS team_name, t.logo_url AS team_logo, t.tracked,
            l.name AS league_name
        FROM standings s
        JOIN teams   t ON t.id = s.team_id
        JOIN leagues l ON l.id = s.league_id
        WHERE l.api_id = :lid AND s.season = :season
        ORDER BY s.position ASC
    """)
    result = await db.execute(sql, {"lid": league_api_id, "season": season})
    rows = result.fetchall()
    return {
        "league": rows[0].league_name if rows else None,
        "season": season,
        "table": [
            {
                "position":      r.position,
                "team":          {"name": r.team_name, "logo": r.team_logo, "tracked": bool(r.tracked)},
                "played":        r.played,
                "won":           r.won,
                "drawn":         r.drawn,
                "lost":          r.lost,
                "goals_for":     r.goals_for,
                "goals_against": r.goals_against,
                "goal_diff":     r.goal_diff,
                "points":        r.points,
                "form":          r.form,
            }
            for r in rows
        ],
    }
