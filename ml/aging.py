"""Aging curves: how output changes with age, by position, and whether that helps predict next season.

Curve. For a player-season, y = log(output / mean output of that position in that season), where
output is a league-adjusted rate. Dividing by the same-season position mean removes league-wide drift
(age, season and a player's birth year are collinear once you hold the player fixed, so a period
trend would otherwise leak into the age effect). Then

    y[p, t] = player_p + f(age[p, t]) + noise

is estimated with a within-player (fixed-effects) regression on age dummies, so f is identified
from how the *same* players change as they age, not from comparing different cohorts. f is
reported relative to age 25: exp(f) = output as a multiple of what the player would produce at 25.
Intervals are a cluster bootstrap over players.

Known bias, stated not hidden: only players who keep getting 900+ minutes appear at each age, so
decliners drop out and curves at older ages are optimistic (survivorship).

Forecast test. Given y_t, predict y_{t+1} with
    persistence        y_t
    shrunk persistence  mu + lam * (y_t - mu)             (regression to the position mean)
    curve + shrinkage   f(a+1) + mu_s + lam * (y_t - f(a) - mu_s)
all fitted only on seasons already finished at the origin. See evaluate().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AGE_MIN, AGE_MAX, REF_AGE = 18, 35, 25
GROUPS = ["FWD", "WING_AM", "MID", "DEF"]
METRICS = {
    "attack": lambda d: d.npxg_p90_adj + d.xa_p90_adj,         # league-adjusted npxG + xA per 90
    "defence": lambda d: d.tackles_won_p90 + d.interceptions_p90,  # FBref, from 2016, not league-adjusted
}


def panel(df: pd.DataFrame, metric: str = "attack", min_minutes: int = 900) -> pd.DataFrame:
    """One row per player-season: relative log output y and integer age (clipped to [18, 35])."""
    d = df[(df.minutes >= min_minutes) & df.age.notna() & df.position_group.isin(GROUPS)].copy()
    d["output"] = METRICS[metric](d)
    d = d[d.output > 0]
    d = d.sort_values("minutes").groupby(["player_id", "season"], as_index=False).tail(1)  # main league
    d["age_i"] = d.age.round().clip(AGE_MIN, AGE_MAX).astype(int)
    d["y"] = np.log(d.output / d.groupby(["position_group", "season"]).output.transform("mean"))
    return d[["player_id", "season", "position_group", "age_i", "minutes", "y"]].reset_index(drop=True)


def _design(age_i: np.ndarray) -> np.ndarray:
    ages = [a for a in range(AGE_MIN, AGE_MAX + 1) if a != REF_AGE]
    return (age_i[:, None] == np.array(ages)[None, :]).astype(float)


def _fit(y: np.ndarray, age_i: np.ndarray, pid: np.ndarray) -> np.ndarray:
    """Within-player OLS; returns f(age) for AGE_MIN..AGE_MAX relative to REF_AGE."""
    x = _design(age_i)
    _, inv = np.unique(pid, return_inverse=True)
    n = np.bincount(inv).astype(float)
    y = y - (np.bincount(inv, weights=y) / n)[inv]
    x = x - np.column_stack([np.bincount(inv, weights=x[:, j]) / n for j in range(x.shape[1])])[inv]
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    ages = list(range(AGE_MIN, AGE_MAX + 1))
    out = np.zeros(len(ages))
    out[[i for i, a in enumerate(ages) if a != REF_AGE]] = beta
    return out


def fit_curve(p: pd.DataFrame, n_boot: int = 200, seed: int = 0) -> pd.DataFrame:
    """f(age) relative to age 25 with a 95% cluster-bootstrap interval, for one position group's panel."""
    p = p.groupby("player_id").filter(lambda g: len(g) >= 2)  # players seen once carry no within-player information
    ages = np.arange(AGE_MIN, AGE_MAX + 1)
    point = _fit(p.y.to_numpy(), p.age_i.to_numpy(), p.player_id.to_numpy())
    groups = {pid: g for pid, g in p.groupby("player_id")}
    ids = np.array(list(groups))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        s = rng.choice(ids, len(ids))
        b = pd.concat([groups[i].assign(player_id=k) for k, i in enumerate(s)])
        draws.append(_fit(b.y.to_numpy(), b.age_i.to_numpy(), b.player_id.to_numpy()))
    draws = np.array(draws) if draws else np.full((1, len(ages)), np.nan)  # n_boot=0: point estimate only
    n_obs = p.groupby("age_i").size().reindex(ages, fill_value=0).to_numpy()
    return pd.DataFrame({"age": ages, "effect": point, "lo": np.percentile(draws, 2.5, axis=0),
                         "hi": np.percentile(draws, 97.5, axis=0), "n_obs": n_obs,
                         "multiple_of_25": np.exp(point)})


