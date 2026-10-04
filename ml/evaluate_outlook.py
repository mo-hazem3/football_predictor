"""CLI: python -m ml.evaluate_outlook [--origins 2018 2022] [--out docs/outlook_backtest.txt]

Rolling-origin test of the fan chart (ml.outlook). At each origin season T the features are rebuilt from data
up to T (league-strength factors included), the models are fitted only on (player-season, later season) pairs
whose later season is <= T, and every reliable player-season at T is forecast 1, 2 and 3 seasons ahead. Truth
comes from the full data, and only where the player really has a 900+ minute season at t+h (the bands are
conditional on that; a separate check scores the probability that he does).

Scores: pinball loss averaged over the 10/50/90% quantiles (lower is better), coverage of the 10-90% band
(target 80%), and median absolute error. Intervals on differences are bootstrapped over players.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline import db
from features.build import build
from ml.backtest import boot_diff
from ml.learned import add_trend
from ml.outcomes import add_composite, build_outcomes, value_series
from ml.outlook import GROUPS, HORIZONS, QUANTILES, Outlook, build_pairs, pinball

MODELS = ["persistence", "shrinkage", "quantile GB"]


def run_origin(conn, squads: pd.DataFrame, full_pairs: pd.DataFrame, T: int, last_season: int) -> pd.DataFrame:
    df_t, _ = build(conn, n_boot=0, max_season=T)
    out_t = add_trend(build_outcomes(add_composite(df_t), value_series(squads[squads.season <= T]), 3, T))
    pairs_t = build_pairs(out_t, T)
    model = Outlook().fit(pairs_t)
    targets = pairs_t[pairs_t.season == T].reset_index(drop=True)
    preds = {"quantile GB": model.predict(targets), **model.predict_baselines(targets)}
    p_obs = model.predict_observed(targets)
    truth = full_pairs.set_index(["player_id", "season"]).reindex(pd.MultiIndex.from_arrays([targets.player_id, targets.season]))
    rows = []
    for j, h in enumerate(HORIZONS):
        if T + h > last_season:
            continue
        known = pairs_t[pairs_t[f"known{h}"]]
        base_rate = float(known[f"y{h}"].notna().mean())
        for i, r in targets.iterrows():
            y = truth[f"y{h}"].iloc[i]
            rec = {"origin": T, "h": h, "player_id": r.player_id, "age": r.age, "group": r.position_group, "level": r.composite,
                   "y": y, "observed": not np.isnan(y), "p_obs": p_obs[i, j], "base_rate": base_rate}
            for m in MODELS:
                rec[f"q_{m}"] = preds[m][i, j]
            rows.append(rec)
    return pd.DataFrame(rows)


def report(res: pd.DataFrame) -> str:
    L = [f"Outlook backtest: origins {sorted(res.origin.unique())}; level = composite percentile (0-100); "
         "bands are conditional on a 900+ minute top-5 season at t+h.", ""]
    obs = res[res.observed].copy()
    for m in MODELS:
        obs[f"pin_{m}"] = pinball(obs.y.to_numpy(), np.vstack(obs[f"q_{m}"].to_numpy()))
        q = np.vstack(obs[f"q_{m}"].to_numpy())
        obs[f"cov_{m}"] = ((obs.y.to_numpy() >= q[:, 0]) & (obs.y.to_numpy() <= q[:, 2])).astype(float)
        obs[f"mae_{m}"] = np.abs(obs.y.to_numpy() - q[:, 1])
    subsets = [("all ages", obs), ("age <= 23", obs[obs.age <= 23]), ("age 24-29", obs[(obs.age > 23) & (obs.age < 30)]), ("age >= 30", obs[obs.age >= 30])]
    for name, s in subsets:
        L += [f"=== {name}: {len(s)} forecasts, {s.player_id.nunique()} players ===",
              f"{'':<4}{'model':<14}{'pinball':>9}{'80% cover':>11}{'median MAE':>12}{'  vs shrinkage (95% CI)':>34}"]
        for h in HORIZONS:
            sh = s[s.h == h]
            if len(sh) < 20:
                continue
            ref = sh["pin_shrinkage"].to_numpy()
            for m in MODELS:
                d, lo, hi = boot_diff(sh[f"pin_{m}"].to_numpy(), ref, sh.player_id.to_numpy(), n=500)
                tag = f"h={h}" if m == MODELS[0] else ""
                L.append(f"{tag:<4}{m:<14}{sh[f'pin_{m}'].mean():9.3f}{sh[f'cov_{m}'].mean():11.2f}{sh[f'mae_{m}'].mean():12.2f}"
                         + (f"{d:+10.3f} [{lo:+.3f}, {hi:+.3f}]" if m != "shrinkage" else f"{'(reference)':>34}"))
        L.append("")

    L.append("=== still a 900+ minute top-5 player at t+h? (all ages) ===")
    for h in HORIZONS:
        s = res[res.h == h]
        brier = np.mean((s.p_obs - s.observed.astype(float)) ** 2)
        base = np.mean((s.base_rate - s.observed.astype(float)) ** 2)
        L.append(f"h={h}: realised {s.observed.mean():.2f}, predicted mean {s.p_obs.mean():.2f}; Brier {brier:.4f} vs base rate {base:.4f}")
    L += ["", "=== BY ORIGIN (h=2 pinball: persistence / shrinkage / quantile GB; n) ==="]
    for T, s in obs[obs.h == 2].groupby("origin"):
        L.append(f"  {T}: " + " / ".join(f"{s[f'pin_{m}'].mean():.3f}" for m in MODELS) + f"   n={len(s)}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origins", nargs=2, type=int, default=[2018, 2022], metavar=("FIRST", "LAST"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    full_df, _ = build(conn, n_boot=0)                           # answer key only
    last = int(full_df.season.max())
    full_out = add_trend(build_outcomes(add_composite(full_df), value_series(squads), 3, last))
    full_pairs = build_pairs(full_out, last)
    parts = []
    for T in range(args.origins[0], args.origins[1] + 1):
        parts.append(run_origin(conn, squads, full_pairs, T, last))
        print(f"origin {T}: {len(parts[-1])} forecasts", flush=True)
    text = report(pd.concat(parts, ignore_index=True))
    print("\n" + text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
