from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/standings", tags=["standings"])


@router.get("/{league_api_id}")
async def get_standings(
    league_api_id: int,
    season: int = Query(2025),
    db: AsyncSession = Depends(get_db),
):
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
