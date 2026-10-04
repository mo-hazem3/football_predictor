"""Trajectory projection: what did comparable players go on to become?

For a target player-season, take the k closest comps whose outcome window had already finished
by the as-of date, and read off what became of them. The answer is a *distribution*, not a point:

  * outcome-tier probabilities with 80% credible intervals. Comp counts are shrunk toward the
    base rate of everyone of that position and age (a Dirichlet prior worth `prior_strength`
    comps), so a thin or lopsided comp set cannot produce a confident 0% / 100%.
  * a market-value range: the comps' peak-value / current-value ratios, applied to the target's
    current value (conditional on staying in a top-5 squad).

Leakage rule (asserted): with horizon H and as-of season t, every comp season s satisfies
s + H <= t, i.e. the comp's whole outcome window was already observed at t.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml.outcomes import classes_for
from ml.similarity import SimilarityEngine

LAST_SEASON = 2025


@dataclass
class Projection:
    group: str
    horizon: int
    classes: list[str]
    probs: np.ndarray              # posterior mean per class
    lo: np.ndarray                 # 10th percentile of the posterior
    hi: np.ndarray                 # 90th percentile
    counts: np.ndarray             # raw comp counts per class
    base_rate: np.ndarray          # position + age base rate (the prior)
    n_comps: int
    comps: pd.DataFrame = field(repr=False)
    value_now: float | None = None
    value_ratio_quantiles: dict | None = None   # {0.1: .., 0.5: .., 0.9: ..}, None if < 5 comps with a value
    n_value_comps: int = 0

    def value_range(self) -> dict | None:
        if self.value_ratio_quantiles is None or not self.value_now:
            return None
        return {q: self.value_now * r for q, r in self.value_ratio_quantiles.items()}

    def table(self) -> pd.DataFrame:
        return pd.DataFrame({"outcome": self.classes, "probability": self.probs, "p10": self.lo, "p90": self.hi,
                             "comps": self.counts, "base_rate": self.base_rate})


def age_peer_rows(outcomes: pd.DataFrame, group: str, age: float, max_season: int, window: float) -> pd.DataFrame:
    """Everyone of the same position and similar age whose outcome is already known at the as-of date."""
    o = outcomes
    return o[(o.position_group == group) & (o.minutes >= 900) & o.age.notna() & ((o.age - age).abs() <= window)
             & (o.season <= max_season) & o.observable & o.tier.notna()]


def class_rates(tiers: pd.Series, classes: list[str]) -> np.ndarray:
    counts = tiers.value_counts().reindex(classes, fill_value=0).to_numpy(dtype=float)
    return counts / counts.sum() if counts.sum() else np.full(len(classes), 1.0 / len(classes))


def posterior(counts: np.ndarray, base_rate: np.ndarray, prior_strength: float, n_draws: int = 4000, seed: int = 0):
    alpha = counts + prior_strength * base_rate + 1e-9
    draws = np.random.default_rng(seed).dirichlet(alpha, size=n_draws)
    return alpha / alpha.sum(), np.percentile(draws, 10, axis=0), np.percentile(draws, 90, axis=0)


def project(engine: SimilarityEngine, outcomes: pd.DataFrame, player_id: int, season: int, horizon: int = 3,
            k: int = 30, as_of: int | None = None, prior_strength: float = 10.0) -> Projection:
    """Project a player-season. `outcomes` is the output of ml.outcomes.build_outcomes on the same features."""
    as_of = LAST_SEASON if as_of is None else as_of
    cutoff = as_of - horizon                          # latest comp season whose window is fully observed
    t = engine.target_row(player_id, season)
    comps = engine.comps(player_id, season, k=k, max_season=cutoff)
    keys = ["player_id", "season", "league"]
    comps = comps.merge(outcomes[keys + ["tier", "value_ratio", "observable"]], on=keys, how="left", suffixes=("", "_o"))
    comps = comps[comps.observable.fillna(False).astype(bool) & comps.tier.notna()]
    assert (comps.season + horizon <= as_of).all(), "leakage: a comp's outcome window extends past the as-of date"

    classes = classes_for(t.position_group)
    peers = age_peer_rows(outcomes, t.position_group, t.age, cutoff, engine.age_window)
    base = class_rates(peers.tier, classes)
    counts = comps.tier.value_counts().reindex(classes, fill_value=0).to_numpy(dtype=float)
    probs, lo, hi = posterior(counts, base, prior_strength)

    now = outcomes[(outcomes.player_id == player_id) & (outcomes.season == season)].value_now
    value_now = float(now.iloc[0]) if len(now) and not pd.isna(now.iloc[0]) else None
    r = comps.value_ratio.dropna()
    quant = {q: float(np.quantile(r, q)) for q in (0.1, 0.5, 0.9)} if len(r) >= 5 else None
    return Projection(t.position_group, horizon, classes, probs, lo, hi, counts, base, len(comps), comps,
                      value_now, quant, len(r))
