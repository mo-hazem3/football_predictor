"""CLI: python -m ml.backtest [--horizon 3] [--origins 2018 2022] [--k 30] [--max-age 23]

Rolling-origin backtest of the trajectory projection. For each origin season t:

  1. Rebuild the features from data up to t only (league-strength factors included).
  2. Targets: players aged <= max-age with 900+ minutes in season t.
  3. Predict each target's next-`horizon`-season outcome from comps whose whole outcome window
     was already finished by t (asserted in ml.trajectory.project).
  4. Score against what actually happened (outcomes built from the full data, which is the
     only place the future is used, and only as the answer key).

Compared against:
  B0  base rate of everyone with the same position and similar age (no comps at all)
  B1  "same level": the k players of that position/age closest on the single current number
      (composite percentile, or current market value for the value outcome), same shrinkage
      and k as the comps model. The honest test of whether multi-dimensional similarity pays.
  learned  regularised logistic regression (tiers) / gradient-boosted quantiles (value) on a
      few summary features (ml.learned), trained only on outcomes known at the as-of date

Protocol: the comps configuration (k=30, prior 10, block weights) was fixed before any result
was seen. Everything added afterwards (the learned models and their hyper-parameters) was
developed on the origins 2018-2020 only; 2021-2022 are reported separately as the holdout.

Scoring: Brier score and log loss for outcome-tier probabilities; pinball loss and interval
coverage for market-value ranges. Differences carry a bootstrap interval resampled by player.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from data_pipeline import db
from features.build import build
from ml.learned import TierModel, ValueModel, add_trend, apply_elite_calibration, fit_elite_calibration
from ml.outcomes import COMPOSITES, add_composite, build_outcomes, value_series
from ml.similarity import SimilarityEngine
from ml.trajectory import age_peer_rows, class_rates, posterior, project

QS = (0.1, 0.5, 0.9)


# ---------------------------------------------------------------- predictions
def _nearest(peers: pd.DataFrame, key: np.ndarray, k: int) -> pd.DataFrame:
    """k distinct players closest on a 1-D key (each player's closest season)."""
    p = peers.assign(_d=key).sort_values("_d")
    return p.drop_duplicates("player_id").head(k)


def _ratio_quantiles(ratios: pd.Series) -> np.ndarray | None:
    r = ratios.dropna()
    return np.log(np.quantile(r, QS)) if len(r) >= 5 else None


def predict_origin(conn, full_out: pd.DataFrame, squads: pd.DataFrame, t: int, horizon: int, k: int, max_age: float,
                   prior_strength: float, tier_c: float = 0.03) -> tuple[list[dict], dict]:
    df_t, _ = build(conn, n_boot=0, max_season=t)
    out_t = add_trend(build_outcomes(add_composite(df_t), value_series(squads[squads.season <= t]), horizon, last_season=t))
    eng = SimilarityEngine(out_t)
    truth = full_out.set_index(["player_id", "season", "league"])
    cutoff = t - horizon

    targets = out_t[(out_t.season == t) & (out_t.age <= max_age) & (out_t.minutes >= 900) & out_t.position_group.notna()]
    # learned models see only rows whose outcome window had finished by t
    known = out_t[out_t.observable & (out_t.minutes >= 900)]
    tier_model = TierModel(c=tier_c).fit(known[known.tier.notna()])
    # ablations: what is the learned model's gain actually made of?
    ablations = {"nv": TierModel(c=tier_c, drop=("value",)).fit(known[known.tier.notna()]),                # no market value
                 "lv": TierModel(c=tier_c, drop=("value", "league", "minutes", "trend")).fit(known[known.tier.notna()])}  # level + age + position only
    abl_p = {k: dict(zip(targets.index, m.predict(targets))) for k, m in ablations.items()}
    value_model = ValueModel().fit(known)
    learned_p = dict(zip(targets.index, tier_model.predict(targets)))
    learned_q = dict(zip(targets.index, value_model.predict(targets)))

    recs, skipped = [], {"no_truth": 0, "no_features": 0}
    for r in targets.itertuples():
        key = (r.player_id, r.season, r.league)
        if key not in truth.index or not truth.loc[key, "observable"] or pd.isna(truth.loc[key, "tier"]):
            skipped["no_truth"] += 1
            continue
        tr = truth.loc[key]
        try:
            proj = project(eng, out_t, r.player_id, t, horizon, k=k, as_of=t, prior_strength=prior_strength)
        except (KeyError, ValueError):
            skipped["no_features"] += 1
            continue
        classes = proj.classes
        peers = age_peer_rows(out_t, r.position_group, r.age, cutoff, eng.age_window)

        # B1 for tiers: closest on current composite percentile (same shrinkage as the comps model)
        b1_probs = proj.base_rate
        if r.position_group in ("FWD", "WING_AM", "MID") and pd.notna(r.composite):
            pc = peers[peers.composite.notna()]
            near = _nearest(pc, (pc.composite - r.composite).abs().to_numpy(), k)
            b1_probs = posterior(near.tier.value_counts().reindex(classes, fill_value=0).to_numpy(float),
                                 proj.base_rate, prior_strength)[0]

        # value ranges: comps vs base rate vs same-current-value
        model_q = _ratio_quantiles(proj.comps.value_ratio)
        b0_q = _ratio_quantiles(peers.value_ratio)
        pv = peers[peers.value_ratio.notna() & (peers.value_now > 0)]
        b1_q = None
        if pd.notna(r.value_now) and r.value_now > 0 and len(pv):
            near = _nearest(pv, (np.log(pv.value_now) - np.log(r.value_now)).abs().to_numpy(), k)
            b1_q = _ratio_quantiles(near.value_ratio)

        recs.append({
            "origin": t, "player_id": r.player_id, "name": r.player_name, "group": r.position_group, "age": r.age,
            "classes": classes, "truth": tr.tier, "n_comps": proj.n_comps,
            "p_model": proj.probs, "p_b0": proj.base_rate, "p_b1": b1_probs,
            # learned tier model covers the positions with a performance tier; elsewhere it falls back to the base rate
            "p_learned": learned_p[r.Index] if r.position_group in COMPOSITES else proj.base_rate,
            "p_learned_nv": abl_p["nv"][r.Index] if r.position_group in COMPOSITES else proj.base_rate,
            "p_learned_lv": abl_p["lv"][r.Index] if r.position_group in COMPOSITES else proj.base_rate,
            "q_learned": learned_q[r.Index] if (pd.notna(r.value_now) and r.value_now > 0) else None,
            "truth_log_ratio": np.log(tr.value_ratio) if pd.notna(tr.value_ratio) else np.nan,
            "q_model": model_q, "q_b0": b0_q, "q_b1": b1_q,
        })
    return recs, skipped


# ---------------------------------------------------------------- scoring
def _onehot(classes, truth):
    v = np.zeros(len(classes))
    v[classes.index(truth)] = 1.0
    return v


def tier_losses(recs: pd.DataFrame, model: str) -> pd.DataFrame:
    rows = []
    for r in recs.itertuples():
        p, y = np.clip(getattr(r, f"p_{model}"), 1e-6, 1), _onehot(r.classes, r.truth)
        rows.append({"brier": float(((p - y) ** 2).sum()), "logloss": float(-np.log(p[r.classes.index(r.truth)]))})
    return pd.DataFrame(rows, index=recs.index)


def pinball(y: float, q: np.ndarray) -> float:
    return float(np.mean([max(t * (y - qq), (t - 1) * (y - qq)) for t, qq in zip(QS, q)]))


def boot_diff(a: np.ndarray, b: np.ndarray, groups: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean of (a - b) with a 95% interval, resampling whole players."""
    d = a - b
    ids, inv = np.unique(groups, return_inverse=True)
    sums, cnt = np.bincount(inv, weights=d), np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        s = rng.integers(0, len(ids), len(ids))
        draws.append(sums[s].sum() / cnt[s].sum())
    return float(d.mean()), float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def calibration(p: np.ndarray, y: np.ndarray, bins: int = 4) -> pd.DataFrame:
    q = pd.qcut(p, bins, duplicates="drop")
    return pd.DataFrame({"p": p, "y": y, "bin": q}).groupby("bin", observed=True).agg(
        predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size")).reset_index(drop=True)


MODELS = [("b0", "B0 base rate"), ("b1", "B1 same level"), ("model", "comps"), ("learned", "learned"),
          ("learned_nv", "learned, no value"), ("learned_lv", "learned, level+age")]
COMPARE = [("model", "comps"), ("learned", "learned"), ("learned_nv", "learned, no value"), ("learned_lv", "learned, level+age")]
TIER_ORDER = ["out", "regular", "good", "elite"]


def _section(recs: pd.DataFrame, title: str, calib: bool = False) -> list[str]:
    L = [f"=== {title}: {len(recs)} targets, {recs.player_id.nunique()} players ==="]
    perf = recs[recs.group.isin(COMPOSITES)]

    L += ["", f"PERFORMANCE TIER (forwards, wingers/attacking mids, midfielders; n={len(perf)})",
          f"  realised mix: {perf.truth.value_counts(normalize=True).reindex(TIER_ORDER).round(3).to_dict()}"]
    ls = {m: tier_losses(perf, m) for m, _ in MODELS}
    for m, name in MODELS:
        L.append(f"  {name:<20} Brier {ls[m].brier.mean():.4f}   log loss {ls[m].logloss.mean():.4f}")
    for m, name in COMPARE:
        for o, oname in (("b0", "B0"), ("b1", "B1")):
            d = {k: boot_diff(ls[m][k].to_numpy(), ls[o][k].to_numpy(), perf.player_id.to_numpy()) for k in ("brier", "logloss")}
            L.append(f"  {name:<18} - {oname}: Brier {d['brier'][0]:+.4f} [{d['brier'][1]:+.4f}, {d['brier'][2]:+.4f}]   "
                     f"log loss {d['logloss'][0]:+.4f} [{d['logloss'][1]:+.4f}, {d['logloss'][2]:+.4f}]")
    if calib:
        for m, name in (("model", "comps"), ("learned", "learned")):
            pe = np.array([p[r.classes.index("elite")] for r, p in zip(perf.itertuples(), perf[f"p_{m}"])])
            L += [f"  P(elite) calibration, {name}:",
                  calibration(pe, (perf.truth == "elite").to_numpy().astype(float)).round(3).to_string(index=False)]

    po = {m: np.array([p[0] for p in recs[f"p_{m}"]]) for m, _ in MODELS}   # class 0 is 'out'
    yo = (recs.truth == "out").to_numpy().astype(float)
    L += ["", f"RETENTION: no 900+ minute top-5 season within the horizon (all positions; n={len(recs)}, realised {yo.mean():.3f})"]
    for m, name in MODELS:
        L.append(f"  {name:<20} Brier {np.mean((po[m] - yo) ** 2):.4f}")
    for m, name in COMPARE:
        for o, oname in (("b0", "B0"), ("b1", "B1")):
            d = boot_diff((po[m] - yo) ** 2, (po[o] - yo) ** 2, recs.player_id.to_numpy())
            L.append(f"  {name:<18} - {oname}: Brier {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]")

    ok = recs.truth_log_ratio.notna() & recs.q_model.notna() & recs.q_b0.notna() & recs.q_b1.notna() & recs.q_learned.notna()
    v = recs[ok]
    L += ["", f"MARKET VALUE: peak value in horizon / value now, given a top-5 squad place (n={len(v)})"]
    y = v.truth_log_ratio.to_numpy()
    mods = [("b0", "B0 base rate"), ("b1", "B1 same value"), ("model", "comps"), ("learned", "learned")]
    pl = {m: np.array([pinball(yy, q) for yy, q in zip(y, v[f"q_{m}"])]) for m, _ in mods}
    for m, name in mods:
        cov = np.mean([(q[0] <= yy <= q[2]) for yy, q in zip(y, v[f"q_{m}"])])
        L.append(f"  {name:<14} pinball {pl[m].mean():.4f}   80% interval coverage {cov:.3f}")
    for m, name in (("model", "comps"), ("learned", "learned")):
        for o, oname in (("b0", "B0"), ("b1", "B1")):
            d = boot_diff(pl[m], pl[o], v.player_id.to_numpy())
            L.append(f"  {name:<8} - {oname}: pinball {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]")
    return L


def report(recs: pd.DataFrame, horizon: int) -> str:
    recs = recs.copy()
    recs["origin"] = recs.origin.astype(int)
    origins = sorted(recs.origin.unique())
    L = [f"Backtest: horizon {horizon} seasons, origins {origins}. Differences are model minus baseline, "
         f"with 95% intervals resampled by player: negative = model better (lower loss).", ""]
    L += _section(recs, "ALL ORIGINS", calib=True)
    dev, hold = recs[recs.origin <= 2020], recs[recs.origin >= 2021]
    if len(dev) and len(hold):
        L += ["", ""] + _section(dev, "DEVELOPMENT ORIGINS (learned models tuned here)")
        L += ["", ""] + _section(hold, "HOLDOUT ORIGINS (not used for any tuning of the learned models)")

    perf = recs[recs.group.isin(COMPOSITES)]
    dev_p, hold_p = perf[perf.origin <= 2020], perf[perf.origin >= 2021]
    if len(dev_p) and len(hold_p):
        cal = fit_elite_calibration(np.array([p[3] for p in dev_p.p_learned]), (dev_p.truth == "elite").to_numpy())
        hp = np.vstack(hold_p.p_learned.to_list())
        ls0, ls1 = tier_losses(hold_p, "learned"), tier_losses(hold_p.assign(p_learned=list(apply_elite_calibration(hp, cal))), "learned")
        d = boot_diff(ls1.logloss.to_numpy(), ls0.logloss.to_numpy(), hold_p.player_id.to_numpy())
        L += ["", "", "ELITE-PROBABILITY RECALIBRATION: Platt map fitted on development origins only, applied to the holdout",
              f"  holdout Brier {ls0.brier.mean():.4f} -> {ls1.brier.mean():.4f}   log loss {ls0.logloss.mean():.4f} -> {ls1.logloss.mean():.4f}"
              f"   (log loss change {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}])"]
        pe0, pe1 = hp[:, 3], apply_elite_calibration(hp, cal)[:, 3]
        ye = (hold_p.truth == "elite").to_numpy()
        for lo, hi in ((0, .05), (.05, .2), (.2, .5), (.5, 1.0)):
            m = (pe0 > lo) & (pe0 <= hi)
            L.append(f"  raw P(elite) in ({lo:.2f}, {hi:.2f}]  n={m.sum():3d}: raw mean {pe0[m].mean():.3f} -> recalibrated {pe1[m].mean():.3f}, observed {ye[m].mean():.3f}")
    L += ["", "", "BY ORIGIN (performance Brier: B0 / B1 / comps / learned / learned no-value / learned level+age; n; mean comps used)"]
    for t, g in perf.groupby("origin"):
        a = {m: tier_losses(g, m).brier.mean() for m, _ in MODELS}
        L.append(f"  {t}: {a['b0']:.4f} / {a['b1']:.4f} / {a['model']:.4f} / {a['learned']:.4f} / {a['learned_nv']:.4f} / {a['learned_lv']:.4f}   n={len(g)}  comps={g.n_comps.mean():.0f}")

    pe = pd.Series([p[r.classes.index("elite")] for r, p in zip(perf.itertuples(), perf.p_model)], index=perf.index)
    over = perf[perf.truth.isin(["out", "regular"])].assign(p_elite=pe).nlargest(5, "p_elite")
    under = perf[perf.truth == "elite"].assign(p_elite=pe).nsmallest(6, "p_elite")
    L += ["", "MOST CONFIDENT MISSES of the comps model", "  predicted elite, did not become one:"]
    L += [f"    {r.name} ({r.origin}, age {r.age:.1f}, {r.group}): P(elite)={r.p_elite:.2f}, became {r.truth}" for r in over.itertuples()]
    L.append("  became elite, comps gave little chance:")
    L += [f"    {r.name} ({r.origin}, age {r.age:.1f}, {r.group}): P(elite)={r.p_elite:.2f}" for r in under.itertuples()]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--origins", nargs=2, type=int, default=[2018, 2022], metavar=("FIRST", "LAST"))
    ap.add_argument("--k", type=int, default=30)
    ap.add_argument("--max-age", type=float, default=23.0)
    ap.add_argument("--prior-strength", type=float, default=10.0)
    ap.add_argument("--tier-c", type=float, default=0.03, help="inverse L2 strength of the learned tier model")
    ap.add_argument("--out", default=None, help="write the report to this file as well")
    ap.add_argument("--calibration-out", default=None,
                    help="write the P(elite) calibration map, fitted on ALL origins' out-of-time predictions, to this JSON file")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    full_df, _ = build(conn, n_boot=0)                      # answer key only
    full_out = build_outcomes(add_composite(full_df), value_series(squads), args.horizon, last_season=2025)

    recs, skipped = [], {}
    for t in range(args.origins[0], args.origins[1] + 1):
        r, s = predict_origin(conn, full_out, squads, t, args.horizon, args.k, args.max_age, args.prior_strength, args.tier_c)
        print(f"origin {t}: {len(r)} targets scored, skipped {s}", flush=True)
        recs += r
    all_recs = pd.DataFrame(recs)
    if args.calibration_out:
        import json
        from pathlib import Path
        perf = all_recs[all_recs.group.isin(COMPOSITES)]
        cal = fit_elite_calibration(np.array([p[3] for p in perf.p_learned]), (perf.truth == "elite").to_numpy())
        cal["fitted_on"] = {"origins": [int(o) for o in sorted(perf.origin.unique())], "horizon": args.horizon, "n": len(perf)}
        Path(args.calibration_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.calibration_out).write_text(json.dumps(cal, indent=1), encoding="utf-8")
    text = report(all_recs, args.horizon)
    print("\n" + text)
    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
