"""StatsBomb open-data loader: events + lineups -> per-player-season stats."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from data_pipeline.cache import get_json

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

STAT_COLS = [
    "shots", "goals", "xg", "passes", "passes_completed", "key_passes",
    "dribbles", "dribbles_completed", "carries", "tackles", "interceptions",
    "pressures", "aerial_duels", "aerial_duels_won",
]


def competitions() -> list[dict]:
    return get_json(f"{BASE}/competitions.json")


def matches(competition_id: int, season_id: int) -> list[dict]:
    return get_json(f"{BASE}/matches/{competition_id}/{season_id}.json")


def events(match_id: int) -> list[dict]:
    return get_json(f"{BASE}/events/{match_id}.json")


def lineups(match_id: int) -> list[dict]:
    return get_json(f"{BASE}/lineups/{match_id}.json")


def _to_minutes(ts: str | None, default: float) -> float:
    """'MM:SS' -> minutes as float."""
    if not ts:
        return default
    m, s = ts.split(":")[:2]
    return int(m) + int(s) / 60


def match_minutes(lineup: list[dict], match_length: float) -> dict[int, tuple[float, str | None]]:
    """player_id -> (minutes played, primary position) from lineup position spans."""
    out: dict[int, tuple[float, str | None]] = {}
    for team in lineup:
        for p in team["lineup"]:
            spans = p.get("positions", [])
            if not spans:
                continue  # unused substitute
            played: dict[str, float] = defaultdict(float)
            for sp in spans:
                start = _to_minutes(sp.get("from"), 0.0)
                end = _to_minutes(sp.get("to"), match_length)
                played[sp["position"]] += max(end - start, 0.0)
            total = sum(played.values())
            if total > 0:
                out[p["player_id"]] = (total, max(played, key=played.get))
    return out


def aggregate_match(evts: list[dict]) -> dict[int, dict]:
    """Count on-ball actions per player for one match."""
    agg: dict[int, dict] = defaultdict(lambda: {c: 0 for c in STAT_COLS} | {"team": None})
    for e in evts:
        player = e.get("player")
        if not player:
            continue
        a = agg[player["id"]]
        a["team"] = e["team"]["name"]
        a["name"] = player["name"]
        t = e["type"]["name"]
        if t == "Shot":
            a["shots"] += 1
            a["xg"] += e["shot"].get("statsbomb_xg", 0.0)
            if e["shot"]["outcome"]["name"] == "Goal":
                a["goals"] += 1
        elif t == "Pass":
            p = e["pass"]
            a["passes"] += 1
            if "outcome" not in p:  # no outcome == completed
                a["passes_completed"] += 1
            if p.get("shot_assist") or p.get("goal_assist"):
                a["key_passes"] += 1
        elif t == "Dribble":
            a["dribbles"] += 1
            if e["dribble"]["outcome"]["name"] == "Complete":
                a["dribbles_completed"] += 1
        elif t == "Carry":
            a["carries"] += 1
        elif t == "Interception":
            a["interceptions"] += 1
        elif t == "Pressure":
            a["pressures"] += 1
        elif t == "Duel":
            d = e.get("duel", {})
            if d.get("type", {}).get("name") == "Tackle":
                a["tackles"] += 1
        # Aerial contests are logged on the pass/clearance/shot via `aerial_won`
        for key in ("clearance", "pass", "shot"):
            if key in e and e[key].get("aerial_won"):
                a["aerial_duels"] += 1
                a["aerial_duels_won"] += 1
        if t == "Miscontrol" and e.get("miscontrol", {}).get("aerial_won"):
            a["aerial_duels"] += 1
            a["aerial_duels_won"] += 1
    return agg


def player_season_stats(competition_id: int, season_id: int, max_matches: int | None = None) -> pd.DataFrame:
    """Aggregate every match of a competition-season into one row per player/team."""
    ms = matches(competition_id, season_id)
    if max_matches:
        ms = ms[:max_matches]
    rows: dict[tuple[int, str], dict] = {}
    meta = {}
    for m in ms:
        mid = m["match_id"]
        evts = events(mid)
        length = max((e.get("minute", 0) for e in evts), default=90) + 1
        mins = match_minutes(lineups(mid), float(length))
        country = {}
        for team in lineups(mid):
            for p in team["lineup"]:
                c = (p.get("country") or {}).get("name")
                country[p["player_id"]] = c
        per_player = aggregate_match(evts)
        for pid, (minutes, pos) in mins.items():
            stats = per_player.get(pid)
            if stats is None:
                continue
            key = (pid, stats["team"])
            r = rows.setdefault(key, {
                "source": "statsbomb", "source_player_id": pid,
                "player_name": stats.get("name"), "country": country.get(pid),
                "competition_id": competition_id, "season_id": season_id,
                "team": stats["team"], "matches": 0, "minutes": 0.0,
                **{c: 0 for c in STAT_COLS}, "_pos": defaultdict(float),
            })
            r["matches"] += 1
            r["minutes"] += minutes
            r["_pos"][pos] += minutes
            for c in STAT_COLS:
                r[c] += stats[c]
        meta = m
    out = []
    for r in rows.values():
        pos = r.pop("_pos")
        r["primary_position"] = max(pos, key=pos.get) if pos else None
        r["competition"] = meta.get("competition", {}).get("competition_name", "")
        r["season"] = meta.get("season", {}).get("season_name", "")
        out.append(r)
    return pd.DataFrame(out)
