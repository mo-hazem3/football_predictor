"""Understat loader (player season stats + xG/xA) via its public JSON endpoint.

soccerdata's Understat reader uses a TLS client that ignores HTTP proxies, so
we call the same endpoint with plain `requests` through the shared cache.
"""
from __future__ import annotations

import html

import pandas as pd

from data_pipeline.cache import get_json

LEAGUES = ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
URL = "https://understat.com/getLeagueData/{league}/{season}"
MIN_INTERVAL_S = 1.0  # be gentle with a small site

_INT = ["games", "time", "goals", "assists", "shots", "key_passes", "yellow_cards", "red_cards", "npg"]
_FLOAT = ["xG", "xA", "npxG", "xGChain", "xGBuildup"]


def fetch_league_payload(league: str, season: int) -> dict:
    """The whole league payload ('players', 'teams' with per-match history, 'dates'); cached on disk."""
    return get_json(
        URL.format(league=league, season=season),
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{league}/{season}"},
        min_interval=MIN_INTERVAL_S,
    )


def fetch_league_season(league: str, season: int) -> list[dict]:
    return fetch_league_payload(league, season)["players"]


def to_frame(players: list[dict], league: str, season: int) -> pd.DataFrame:
    """Normalise Understat's all-strings payload into typed columns."""
    rows = []
    for p in players:
        row = {
            "understat_player_id": int(p["id"]),
            "player_name": html.unescape(p["player_name"]),  # payload has entities like &#039;
            "league": league,
            "season": season,
            "team": html.unescape(p["team_title"]),
            "position": p.get("position"),
            "minutes": int(p["time"]),
        }
        for k in _INT:
            if k != "time":
                row[k] = int(p[k])
        for k in _FLOAT:
            row[k.lower().replace("xgchain", "xg_chain").replace("xgbuildup", "xg_buildup")] = float(p[k])
        rows.append(row)
    return pd.DataFrame(rows)
