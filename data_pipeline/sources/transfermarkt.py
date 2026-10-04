"""Transfermarkt loader: squads (bio + market value), market-value history, transfer history.

Squad pages give every player's birth date, nationality(ies), position and
market value for a club-season, which is what entity resolution and the age
features need. Per-player market-value and transfer history come from the
site's own JSON endpoints (the ones its charts use) and are fetched on demand.

All requests go through the shared disk cache with a slow, polite interval.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from data_pipeline.cache import get_html, get_json

BASE = "https://www.transfermarkt.com"
HEADERS = {"Accept-Language": "en-US,en;q=0.9"}
MIN_INTERVAL_S = 3.0

# Understat league name -> (Transfermarkt slug, competition code).
# Transfermarkt's saison_id is the season start year, same as Understat's.
COMPETITIONS = {
    "EPL": ("premier-league", "GB1"),
    "La_liga": ("laliga", "ES1"),
    "Bundesliga": ("bundesliga", "L1"),
    "Serie_A": ("serie-a", "IT1"),
    "Ligue_1": ("ligue-1", "FR1"),
}

_MULTIPLIER = {"bn": 1_000_000_000, "m": 1_000_000, "k": 1_000, "": 1}


def parse_money(text: str | None) -> int | None:
    """'€40.63m' -> 40630000, '€500k' -> 500000, '€1.46bn' -> 1460000000, '-'/'?'/'' -> None."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(bn|m|k)?\s*$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    return round(float(m.group(1)) * _MULTIPLIER[(m.group(2) or "").lower()])


def parse_date(text: str | None) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except (AttributeError, ValueError):
        return None


# ---------------------------------------------------------------- competition → clubs

def competition_url(league: str, season: int) -> str:
    slug, code = COMPETITIONS[league]
    return f"{BASE}/{slug}/startseite/wettbewerb/{code}/plus/?saison_id={season}"


def parse_clubs(html: str) -> list[dict]:
    """Clubs listed on a competition-season page: [{club_id, slug, name}]."""
    soup = BeautifulSoup(html, "lxml")
    clubs, seen = [], set()
    for a in soup.select("table.items td.hauptlink a[href*='/startseite/verein/']"):
        m = re.match(r"/([^/]+)/startseite/verein/(\d+)", a["href"])
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            clubs.append({"club_id": int(m.group(2)), "slug": m.group(1), "name": a.get_text(strip=True)})
    return clubs


def fetch_clubs(league: str, season: int) -> list[dict]:
    return parse_clubs(get_html(competition_url(league, season), headers=HEADERS, min_interval=MIN_INTERVAL_S))


# ---------------------------------------------------------------- club → squad

def squad_url(club: dict, season: int) -> str:
    return f"{BASE}/{club['slug']}/kader/verein/{club['club_id']}/saison_id/{season}/plus/1"


_DOB = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*\(\d+\)$")
_HEIGHT = re.compile(r"^(\d),(\d{2})\s*m$")


def parse_squad(html: str, club: dict, season: int, league: str) -> list[dict]:
    """One dict per player on a club-season squad page (cells are matched by content, not column index)."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.items")
    if table is None:
        return []
    rows = []
    for tr in table.select("tbody > tr"):
        cells = tr.find_all("td", recursive=False)
        link = tr.select_one("td.hauptlink a[href*='/profil/spieler/']")
        if not link or not cells:
            continue
        pid = int(re.search(r"/spieler/(\d+)", link["href"]).group(1))
        inner = tr.select_one("table.inline-table")
        inner_rows = inner.find_all("tr", recursive=False) if inner else []
        position = inner_rows[1].get_text(strip=True) if len(inner_rows) > 1 else None

        birth_date = height = foot = None
        for c in cells:
            text = c.get_text(" ", strip=True)
            if birth_date is None and (m := _DOB.match(text)):
                birth_date = parse_date(m.group(1))
            elif height is None and (m := _HEIGHT.match(text)):
                height = int(m.group(1)) * 100 + int(m.group(2))
            elif foot is None and text in ("left", "right", "both"):
                foot = text
        flags = [img["title"] for img in tr.select("img.flaggenrahmen") if img.get("title")]
        # Dual nationals show several flags in the same cell; the first is the primary one.
        nationalities = list(dict.fromkeys(flags))
        rows.append({
            "tm_player_id": pid,
            "season": season,
            "league": league,
            "club_id": club["club_id"],
            "club_name": club["name"],
            "player_name": link.get_text(strip=True),
            "position": position,
            "birth_date": birth_date.isoformat() if birth_date else None,
            "nationality": nationalities[0] if nationalities else None,
            "nationalities": "|".join(nationalities) or None,
            "height_cm": height,
            "foot": foot,
            "market_value_eur": parse_money(cells[-1].get_text(strip=True)),
        })
    return rows


def fetch_squad(club: dict, season: int, league: str) -> list[dict]:
    html = get_html(squad_url(club, season), headers=HEADERS, min_interval=MIN_INTERVAL_S)
    return parse_squad(html, club, season, league)


# ---------------------------------------------------------------- per-player history (JSON)

def parse_market_values(payload: dict, tm_player_id: int) -> list[dict]:
    rows = []
    for p in payload.get("list", []):
        d = parse_date(p.get("datum_mw"))
        if d is None or p.get("y") is None:
            continue
        rows.append({
            "tm_player_id": tm_player_id,
            "date": d.isoformat(),
            "value_eur": int(p["y"]),
            "club": p.get("verein"),
            "age": int(p["age"]) if str(p.get("age", "")).isdigit() else None,
        })
    return rows


def fetch_market_values(tm_player_id: int) -> list[dict]:
    payload = get_json(f"{BASE}/ceapi/marketValueDevelopment/graph/{tm_player_id}", headers=HEADERS, min_interval=MIN_INTERVAL_S)
    return parse_market_values(payload, tm_player_id)


def _club_id(side: dict) -> int | None:
    m = re.search(r"/verein/(\d+)", side.get("href") or "")
    return int(m.group(1)) if m else None


def parse_transfers(payload: dict, tm_player_id: int) -> list[dict]:
    """Transfer history including youth/reserve moves (the pathway signal).

    `fee_eur` is None for free transfers, loans and unknown fees; the raw text
    is kept in `fee_text` so those cases stay distinguishable.
    """
    rows = []
    for t in payload.get("transfers", []):
        m = re.search(r"/transfer_id/(\d+)", t.get("url") or "")
        if not m or t.get("futureTransfer"):
            continue
        rows.append({
            "tm_player_id": tm_player_id,
            "transfer_id": int(m.group(1)),
            "date": t.get("dateUnformatted"),
            "season": t.get("season"),
            "from_club": t["from"].get("clubName"),
            "from_club_id": _club_id(t["from"]),
            "to_club": t["to"].get("clubName"),
            "to_club_id": _club_id(t["to"]),
            "fee_text": t.get("fee"),
            "fee_eur": None if "loan" in (t.get("fee") or "").lower() else parse_money(t.get("fee")),
            "market_value_eur": parse_money(t.get("marketValue")),
        })
    return rows


def fetch_transfers(tm_player_id: int) -> list[dict]:
    payload = get_json(f"{BASE}/ceapi/transferHistory/list/{tm_player_id}", headers=HEADERS, min_interval=MIN_INTERVAL_S)
    return parse_transfers(payload, tm_player_id)
