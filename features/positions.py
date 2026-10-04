"""Collapse Transfermarkt / Understat position labels into comparable groups.

Five groups, because wingers/attacking mids and centre-forwards produce very
different shot/chance profiles, while finer splits leave too few players per
league-season for percentiles to mean anything.
"""
from __future__ import annotations

GROUPS = ["GK", "DEF", "MID", "WING_AM", "FWD"]

_TM = {
    "Goalkeeper": "GK",
    "Centre-Back": "DEF", "Left-Back": "DEF", "Right-Back": "DEF", "Defender": "DEF",
    "Defensive Midfield": "MID", "Central Midfield": "MID", "Left Midfield": "MID",
    "Right Midfield": "MID", "Midfielder": "MID",
    "Attacking Midfield": "WING_AM", "Left Winger": "WING_AM", "Right Winger": "WING_AM",
    "Centre-Forward": "FWD", "Second Striker": "FWD", "Striker": "FWD",
}

# Understat lists every position played, e.g. 'F M S' ('S' = appeared as substitute).
_US = {"GK": "GK", "D": "DEF", "M": "MID", "F": "FWD"}


def from_transfermarkt(position: str | None) -> str | None:
    return _TM.get(position) if position else None


def from_understat(position: str | None) -> str | None:
    """Coarse fallback for players we could not link: the first listed non-sub position."""
    for token in (position or "").split():
        if token in _US:
            return _US[token]
    return None


def position_group(tm_position: str | None, understat_position: str | None) -> str | None:
    return from_transfermarkt(tm_position) or from_understat(understat_position)
