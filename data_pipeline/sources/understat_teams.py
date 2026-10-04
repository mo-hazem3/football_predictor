"""Team-level data from Understat: per-match team stats and a tactical-style breakdown.

Two sources, both already how Understat's own pages are built:
  * the league payload (already cached for the player data): per team and match xG for/against,
    PPDA (pressing intensity), deep completions and results   -> team_matches
  * /getTeamData/<team>/<season>: what a team creates and concedes split by situation (open play,
    corners, set pieces), attack speed (fast/normal/slow), shot zone, timing, game state and
    formation                                                 -> team_style (long format)

No event data is needed, so this covers all five leagues for every season, unlike StatsBomb's
open data (which has a single Bundesliga season for one club).
"""
from __future__ import annotations

from data_pipeline.cache import get_json

TEAM_URL = "https://understat.com/getTeamData/{team}/{season}"
MIN_INTERVAL_S = 1.0
STYLE_GROUPS = ["situation", "attackSpeed", "shotZone", "timing", "gameState", "formation", "result"]


def match_rows(payload: dict, league: str, season: int) -> list[dict]:
    """One row per team and match from a league payload's per-team history."""
    rows = []
    for team in payload.get("teams", {}).values():
        for h in team["history"]:
            rows.append({
                "league": league, "season": season, "team": team["title"], "match_date": h["date"],
                "home": 1 if h["h_a"] == "h" else 0,
                "xg": float(h["xG"]), "xga": float(h["xGA"]), "npxg": float(h["npxG"]), "npxga": float(h["npxGA"]),
                "ppda_att": int(h["ppda"]["att"]), "ppda_def": int(h["ppda"]["def"]),
                "ppda_allowed_att": int(h["ppda_allowed"]["att"]), "ppda_allowed_def": int(h["ppda_allowed"]["def"]),
                "deep": int(h["deep"]), "deep_allowed": int(h["deep_allowed"]),
                "scored": int(h["scored"]), "missed": int(h["missed"]), "xpts": float(h["xpts"]), "pts": int(h["pts"]),
            })
    return rows


def team_titles(payload: dict) -> list[str]:
    return sorted(t["title"] for t in payload.get("teams", {}).values())


def fetch_team_data(team: str, season: int) -> dict:
    """The full /getTeamData payload for one team-season ('statistics', 'players', 'dates'); cached on disk."""
    return get_json(
        TEAM_URL.format(team=team.replace(" ", "_"), season=season),
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/team/{team.replace(' ', '_')}/{season}"},
        min_interval=MIN_INTERVAL_S,
    )


def fetch_team_statistics(team: str, season: int) -> dict:
    return fetch_team_data(team, season)["statistics"]


def player_rows(data: dict, league: str, season: int, team: str) -> list[dict]:
    """Club-level player rows: unlike the league payload these are NOT merged across clubs for mid-season movers."""
    return [{
        "league": league, "season": season, "team": team, "understat_player_id": int(p["id"]), "player_name": p["player_name"],
        "position": p.get("position"), "games": int(p["games"]), "minutes": int(p["time"]), "goals": int(p["goals"]),
        "assists": int(p["assists"]), "shots": int(p["shots"]), "key_passes": int(p["key_passes"]),
        "xg": float(p["xG"]), "xa": float(p["xA"]), "npxg": float(p["npxG"]),
        "xg_chain": float(p["xGChain"]), "xg_buildup": float(p["xGBuildup"]),
    } for p in data.get("players", [])]


def style_rows(statistics: dict, league: str, season: int, team: str) -> list[dict]:
    """Flatten the grouped statistics into one row per (group, stat)."""
    rows = []
    for group in STYLE_GROUPS:
        for stat, v in statistics.get(group, {}).items():
            against = v.get("against", {})
            rows.append({
                "league": league, "season": season, "team": team, "grp": group, "stat": stat,
                "time": int(v["time"]) if v.get("time") is not None else None,
                "shots": int(v["shots"]), "goals": int(v["goals"]), "xg": float(v["xG"]),
                "against_shots": int(against.get("shots", 0)), "against_goals": int(against.get("goals", 0)),
                "against_xg": float(against.get("xG", 0.0)),
            })
    return rows
