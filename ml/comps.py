"""CLI: python -m ml.comps "Lamine Yamal" --season 2024 [-k 10] [--no-context]

Prints the closest comparable player-seasons and the gap analysis against them.
"""
from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline import db
from ml.gap_analysis import gap_analysis
from ml.similarity import SimilarityEngine


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name")
    ap.add_argument("--season", type=int, help="season start year (default: the player's latest ranked season)")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--metric", default="euclidean", choices=["euclidean", "mahalanobis", "cosine"])
    ap.add_argument("--no-context", action="store_true", help="compare stats only (ignore league strength / league jump / soft age)")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    df = pd.read_sql("SELECT * FROM player_season_features", db.connect(args.db))
    eng = SimilarityEngine(df, metric=args.metric, use_context=not args.no_context)
    found = eng.find(args.name, args.season)
    if found.empty:
        print(f"No ranked player-season matches '{args.name}'.")
        return 1
    exact = found[found.player_name.str.casefold() == args.name.casefold()]
    if exact.player_id.nunique() == 1:  # 'Rodri' should not be ambiguous with 'Rodrigo ...'
        found = exact
    if found.player_id.nunique() > 1:
        print("Several players match; be more specific:\n" + found.drop_duplicates("player_id").to_string(index=False))
        return 1
    row = found.sort_values("season").iloc[-1]
    comps = eng.comps(int(row.player_id), int(row.season), k=args.k)
    target = eng.target_row(int(row.player_id), int(row.season))

    pd.set_option("display.width", 220)
    print(f"{row.player_name}, {row.season}/{str(row.season + 1)[-2:]} {row.league} {row.team} "
          f"({row.position_group}, age {row.age:.1f}, {int(row.minutes)} min)")
    print(f"features used: {', '.join(comps.attrs['features_used'])}\n")
    cols = ["player_name", "season", "league", "team", "age", "minutes", "distance"]
    print(comps[cols].round(2).to_string(index=False))
    gaps = gap_analysis(target, comps)
    if len(gaps):
        print("\nGap analysis vs these comps (percentile points; weakest first):")
        print(gaps[["label", "target_pct", "comp_median_pct", "gap", "flag"]].round(0).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
