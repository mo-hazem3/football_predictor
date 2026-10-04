"""CLI: python -m ml.project "Lamine Yamal" --season 2024 [--horizon 3] [-k 30]

Forecast what a player is likely to become over the next `horizon` seasons: outcome
probabilities with a range, a market-value range, and the comps that serve as evidence.
Only information available at the end of `--as-of` (default 2025) is used.
"""
from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline import db
from ml.forecast import Forecaster

TIER_TEXT = {"elite": "elite (top decile)", "good": "good (top quartile)", "regular": "regular top-5 player",
             "out": "out (no 900+ min top-5 season)", "retained": "still a top-5 regular"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name")
    ap.add_argument("--season", type=int)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--as-of", type=int, default=2025)
    ap.add_argument("-k", type=int, default=30)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    features = pd.read_sql("SELECT * FROM player_season_features", conn)
    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    fc = Forecaster(features, squads, horizon=args.horizon, as_of=args.as_of)

    found = fc.engine.find(args.name, args.season)
    exact = found[found.player_name.str.casefold() == args.name.casefold()]
    if exact.player_id.nunique() == 1:
        found = exact
    if found.empty or found.player_id.nunique() > 1:
        print("No unique ranked match for that name." if found.empty else
              "Several players match; be more specific:\n" + found.drop_duplicates("player_id").to_string(index=False))
        return 1
    row = found.sort_values("season").iloc[-1]
    f = fc.forecast(int(row.player_id), int(row.season), k=args.k)

    pd.set_option("display.width", 200)
    if f.season + f.horizon <= f.as_of:
        print(f"note: {f.name}'s {f.horizon}-season outcome is already known as of {f.as_of}, so this is not a true forecast; "
              f"pass --as-of {f.season} to see what could have been said at the time.\n")
    print(f"{f.name}, {f.season}/{str(f.season + 1)[-2:]} ({f.group}, age {f.age:.1f}) -> next {f.horizon} seasons, "
          f"using only information up to {f.as_of}\n")
    print(f"Outcome probabilities ({f.source}; range = 10-90% across bootstrap fits, model uncertainty only):")
    pct = lambda x: "  <1%" if x < 0.01 else f"{x:5.0%}" if x >= 0.1 else f"{x:5.1%}"
    for c, p, lo, hi, cs in zip(f.classes, f.probs, f.lo, f.hi, f.comps_view.probs):
        rng = f"  [{pct(lo)} - {pct(hi)}]" if f.source == "learned model" else ""
        print(f"  {TIER_TEXT.get(c, c):<34} {pct(p)}{rng}   (comps alone: {pct(cs)})")
    if f.value_range:
        v = f.value_range
        print(f"\nMarket value (now EUR {f.value_now / 1e6:.1f}m): peak within {f.horizon} seasons, if he stays on a top-5 squad: "
              f"EUR {v[0.1] / 1e6:.0f}m - {v[0.9] / 1e6:.0f}m (median {v[0.5] / 1e6:.0f}m)"
              + (f"; capped at EUR {f.value_ceiling / 1e6:.0f}m, the highest value in the data" if f.value_ceiling and v[0.9] >= f.value_ceiling else ""))

    c = f.comps_view.comps.sort_values("distance").head(10)
    print(f"\nEvidence: closest comps whose {f.horizon}-season outcome is already known ({f.comps_view.n_comps} used for the 'comps alone' column):")
    c = c.assign(became=c.tier, value_x=c.value_ratio.round(2))
    print(c[["player_name", "season", "league", "age", "distance", "became", "value_x"]].round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
