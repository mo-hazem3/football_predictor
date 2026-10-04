"""CLI: python -m features.build [--min-minutes 450] [--boot 300]

Builds, in the pipeline SQLite database:
  league_strength          factor per league + 95% interval (see league_strength.py)
  player_season_features   one row per Understat player-season: age, position group,
                           per-90 rates, league-adjusted rates, percentiles

Assumptions (also in the README):
  * Age is decimal years on 1 Jan of the season's end year (mid-season).
  * Position group comes from Transfermarkt, falling back to Understat's coarse label.
  * Percentiles only rank players with >= --min-minutes; everyone else gets NaN.
  * `*_pct_league` ranks within (league, season, position group);
    `*_pct_global` ranks within (season, position group) across all leagues,
    using league-adjusted rates, so a striker's 80th percentile means the same everywhere.
  * Understat has no defensive actions or goalkeeper stats, so GK/DEF profiles are
    thin until FBref is added.
"""
from __future__ import annotations

import argparse
import sqlite3

import numpy as np
import pandas as pd

from data_pipeline import db
from features import league_strength
from features.positions import position_group

COUNTS = ["goals", "assists", "npg", "shots", "key_passes", "xg", "xa", "npxg", "xg_chain", "xg_buildup"]
# volume-type attacking rates that are scaled by the league factor
ADJUSTED = ["npxg", "xa", "xg", "shots", "key_passes", "xg_chain", "xg_buildup"]
PERCENTILED = ["npxg", "xa", "shots", "key_passes", "xg_chain", "xg_buildup"]

# FBref (via fbref_tm_links). Defensive actions are ranked within league only: the league factor
# was estimated on attacking output and has not been validated for them.
FBREF_COUNTS = ["tackles_won", "interceptions", "crosses", "fouls", "fouled"]
GK_COUNTS = ["goals_against", "shots_on_target_against", "saves", "clean_sheets"]
FBREF_PERCENTILED = [f"{c}_p90" for c in FBREF_COUNTS]
GK_PERCENTILED = ["save_pct", "gk_sota_p90"]  # without post-shot xG, save% is a noisy quality proxy

_LOAD_SQL = """
SELECT u.understat_player_id AS player_id, u.player_name, u.league, u.season, u.team,
       u.position AS understat_position, u.games, u.minutes,
       u.goals, u.assists, u.npg, u.shots, u.key_passes, u.xg, u.xa, u.npxg, u.xg_chain, u.xg_buildup,
       l.tm_player_id, t.birth_date, t.nationality, t.tm_position
FROM understat_player_seasons u
LEFT JOIN understat_tm_links l
       ON l.understat_player_id = u.understat_player_id AND l.league = u.league AND l.season = u.season
LEFT JOIN (SELECT tm_player_id, season, MIN(birth_date) AS birth_date, MIN(nationality) AS nationality,
                  MIN(position) AS tm_position
           FROM transfermarkt_squads GROUP BY tm_player_id, season) t
       ON t.tm_player_id = l.tm_player_id AND t.season = u.season
"""


