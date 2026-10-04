"""CLI: python -m data_pipeline.ingest_fbref --leagues EPL Bundesliga --seasons 2014 2025

Opens Chrome via soccerdata/seleniumbase; pages are cached by soccerdata in
~/soccerdata/, so interrupted runs resume cheaply.
"""
from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from data_pipeline import db
from data_pipeline.sources import fbref


def _save(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    df = df.astype(object).where(df.notna(), None)  # NaN -> NULL
    cols = list(df.columns)
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        df.values.tolist(),
    )
    conn.commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+", default=list(fbref.LEAGUES), choices=list(fbref.LEAGUES))
    ap.add_argument("--seasons", nargs=2, type=int, default=[2014, 2025], metavar=("FIRST", "LAST"),
                    help="inclusive range of season start years")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    for league in args.leagues:
        for season in range(args.seasons[0], args.seasons[1] + 1):
            try:
                outfield, keepers = fbref.fetch_league_season(league, season)
            except Exception as exc:  # keep going; one bad page should not end a long run
                print(f"  skip {league} {season}: {type(exc).__name__}: {str(exc)[:150]}", flush=True)
                continue
            _save(conn, "fbref_player_seasons", outfield)
            _save(conn, "fbref_keeper_seasons", keepers)
            print(f"{league} {season}: {len(outfield)} outfield, {len(keepers)} keepers", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
