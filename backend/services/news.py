"""
Agregador de notícias via Google News RSS.
Gratuito, sem chave, atualizado em tempo real pelo Google.
"""
import re
import httpx
from xml.etree import ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

# Chave interna → query Google News
FEEDS = {
    "sao-paulo":   ('"São Paulo FC"',           "pt-BR", "BR", "BR:pt-419"),
    "santos":      ('"Santos FC"',              "pt-BR", "BR", "BR:pt-419"),
    "corinthians": ('"Corinthians" futebol',    "pt-BR", "BR", "BR:pt-419"),
    "palmeiras":   ('"Palmeiras" futebol',      "pt-BR", "BR", "BR:pt-419"),
    "flamengo":    ('"Flamengo" futebol',       "pt-BR", "BR", "BR:pt-419"),
    "celtics":     ('"Boston Celtics"',         "en-US", "US", "US:en"),
}

LABELS = {
    "sao-paulo":   "São Paulo",
    "santos":      "Santos",
    "corinthians": "Corinthians",
    "palmeiras":   "Palmeiras",
    "flamengo":    "Flamengo",
    "celtics":     "Boston Celtics",
}


def _build_url(query: str, hl: str, gl: str, ceid: str) -> str:
    from urllib.parse import quote_plus
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


async def fetch_news(team_key: str, limit: int = 20) -> list[dict]:
    cfg = FEEDS.get(team_key)
    if not cfg:
        return []

    url = _build_url(*cfg)
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 SportsHub/1.0"},
            )
            r.raise_for_status()
    except Exception as e:
        print(f"[news] erro {team_key}: {e}")
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"[news] parse erro {team_key}: {e}")
        return []

    items = []
    for item in root.findall(".//item")[:limit]:
        title = _strip_html(item.findtext("title", ""))
        link  = item.findtext("link", "").strip()
        pub   = item.findtext("pubDate", "")

        # Tenta extrair fonte (Google News coloca " - Fonte" no título)
        m = re.match(r"^(.+?) - ([^-]+)$", title)
        if m:
            clean_title = m.group(1).strip()
            source = m.group(2).strip()
        else:
            clean_title = title
            source = ""

        try:
            published_iso = parsedate_to_datetime(pub).isoformat() if pub else None
        except Exception:
            published_iso = pub

        items.append({
            "title":     clean_title,
            "link":      link,
            "source":    source,
            "published": published_iso,
        })
    return items
