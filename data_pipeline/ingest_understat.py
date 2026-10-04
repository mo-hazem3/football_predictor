"""CLI: python -m data_pipeline.ingest_understat --leagues EPL La_liga --seasons 2014 2025"""
from __future__ import annotations

import argparse

from data_pipeline import db
from data_pipeline.sources import understat as us


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+", default=us.LEAGUES)
    ap.add_argument("--seasons", nargs=2, type=int, default=[2014, 2025], metavar=("FIRST", "LAST"),
                    help="inclusive range of season start years")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(understat_player_seasons)")]
    total = 0
    for league in args.leagues:
        for season in range(args.seasons[0], args.seasons[1] + 1):
            try:
                df = us.to_frame(us.fetch_league_season(league, season), league, season)
            except Exception as exc:  # keep going; report at the end
                print(f"  skip {league} {season}: {exc}")
                continue
            conn.executemany(
                f"INSERT OR REPLACE INTO understat_player_seasons ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                df[cols].values.tolist(),
            )
            conn.commit()
            total += len(df)
            print(f"{league} {season}: {len(df)} rows")
    print(f"Stored {total} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
