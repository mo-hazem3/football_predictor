"""CLI: python -m data_pipeline.ingest_statsbomb --list | --competition ID --season ID [--max-matches N]"""
from __future__ import annotations

import argparse

from data_pipeline import db
from data_pipeline.sources import statsbomb as sb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list available competition-seasons")
    ap.add_argument("--competition", type=int)
    ap.add_argument("--season", type=int)
    ap.add_argument("--max-matches", type=int, default=None)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    if args.list:
        for c in sorted(sb.competitions(), key=lambda c: (c["competition_name"], c["season_name"])):
            print(f'{c["competition_id"]:>4} {c["season_id"]:>4}  {c["competition_name"]} — {c["season_name"]}')
        return 0
    if args.competition is None or args.season is None:
        ap.error("--competition and --season are required (or use --list)")

    df = sb.player_season_stats(args.competition, args.season, args.max_matches)
    if df.empty:
        print("No rows produced.")
        return 1
    conn = db.connect(args.db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(player_season_stats)")]
    conn.executemany(
        f"INSERT OR REPLACE INTO player_season_stats ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        df[cols].where(df[cols].notna(), None).values.tolist(),
    )
    conn.commit()
    print(f"Stored {len(df)} player-season rows ({df['competition'].iat[0]} {df['season'].iat[0]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
