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
CREATE TABLE IF NOT EXISTS understat_player_seasons (
    understat_player_id INTEGER NOT NULL,
    player_name  TEXT NOT NULL,
    league       TEXT NOT NULL,
    season       INTEGER NOT NULL,   -- start year, e.g. 2023 = 2023/24
    team         TEXT NOT NULL,
    position     TEXT,
    games        INTEGER, minutes INTEGER,
    goals        INTEGER, assists INTEGER, shots INTEGER, key_passes INTEGER,
    xg REAL, xa REAL, npg INTEGER, npxg REAL, xg_chain REAL, xg_buildup REAL,
    yellow_cards INTEGER, red_cards INTEGER,
    PRIMARY KEY (understat_player_id, league, season, team)
);
CREATE TABLE IF NOT EXISTS transfermarkt_squads (
    tm_player_id INTEGER NOT NULL,
    season       INTEGER NOT NULL,   -- start year, same convention as Understat
    league       TEXT NOT NULL,
    club_id      INTEGER NOT NULL,
    club_name    TEXT NOT NULL,
    player_name  TEXT NOT NULL,
    position     TEXT,
    birth_date   TEXT,               -- ISO date
    nationality  TEXT,               -- primary (first listed)
    nationalities TEXT,              -- all, '|' separated
    height_cm    INTEGER,
    foot         TEXT,
    market_value_eur INTEGER,
    PRIMARY KEY (tm_player_id, season, club_id)
);
CREATE TABLE IF NOT EXISTS transfermarkt_market_values (
    tm_player_id INTEGER NOT NULL,
    date         TEXT NOT NULL,
    value_eur    INTEGER NOT NULL,
    club         TEXT,
    age          INTEGER,
    PRIMARY KEY (tm_player_id, date)
);
CREATE TABLE IF NOT EXISTS transfermarkt_transfers (
    tm_player_id INTEGER NOT NULL,
    transfer_id  INTEGER NOT NULL,
    date         TEXT,
    season       TEXT,
    from_club    TEXT, from_club_id INTEGER,
    to_club      TEXT, to_club_id   INTEGER,
    fee_text     TEXT,
    fee_eur      INTEGER,
    market_value_eur INTEGER,
    PRIMARY KEY (tm_player_id, transfer_id)
);
CREATE TABLE IF NOT EXISTS understat_tm_links (
    understat_player_id INTEGER NOT NULL,
    tm_player_id INTEGER NOT NULL,
    league  TEXT NOT NULL,
    season  INTEGER NOT NULL,
    score   REAL NOT NULL,
    stage   TEXT NOT NULL,           -- 'name' (global name match) or 'club' (relaxed match inside a learned club)
    PRIMARY KEY (understat_player_id, league, season)
);
CREATE TABLE IF NOT EXISTS fbref_player_seasons (
    league TEXT NOT NULL, season INTEGER NOT NULL, team TEXT NOT NULL, player_name TEXT NOT NULL,
    nation TEXT, pos TEXT, born INTEGER, age INTEGER,
    matches INTEGER, starts INTEGER, minutes INTEGER, goals INTEGER, assists INTEGER,
    pens_made INTEGER, pens_att INTEGER, yellow_cards INTEGER, red_cards INTEGER,
    fouls INTEGER, fouled INTEGER, offsides INTEGER, crosses INTEGER,
    interceptions INTEGER, tackles_won INTEGER,
    PRIMARY KEY (league, season, team, player_name)
);
CREATE TABLE IF NOT EXISTS fbref_keeper_seasons (
    league TEXT NOT NULL, season INTEGER NOT NULL, team TEXT NOT NULL, player_name TEXT NOT NULL,
    nation TEXT, born INTEGER, age INTEGER,
    matches INTEGER, starts INTEGER, minutes INTEGER,
    goals_against INTEGER, shots_on_target_against INTEGER, saves INTEGER,
    wins INTEGER, draws INTEGER, losses INTEGER, clean_sheets INTEGER,
    pk_att INTEGER, pk_allowed INTEGER, pk_saved INTEGER, pk_missed INTEGER,
    PRIMARY KEY (league, season, team, player_name)
);
CREATE TABLE IF NOT EXISTS fbref_tm_links (
    league TEXT NOT NULL, season INTEGER NOT NULL,
    player_name TEXT NOT NULL, born INTEGER NOT NULL,   -- born 0 = unknown
    tm_player_id INTEGER NOT NULL,
    score REAL NOT NULL, stage TEXT NOT NULL,
    PRIMARY KEY (league, season, player_name, born)
);
CREATE INDEX IF NOT EXISTS idx_tm_squads_name ON transfermarkt_squads(player_name);
CREATE INDEX IF NOT EXISTS idx_pss_name ON player_season_stats(player_name);
"""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)  # long scrapes and analysis scripts share this file
    conn.executescript(SCHEMA)
    return conn
