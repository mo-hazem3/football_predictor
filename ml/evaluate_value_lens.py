"""CLI: python -m ml.evaluate_value_lens [--horizon 1] [--boot 500]

Does "underpriced for what he produces" predict later value growth?

For each origin season the pricing model is refit on data up to that season (cross-fitted by player), each
player gets a residual (log actual - log predicted value), and we compare the value change over the next
`horizon` seasons across residual groups, within each position and season (so league-wide inflation and
position differences cannot drive the result). Intervals are bootstrapped over players.

Reading guide. A value change is only observed while the player stays on a top-5 squad, so everything is
conditional on staying. Value also mean-reverts mechanically (cheap players have room to rise), so the
last block asks whether the residual adds anything once the starting value and age are controlled for.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from data_pipeline import db
from features.build import build
from ml.learned import add_trend
from ml.outcomes import add_composite, build_outcomes, value_series
from ml.value_lens import backtest, build_panel, complete_changes, history_index


def boot_mean_diff(a: np.ndarray, ga: np.ndarray, b: np.ndarray, gb: np.ndarray, n: int, seed: int = 0):
    """Mean(a) - mean(b) with a 95% interval, resampling whole players in each group."""
    rng = np.random.default_rng(seed)
    pa, pb = np.unique(ga), np.unique(gb)
    ia = {p: np.flatnonzero(ga == p) for p in pa}
    ib = {p: np.flatnonzero(gb == p) for p in pb}
    d = []
    for _ in range(n):
        sa = np.concatenate([ia[p] for p in rng.choice(pa, len(pa))])
        sb = np.concatenate([ib[p] for p in rng.choice(pb, len(pb))])
        d.append(a[sa].mean() - b[sb].mean())
    return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def ols_clustered(y: np.ndarray, x: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and player-clustered standard errors (CR0 sandwich)."""
    x1 = np.column_stack([np.ones(len(x)), x])
    xtx_inv = np.linalg.inv(x1.T @ x1)
    beta = xtx_inv @ x1.T @ y
    u = y - x1 @ beta
    meat = np.zeros((x1.shape[1], x1.shape[1]))
    for g in np.unique(groups):
        m = groups == g
        s = x1[m].T @ u[m]
        meat += np.outer(s, s)
    cov = xtx_inv @ meat @ xtx_inv
    return beta, np.sqrt(np.diag(cov))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    values = value_series(squads)
    features, _ = build(conn, n_boot=0)
    out = add_trend(build_outcomes(add_composite(features), values, 3, 2025))
    panel = build_panel(out)
    res = backtest(panel, values, horizon=args.horizon)
    print(f"{len(res)} player-seasons, {res.player_id.nunique()} players, origins {sorted(res.origin.unique())}, horizon {args.horizon}")

    # residual rank within position and season: 0 = most underpriced, 1 = most overpriced
    res["rank"] = res.groupby(["origin", "position_group"]).resid.rank(pct=True)
    res["group"] = pd.cut(res["rank"], [0, 0.1, 0.3, 0.7, 0.9, 1.0],
                          labels=["most underpriced 10%", "underpriced 10-30%", "fairly priced", "overpriced 70-90%", "most overpriced 10%"])
    # value change net of the position-season average, so we compare like with like
    res["delta_net"] = res.delta - res.groupby(["origin", "position_group"]).delta.transform("mean")
    t = res.groupby("group", observed=True).agg(n=("delta", "size"), mean_resid=("resid", "mean"), mean_change=("delta_net", "mean"),
                                                age=("age", "mean"), start_value_m=("value_now", lambda v: v.median() / 1e6))
    t["mean_change_pct"] = (np.exp(t.mean_change) - 1) * 100
    pd.set_option("display.width", 200)
    print(f"\nValue change over the next {args.horizon} season(s), net of the same position-season average:")
    print(t[["n", "mean_resid", "age", "start_value_m", "mean_change_pct"]].round(2).to_string())

    def top_vs_bottom(g):
        lo_, hi_ = g[g["rank"] <= 0.1], g[g["rank"] > 0.9]
        return boot_mean_diff(lo_.delta_net.to_numpy(), lo_.player_id.to_numpy(), hi_.delta_net.to_numpy(), hi_.player_id.to_numpy(), args.boot), len(lo_), len(hi_)

    (d, a, b), nl, nh = top_vs_bottom(res)
    print(f"\nMost underpriced 10% minus most overpriced 10%: {d:+.3f} log points ({(np.exp(d) - 1) * 100:+.0f}%), 95% interval [{a:+.3f}, {b:+.3f}]  (n={nl}/{nh})")
    for pos, g in res.groupby("position_group"):
        (d, a, b), nl, nh = top_vs_bottom(g)
        print(f"  {pos:<8} n={nl}/{nh}  {d:+.3f}  [{a:+.3f}, {b:+.3f}]")
    for name, g in (("origins 2016-2019", res[res.origin <= 2019]), ("origins 2020-2023", res[res.origin >= 2020])):
        (d, a, b), nl, nh = top_vs_bottom(g)
        print(f"  {name}: {d:+.3f}  [{a:+.3f}, {b:+.3f}]")

    # selection check: the change is only seen for players who stay on a top-5 squad
    allr = backtest(panel, values, horizon=args.horizon, keep_missing=True)
    allr["rank"] = allr.groupby(["origin", "position_group"]).resid.rank(pct=True)
    allr["seen"] = allr.delta.notna()
    seen_lo, seen_hi = allr[allr["rank"] <= 0.1].seen.mean(), allr[allr["rank"] > 0.9].seen.mean()
    print(f"\nSelection check: still on a top-5 squad {args.horizon} season(s) later: most underpriced {seen_lo:.0%}, most overpriced {seen_hi:.0%}, all {allr.seen.mean():.0%}")
    for penalty in (-0.3, -0.7):  # a leaver's value is assumed to have fallen by this many log points (-0.7 = value halves)
        z = allr.assign(delta=allr.delta.fillna(allr.groupby(["origin", "position_group"]).delta.transform("mean") + penalty))
        z["delta_net"] = z.delta - z.groupby(["origin", "position_group"]).delta.transform("mean")
        l_, h_ = z[z["rank"] <= 0.1], z[z["rank"] > 0.9]
        d, a, b = boot_mean_diff(l_.delta_net.to_numpy(), l_.player_id.to_numpy(), h_.delta_net.to_numpy(), h_.player_id.to_numpy(), args.boot)
        print(f"  leavers assigned {penalty:+.1f}: most underpriced minus most overpriced {d:+.3f}  [{a:+.3f}, {b:+.3f}]")

    # fill leavers' value changes from their full Transfermarkt history (it tracks players after they leave)
    history = pd.read_sql("SELECT tm_player_id, date, value_eur FROM transfermarkt_market_values", conn)
    full = complete_changes(allr, history_index(history), args.horizon)
    lv = full[full.leaver]
    covered = lv.delta_full.notna()
    print(f"\nLeavers with value history: {covered.mean():.0%} of {len(lv)}; their mean value change {lv.delta_full[covered].mean():+.2f} log points "
          f"(median {lv.delta_full[covered].median():+.2f}); stayers {full[~full.leaver].delta.mean():+.2f}")
    for name, g in (("most underpriced", full[full["rank"] <= 0.1]), ("most overpriced", full[full["rank"] > 0.9])):
        lg = g[g.leaver]
        print(f"  {name}: leavers {len(lg)/len(g):.0%} of group, covered {lg.delta_full.notna().mean():.0%}, leavers' mean change {lg.delta_full.mean():+.2f}, stayers' {g[~g.leaver].delta.mean():+.2f}")
    pos_origin = ["origin", "position_group"]
    seen_full = full[full.delta_full.notna()].copy()
    seen_full["delta_net"] = seen_full.delta_full - seen_full.groupby(pos_origin).delta_full.transform("mean")
    l_, h_ = seen_full[seen_full["rank"] <= 0.1], seen_full[seen_full["rank"] > 0.9]
    d, a, b = boot_mean_diff(l_.delta_net.to_numpy(), l_.player_id.to_numpy(), h_.delta_net.to_numpy(), h_.player_id.to_numpy(), args.boot)
    print(f"  CORRECTED (stayers + leavers with history, n={len(l_)}/{len(h_)}): most underpriced minus most overpriced {d:+.3f} [{a:+.3f}, {b:+.3f}]  ({(np.exp(d) - 1) * 100:+.0f}%)")
    def corrected(g):
        a_, b_ = g[g["rank"] <= 0.1], g[g["rank"] > 0.9]
        return boot_mean_diff(a_.delta_net.to_numpy(), a_.player_id.to_numpy(), b_.delta_net.to_numpy(), b_.player_id.to_numpy(), args.boot)

    for pos, g in seen_full.groupby("position_group"):
        d, a, b = corrected(g)
        print(f"    corrected, {pos:<8} {d:+.3f} [{a:+.3f}, {b:+.3f}]")
    for name, g in (("origins 2016-2019", seen_full[seen_full.origin <= 2019]), ("origins 2020-2023", seen_full[seen_full.origin >= 2020])):
        d, a, b = corrected(g)
        print(f"    corrected, {name}: {d:+.3f} [{a:+.3f}, {b:+.3f}]")
    for penalty in (-0.3, -0.7):  # leavers WITHOUT history are still unknown: bound them
        z = full.assign(delta_full=full.delta_full.fillna(full.groupby(pos_origin).delta_full.transform("mean") + penalty))
        z["delta_net"] = z.delta_full - z.groupby(pos_origin).delta_full.transform("mean")
        l_, h_ = z[z["rank"] <= 0.1], z[z["rank"] > 0.9]
        d, a, b = boot_mean_diff(l_.delta_net.to_numpy(), l_.player_id.to_numpy(), h_.delta_net.to_numpy(), h_.player_id.to_numpy(), args.boot)
        print(f"    leavers still without history assigned {penalty:+.1f}: {d:+.3f} [{a:+.3f}, {b:+.3f}]")

    # does the residual add anything once starting value and age are controlled for?
    x = np.column_stack([res.resid, res.log_value, res.age, res.age ** 2])
    beta, se = ols_clustered(res.delta_net.to_numpy(), x, res.player_id.to_numpy())
    print("\nOLS of net value change on residual, starting value and age (player-clustered SEs):")
    for n_, b_, s_ in zip(["const", "residual", "log value", "age", "age^2"], beta, se):
        print(f"  {n_:<10} {b_:+.4f}  (se {s_:.4f}, t = {b_ / s_:+.1f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
