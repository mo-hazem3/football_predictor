"""SQLite storage for pipeline output."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "db" / "football.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_season_stats (
    source          TEXT NOT NULL,
    source_player_id INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    country         TEXT,
    competition_id  INTEGER NOT NULL,
    season_id       INTEGER NOT NULL,
    competition     TEXT NOT NULL,
    season          TEXT NOT NULL,
    team            TEXT,
    primary_position TEXT,
    matches         INTEGER NOT NULL,
    minutes         REAL NOT NULL,
    shots           INTEGER, goals INTEGER, xg REAL,
    passes          INTEGER, passes_completed INTEGER, key_passes INTEGER,
    dribbles        INTEGER, dribbles_completed INTEGER,
    carries         INTEGER,
    tackles         INTEGER, interceptions INTEGER, pressures INTEGER,
    aerial_duels    INTEGER, aerial_duels_won INTEGER,
    PRIMARY KEY (source, source_player_id, competition_id, season_id, team)
);
CREATE INDEX IF NOT EXISTS idx_pss_name ON player_season_stats(player_name);
"""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
