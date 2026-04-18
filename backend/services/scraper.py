"""
Scraper leve para cruzar canais de TV brasileiros com os jogos já salvos no banco.
Estratégia: GE.Globo lista jogos da semana com canal. Casamos por time + data.

AVISO: Web scraping é frágil. Use como fallback quando a API não retornar broadcast.
A Globo/GE bloqueia bots — use headers realistas e respeite robots.txt em produção.
"""
import json
import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

GE_URL = "https://ge.globo.com/futebol/agenda-de-jogos/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Normaliza nomes parciais para bater com os times do banco
TEAM_ALIASES = {
    "são paulo": "São Paulo FC",
    "spfc": "São Paulo FC",
    "santos": "Santos FC",
    "corinthians": "Corinthians",
    "palmeiras": "Palmeiras",
    "flamengo": "Flamengo",
    "celtics": "Boston Celtics",
}


def _normalize(name: str) -> str:
    return name.lower().strip()


async def _fetch_ge_page() -> str:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(GE_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text


def _parse_ge(html: str) -> list[dict]:
    """
    Retorna lista de dicts:
      {"date": "2025-04-20", "home": "flamengo", "away": "palmeiras", "channels": ["Premiere"]}
    GE renderiza alguns dados via JSON-LD — tentamos isso primeiro, depois HTML.
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Tenta JSON-LD embutido (mais confiável que HTML scraping)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") == "SportsEvent":
                home = _normalize(data.get("homeTeam", {}).get("name", ""))
                away = _normalize(data.get("awayTeam", {}).get("name", ""))
                start = data.get("startDate", "")[:10]
                channels = [data.get("broadcastOfEvent", {}).get("name", "")] if "broadcastOfEvent" in data else []
                if home and away:
                    results.append({"date": start, "home": home, "away": away, "channels": channels})
        except (json.JSONDecodeError, AttributeError):
            continue

    # Fallback: parse HTML das cards de jogos (estrutura GE 2025)
    if not results:
        for card in soup.select("[class*='match-item'], [class*='jogo']"):
            teams = card.select("[class*='team-name'], [class*='time']")
            channel_tag = card.select_one("[class*='channel'], [class*='canal'], [class*='transmissao']")
            date_tag = card.select_one("[class*='date'], [class*='data'], time")
            if len(teams) >= 2:
                results.append({
                    "date":     date_tag.get("datetime", "")[:10] if date_tag else "",
                    "home":     _normalize(teams[0].get_text()),
                    "away":     _normalize(teams[1].get_text()),
                    "channels": [channel_tag.get_text().strip()] if channel_tag else [],
                })

    return results


async def enrich_broadcasts(db: AsyncSession):
    """
    1. Faz scraping do GE
    2. Para cada jogo encontrado, localiza o match no banco por (data ± 1 dia, time name)
    3. Atualiza broadcast se estava vazio ou era da API
    """
    try:
        html = await _fetch_ge_page()
    except Exception as e:
        print(f"[scraper] falha ao buscar GE: {e}")
        return 0

    scraped = _parse_ge(html)
    updated = 0

    for item in scraped:
        if not item["channels"] or not item["date"]:
            continue

        # Resolve alias → nome no banco
        home_name = TEAM_ALIASES.get(item["home"])
        away_name = TEAM_ALIASES.get(item["away"])
        if not home_name and not away_name:
            continue

        name_filter = home_name or away_name
        try:
            match_date = datetime.strptime(item["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        date_from = match_date - timedelta(hours=12)
        date_to   = match_date + timedelta(hours=36)

        # Busca matches onde um dos times casa com o nome
        rows = await db.execute(
            text("""
                SELECT m.id, m.broadcast
                FROM matches m
                JOIN teams ht ON ht.id = m.home_team_id
                JOIN teams at ON at.id = m.away_team_id
                WHERE m.scheduled_at BETWEEN :df AND :dt
                  AND (ht.name = :name OR at.name = :name)
                  AND m.sport = 'football'
            """),
            {"df": date_from, "dt": date_to, "name": name_filter},
        )
        for row in rows.fetchall():
            existing = row[1] or []
            merged   = list(set(existing + item["channels"]))
            await db.execute(
                text("UPDATE matches SET broadcast=:b::jsonb, broadcast_src='scraper' WHERE id=:id"),
                {"b": str(merged).replace("'", '"'), "id": row[0]},
            )
            updated += 1

    await db.commit()
    return updated
