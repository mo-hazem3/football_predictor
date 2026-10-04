"""CLI: python -m ml.team_report "Bayer Leverkusen" [--season 2025] [--n 5] [--max-age 29] [--max-value-m 40]

Team style profile -> gaps -> candidate shortlists. See ml.recruit for how far to trust each link (short
version: profiles and gaps are descriptive and stable, the player mapping is a labelled heuristic).
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from data_pipeline import db
from features import team_style as ts
from features.build import build
from ml import recruit
from ml.learned import add_trend
from ml.outcomes import add_composite, build_outcomes, value_series
from ml.value_lens import build_panel, crossfit_residual

NOISY = ts.NOISY_DIMENSIONS


def price_vs_output(out: pd.DataFrame, season: int) -> pd.Series:
    """player_id -> % by which his market value sits below (negative) or above (positive) what peers with the
    same output and age are valued at, for forwards / wingers / midfielders (cross-fitted)."""
    panel = build_panel(out)
    train, cross = panel[panel.season <= season], panel[panel.season == season]
    if cross.empty:
        return pd.Series(dtype=float)
    resid = crossfit_residual(train, cross)
    return pd.Series((np.exp(resid) - 1) * 100, index=cross.player_id.to_numpy())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("team")
    ap.add_argument("--season", type=int, help="start year; default: the team's latest season")
    ap.add_argument("--n", type=int, default=5, help="candidates per gap")
    ap.add_argument("--max-age", type=float, default=29.0)
    ap.add_argument("--max-value-m", type=float, help="budget ceiling in EUR millions (market value)")
    ap.add_argument("--threshold", type=float, default=25.0, help="percentile at or below which a dimension counts as a gap")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    prof = ts.add_percentiles(ts.build_profiles(pd.read_sql("SELECT * FROM team_matches", conn), pd.read_sql("SELECT * FROM team_style", conn)))
    hit = prof[prof.team.str.casefold() == args.team.casefold()]
    if hit.empty:
        hit = prof[prof.team.str.contains(args.team, case=False, regex=False)]
    if hit.empty:
        print(f"No team matching '{args.team}'. Examples: {', '.join(sorted(prof[prof.season == prof.season.max()].team)[:8])}")
        return 1
    if hit.team.nunique() > 1:
        print("Several teams match: " + ", ".join(sorted(hit.team.unique())))
        return 1
    row = (hit[hit.season == args.season] if args.season else hit.sort_values("season").tail(1))
    if row.empty:
        print(f"No data for {hit.team.iloc[0]} in {args.season}.")
        return 1
    row = row.iloc[0]
    team, season = row.team, int(row.season)

    print(f"{team} {season}/{str(season + 1)[-2:]} ({row.league}): {row.pts_pm:.2f} pts/match (xPts {row.xpts_pm:.2f}), xG {row.xg_pm:.2f} for / {row.xga_pm:.2f} against per match\n")
    print("Style dimensions (percentile among that league's teams that season; higher = better):")
    for d in ts.DIMENSIONS:
        flag = "  <- gap" if row[f"{d}_pct"] <= args.threshold else ""
        print(f"  {ts.LABELS[d]:<38} {row[f'{d}_pct']:5.0f}{flag}")
    gaps = ts.gaps(row, args.threshold)
    if gaps.empty:
        print("\nNo dimension at or below the gap threshold.")
        return 0

    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    features, _ = build(conn, n_boot=0)
    out = add_trend(build_outcomes(add_composite(features), value_series(squads), 3, 2025))
    cands = recruit.candidates(out, season, max_age=args.max_age + 2)
    # without a budget the list is just the best players in Europe: default to the club's own scale, the highest
    # market value in its squad that season (override with --max-value-m)
    squad_values = out[(out.season == season) & out.team.fillna("").str.contains(team, regex=False)].value_now
    ceiling = args.max_value_m * 1e6 if args.max_value_m else float(squad_values.max()) if squad_values.notna().any() else None
    if ceiling:
        note = " (the highest value in the squad; change with --max-value-m)" if not args.max_value_m else ""
        print(f"\nCandidate ceiling: market value <= EUR {ceiling / 1e6:.0f}m{note}")
    cands = cands.join(price_vs_output(out, season).rename("price_vs_output"), on="player_id")
    pd.set_option("display.width", 220)
    for g in gaps.itertuples():
        note = "  (noisy dimension: style persists weakly year to year)" if g.dimension in NOISY else ""
        print(f"\nGap: {g.label} ({g.percentile:.0f}th percentile){note}")
        if recruit.GAP_PROFILE.get(g.dimension) is None:
            print(f"  {recruit.NOTES[g.dimension]}")
            continue
        sl = recruit.shortlist(cands, g.dimension, team, n=args.n, max_value_eur=ceiling,
                               max_age=args.max_age)
        if sl.empty:
            print("  no candidate meets the strength bar within these filters")
            continue
        sl = sl.assign(value_m=sl.value_now / 1e6, fit=sl.fit.round(0))
        sl["price_vs_output"] = sl.price_vs_output.round(0)
        print(sl[["player_name", "team", "league", "position_group", "age", "fit", "value_m", "price_vs_output", "age_note"]].round(1).to_string(index=False))
    print("\nfit = mean percentile (within position) on the metrics that bear on the gap; price_vs_output = % below (-) / above (+) the "
          "value of peers with the same output and age. A ranking heuristic: it does not predict that a signing closes the gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
