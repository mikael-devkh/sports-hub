from fastapi import APIRouter, HTTPException, Query

from services.news import fetch_news, FEEDS, LABELS

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/teams")
async def list_teams():
    return [{"key": k, "label": LABELS[k]} for k in FEEDS.keys()]


@router.get("/{team_key}")
async def team_news(team_key: str, limit: int = Query(20, ge=1, le=50)):
    if team_key not in FEEDS:
        raise HTTPException(status_code=404, detail="team not found")
    items = await fetch_news(team_key, limit=limit)
    return {"team": LABELS[team_key], "items": items}