def peak_age(curve: pd.DataFrame, min_obs: int = 30) -> int:
    ok = curve[curve.n_obs >= min_obs]
    return int(ok.loc[ok.effect.idxmax(), "age"])


def plateau(curve: pd.DataFrame, tol: float = 0.03, min_obs: int = 30) -> tuple[int, int] | None:
    """Contiguous ages around the peak whose (3-year smoothed) output is within `tol` of the maximum.

    Curves are flat near the top and noisy, so "peak at 24" overstates what the data can say; a range is
    honest. Smoothing matters because age 25 is the regression's reference point (exactly 0, no noise)
    and its noisy neighbours would otherwise split a plateau in two."""
    ok = curve[curve.n_obs >= min_obs].sort_values("age").reset_index(drop=True)
    if ok.empty:  # no age has enough observations (a sparse position): there is nothing honest to report
        return None
    eff = ok.effect.rolling(3, center=True, min_periods=2).mean()
    near = set(int(a) for a in ok.age[eff >= eff.max() + np.log(1 - tol)])
    peak = int(ok.age[eff.idxmax()])
    lo = hi = peak
    while lo - 1 in near:
        lo -= 1
    while hi + 1 in near:
        hi += 1
    return lo, hi


# ---------------------------------------------------------------- forecast test
BANDS = {"<=22": lambda a: a <= 22, "23-29": lambda a: (a >= 23) & (a <= 29), ">=30": lambda a: a >= 30}


def _pairs(p: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """Pairs of a player's seasons `lag` years apart: y0, age0 now; y1, age1 later."""
    a = p.rename(columns={"y": "y0", "age_i": "a0"})
    b = p[["player_id", "season", "y", "age_i"]].rename(columns={"y": "y1", "age_i": "a1"}).assign(season=lambda d: d.season - lag)
    return a.merge(b, on=["player_id", "season"])


def evaluate(p: pd.DataFrame, origins=range(2018, 2023), lag: int = 1) -> pd.DataFrame:
    """Rolling-origin test of predicting `lag` seasons ahead (per position group and age band).

    At origin t everything is fitted on pairs whose later season is <= t, then used to predict
    t -> t+lag for players with 900+ minutes in both seasons. One row per (group, origin, band, model).
    Players who stop getting 900+ minutes have no outcome, so this scores the survivors."""
    pairs = _pairs(p, lag)
    rows = []
    for g in GROUPS:
        pg, prs = p[p.position_group == g], pairs[pairs.position_group == g]
        for t in origins:
            if t + lag > pg.season.max():
                continue
            train, test = prs[prs.season + lag <= t], prs[prs.season == t]
            if len(train) < 200 or len(test) < 20:
                continue
            curve = fit_curve(pg[pg.season <= t], n_boot=0)
            f = dict(zip(curve.age, curve.effect))
            mu = train.y1.mean()
            # shrinkage weight: slope of later skill on current skill, fitted on the training pairs
            s0, s1 = train.y0 - train.a0.map(f), train.y1 - train.a1.map(f)
            lam = float(np.cov(s0, s1)[0, 1] / np.var(s0))
            lam_nc = float(np.cov(train.y0, train.y1)[0, 1] / np.var(train.y0))
            skill_mu = s1.mean()
            preds = {
                "persistence": test.y0,
                "shrunk persistence": mu + lam_nc * (test.y0 - mu),
                "curve + shrinkage": test.a1.map(f) + skill_mu + lam * (test.y0 - test.a0.map(f) - skill_mu),
            }
            for band, in_band in BANDS.items():
                m = in_band(test.a0).to_numpy()
                if m.sum() < 15:
                    continue
                for name, yhat in preds.items():
                    err = (test.y1 - yhat).to_numpy()[m]
                    rows.append({"group": g, "origin": t, "band": band, "model": name, "n": int(m.sum()),
                                 "abs_err_sum": float(np.abs(err).sum()), "sq_err_sum": float((err ** 2).sum())})
    r = pd.DataFrame(rows)
    return r.assign(mae=r.abs_err_sum / r.n, rmse=np.sqrt(r.sq_err_sum / r.n)) if len(r) else r


def summarise(ev: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Pooled MAE / RMSE per model (and `by` columns), weighting every target equally."""
    g = ev.groupby(by + ["model"]).agg(n=("n", "sum"), a=("abs_err_sum", "sum"), s=("sq_err_sum", "sum")).reset_index()
    return g.assign(MAE=g.a / g.n, RMSE=np.sqrt(g.s / g.n)).drop(columns=["a", "s"])