def load(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(_LOAD_SQL, conn)


_FBREF_OUTFIELD_SQL = """
SELECT l.tm_player_id, p.league, p.season, SUM(p.minutes) AS fb_minutes,
       SUM(p.tackles_won) AS tackles_won, SUM(p.interceptions) AS interceptions, SUM(p.crosses) AS crosses,
       SUM(p.fouls) AS fouls, SUM(p.fouled) AS fouled
FROM fbref_player_seasons p
JOIN fbref_tm_links l ON l.league = p.league AND l.season = p.season
                     AND l.player_name = p.player_name AND l.born = COALESCE(p.born, 0)
GROUP BY l.tm_player_id, p.league, p.season
"""
_FBREF_KEEPER_SQL = """
SELECT l.tm_player_id, p.league, p.season, SUM(p.minutes) AS gk_minutes,
       SUM(p.goals_against) AS goals_against, SUM(p.shots_on_target_against) AS shots_on_target_against,
       SUM(p.saves) AS saves, SUM(p.clean_sheets) AS clean_sheets
FROM fbref_keeper_seasons p
JOIN fbref_tm_links l ON l.league = p.league AND l.season = p.season
                     AND l.player_name = p.player_name AND l.born = COALESCE(p.born, 0)
GROUP BY l.tm_player_id, p.league, p.season
"""


def load_fbref(conn: sqlite3.Connection) -> pd.DataFrame:
    """FBref outfield + keeper counts per (Transfermarkt player, league, season)."""
    out = pd.read_sql(_FBREF_OUTFIELD_SQL, conn)
    gk = pd.read_sql(_FBREF_KEEPER_SQL, conn)
    return out.merge(gk, on=["tm_player_id", "league", "season"], how="outer")


def add_fbref_features(df: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    """Attach FBref counts via the Transfermarkt id, then per-90 rates (outfield) and keeper ratios."""
    df = df.merge(fb, on=["tm_player_id", "league", "season"], how="left")
    for c in FBREF_COUNTS:
        df[f"{c}_p90"] = df[c] / df.fb_minutes * 90
    df["save_pct"] = df.saves / df.shots_on_target_against.where(df.shots_on_target_against > 0)
    df["gk_sota_p90"] = df.shots_on_target_against / df.gk_minutes * 90
    df["gk_ga_p90"] = df.goals_against / df.gk_minutes * 90
    return df


def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["linked"] = df.tm_player_id.notna().astype(int)
    birth = pd.to_datetime(df.birth_date)
    mid_season = pd.to_datetime((df.season + 1).astype(str) + "-01-01")
    df["age"] = (mid_season - birth).dt.days / 365.25
    df["position_group"] = [position_group(a, b) for a, b in zip(df.tm_position, df.understat_position)]
    for c in COUNTS:
        df[f"{c}_p90"] = df[c] / df.minutes * 90
    return df


def add_league_adjustment(df: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(factors[["league", "factor"]].rename(columns={"factor": "league_factor"}), on="league", how="left")
    for c in ADJUSTED:
        df[f"{c}_p90_adj"] = df[f"{c}_p90"] / df.league_factor
    return df


def add_career_context(df: pd.DataFrame) -> pd.DataFrame:
    """Pathway context from the player's own history in the data.

    log_league_factor  strength of the league played in (log of the mover-estimated factor)
    league_jump        log_league_factor now minus that of the previous season (0 if none within 2
                       seasons). Positive = moved to an easier league, negative = a harder one.
    A player in two leagues in one season is represented by the league with most minutes.
    Only the five Understat leagues are covered, so moves to or from other leagues are invisible
    (history starts in 2014: a 2014 row never has a previous season).
    """
    df = df.copy()
    df["log_league_factor"] = np.log(df.league_factor)
    main = (df.sort_values("minutes").groupby(["player_id", "season"], as_index=False).tail(1)
            [["player_id", "season", "log_league_factor"]])
    prev = df[["player_id", "season"]].assign(_i=df.index)
    prev_lf = pd.Series(np.nan, index=df.index)
    for lag in (2, 1):  # lag 1 written last so it wins when both exist
        m = main.assign(season=main.season + lag).rename(columns={"log_league_factor": "_prev"})
        got = prev.merge(m, on=["player_id", "season"], how="inner").drop_duplicates("_i").set_index("_i")["_prev"]
        prev_lf.loc[got.index] = got
    df["league_jump"] = (df.log_league_factor - prev_lf).fillna(0.0)
    return df


def add_percentiles(df: pd.DataFrame, min_minutes: int) -> pd.DataFrame:
    df = df.copy()
    eligible = df.minutes >= min_minutes
    for c in PERCENTILED:
        df[f"{c}_pct_league"] = np.nan
        df[f"{c}_pct_global"] = np.nan
        e = df[eligible & df.position_group.notna()]
        df.loc[e.index, f"{c}_pct_league"] = e.groupby(["league", "season", "position_group"])[f"{c}_p90"].rank(pct=True) * 100
        df.loc[e.index, f"{c}_pct_global"] = e.groupby(["season", "position_group"])[f"{c}_p90_adj"].rank(pct=True) * 100
    return df


def add_group_percentiles(df: pd.DataFrame, cols: list[str], min_minutes: int, position_filter) -> pd.DataFrame:
    """Percentile within (league, season, position group) among eligible players for `position_filter` rows."""
    df = df.copy()
    eligible = (df.minutes >= min_minutes) & df.position_group.notna() & position_filter(df)
    for c in cols:
        name = c[:-4] if c.endswith("_p90") else c
        df[f"{name}_pct_league"] = np.nan
        e = df[eligible & df[c].notna()]
        df.loc[e.index, f"{name}_pct_league"] = e.groupby(["league", "season", "position_group"])[c].rank(pct=True) * 100
    return df


def build(conn: sqlite3.Connection, min_minutes: int = 450, n_boot: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = add_base_features(load(conn))
    obs = league_strength.mover_observations(df)
    factors = league_strength.estimate(obs, n_boot=n_boot)
    df = add_career_context(add_league_adjustment(df, factors))
    df = add_percentiles(df, min_minutes)
    if conn.execute("SELECT 1 FROM fbref_tm_links LIMIT 1").fetchone():
        df = add_fbref_features(df, load_fbref(conn))
        df = add_group_percentiles(df, FBREF_PERCENTILED, min_minutes, lambda d: d.position_group != "GK")
        df = add_group_percentiles(df, GK_PERCENTILED, min_minutes, lambda d: d.position_group == "GK")
    return df, factors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-minutes", type=int, default=450, help="minimum minutes to be ranked in percentiles")
    ap.add_argument("--boot", type=int, default=300, help="bootstrap replicates for league-strength intervals")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    df, factors = build(conn, args.min_minutes, args.boot)
    df.to_sql("player_season_features", conn, if_exists="replace", index=False)
    factors.to_sql("league_strength", conn, if_exists="replace", index=False)
    print(factors.round(3).to_string(index=False))
    print(f"\nplayer_season_features: {len(df)} rows; age known for {df.age.notna().mean():.1%}; "
          f"position group known for {df.position_group.notna().mean():.1%}; "
          f"ranked in percentiles: {(df.minutes >= args.min_minutes).sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
