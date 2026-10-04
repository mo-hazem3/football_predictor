"""League-strength factors estimated from players who changed league.

Idea: a player's underlying ability changes little over a season or two, so
when the same player's output drops (rises) after moving from league A to B,
that tells us B is harder (easier). Pooling all such movers gives one factor
per league.

Model (outcome = log of attacking output per 90, npxG + xA):

    log y[p, t] = player_p + league_l(p,t) + b1*age + b2*age^2 + noise

Player effects are removed by demeaning within player, so only players seen in
different leagues in consecutive seasons (or the same season) contribute. The
5 league effects are centred to mean zero and exponentiated: a factor of 1.10
means "attacking output per 90 is typically 10% higher here than the average
of these leagues, for the same player". Uncertainty comes from a cluster
bootstrap over players.

Known limitations (documented, not hidden):
  * Selection bias: players who move are not random. Regression to the mean
    after a standout season in the origin league makes the destination look
    harder than it is. Same-season movers are less exposed to ageing but
    there are few of them.
  * Only the five Understat leagues are covered; lower leagues need another source.
  * The factor is estimated on npxG+xA and applied to all volume-type
    attacking rates as an assumption.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def mover_observations(df: pd.DataFrame, min_minutes: int = 600) -> pd.DataFrame:
    """Rows usable for estimation.

    Expects columns: player_id, league, season, minutes, age, position_group, npxg_p90, xa_p90.
    Keeps outfield players with reliable minutes and a known age whose league
    differs from that of another observation at most one season away.
    """
    d = df[(df.minutes >= min_minutes) & df.age.notna() & (df.position_group != "GK")].copy()
    d["output"] = d.npxg_p90 + d.xa_p90
    d = d[d.output > 0]
    usable = []
    for _, g in d.groupby("player_id"):
        if g.league.nunique() < 2:
            continue
        for i, r in g.iterrows():
            near_other = g[(g.league != r.league) & ((g.season - r.season).abs() <= 1)]
            if len(near_other):
                usable.append(i)
    d = d.loc[usable]
    # a player must still span >=2 leagues after filtering
    return d.groupby("player_id").filter(lambda g: g.league.nunique() >= 2)


def _fit(obs: pd.DataFrame, leagues: list[str]) -> np.ndarray:
    """Within-player OLS; returns league effects centred to mean zero."""
    y = np.log(obs.output.to_numpy())
    age = (obs.age.to_numpy() - 25.0)
    X = np.column_stack(
        [(obs.league.to_numpy() == lg).astype(float) for lg in leagues[1:]] + [age, age ** 2]
    )
    pid = obs.player_id.to_numpy()
    codes, inv = np.unique(pid, return_inverse=True)
    counts = np.bincount(inv)
    y = y - (np.bincount(inv, weights=y) / counts)[inv]
    X = X - np.array([np.bincount(inv, weights=X[:, j]) / counts for j in range(X.shape[1])]).T[inv]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    eff = np.concatenate([[0.0], beta[: len(leagues) - 1]])  # first league is the reference
    return eff - eff.mean()


def estimate(obs: pd.DataFrame, n_boot: int = 300, seed: int = 0) -> pd.DataFrame:
    """Factor per league with a 95% cluster-bootstrap interval, plus sample sizes."""
    leagues = sorted(obs.league.unique())
    point = _fit(obs, leagues)
    rng = np.random.default_rng(seed)
    groups = {pid: g for pid, g in obs.groupby("player_id")}
    ids = np.array(list(groups))
    boots = []
    for _ in range(n_boot):
        sample = rng.choice(ids, size=len(ids), replace=True)
        # relabel so duplicated players count as distinct clusters
        b = pd.concat([groups[p].assign(player_id=k) for k, p in enumerate(sample)])
        if b.league.nunique() == len(leagues):
            boots.append(_fit(b, leagues))
    boots = np.array(boots)
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    n_obs = obs.groupby("league").size()
    return pd.DataFrame({
        "league": leagues,
        "factor": np.exp(point),
        "ci_low": np.exp(lo),
        "ci_high": np.exp(hi),
        "n_obs": [int(n_obs[lg]) for lg in leagues],
        "n_movers": obs.player_id.nunique(),
    })
