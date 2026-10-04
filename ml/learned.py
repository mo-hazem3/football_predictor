"""Learned trajectory models, as a competitor to comp-based projection.

Both use a handful of summary features of the player-season (current level, age, current
market value, league strength and jump, minutes, last season's change), not the full stats
vector, and are trained only on rows whose outcome window had finished by the as-of date.

  tier model   multinomial logistic regression (L2) over the outcome tiers
  value model  gradient-boosted quantile regressors (10/50/90%) on log(peak value / value now)

Small, regularised models on purpose: a few thousand young-player rows is not enough for
anything flexible to beat a simple summary of current level.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.outcomes import COMPOSITES, PERF_TIERS

QS = (0.1, 0.5, 0.9)


def add_trend(out: pd.DataFrame) -> pd.DataFrame:
    """composite now minus composite last season (same player); NaN when there is no previous season."""
    prev = (out.sort_values("minutes").groupby(["player_id", "season"]).composite.last()
               .rename("prev_composite").reset_index().assign(season=lambda d: d.season + 1))
    return out.merge(prev, on=["player_id", "season"], how="left").assign(
        trend=lambda d: d.composite - d.prev_composite)


# columns of the design matrix that each ablation group removes
GROUPS = {"value": [3, 4], "league": [5, 6], "minutes": [7], "trend": [8, 9]}


def design(rows: pd.DataFrame, drop: tuple[str, ...] = ()) -> np.ndarray:
    """Feature matrix; missing values get a neutral fill plus an indicator.

    `drop` removes feature groups (value, league, minutes, trend) for ablation studies."""
    value = rows.value_now.where(rows.value_now > 0)
    comp = rows.composite.fillna(50.0)
    cols = [
        comp, rows.age, rows.age ** 2, np.log1p(value.fillna(0) / 1e6), value.isna().astype(float),
        rows.log_league_factor, rows.league_jump, rows.minutes / 3000.0,
        rows.trend.fillna(0.0), rows.trend.isna().astype(float),
        (rows.position_group == "WING_AM").astype(float), (rows.position_group == "MID").astype(float),
        (rows.position_group == "DEF").astype(float), (rows.position_group == "GK").astype(float),
        # curvature and level x age: a high current level persists less for the young, and the
        # linear logit overshoots at the top (chosen on the 2018-2020 backtest origins)
        ((comp - 50.0) / 25.0) ** 2, ((comp - 50.0) / 25.0) * (rows.age - 21.0) / 3.0,
    ]
    removed = {i for g in drop for i in GROUPS[g]}
    return np.column_stack([np.asarray(c, dtype=float) for i, c in enumerate(cols) if i not in removed])


class TierModel:
    def __init__(self, c: float = 0.03, drop: tuple[str, ...] = ()):
        self.c = c
        self.drop = drop

    def fit(self, rows: pd.DataFrame) -> "TierModel":
        rows = rows[rows.position_group.isin(COMPOSITES) & rows.tier.isin(PERF_TIERS) & rows.age.notna()]
        self.scaler = StandardScaler().fit(design(rows, self.drop))
        self.model = LogisticRegression(C=self.c, max_iter=2000).fit(self.scaler.transform(design(rows, self.drop)), rows.tier)
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        """Probabilities in PERF_TIERS order (classes unseen in training get ~0)."""
        p = self.model.predict_proba(self.scaler.transform(design(rows, self.drop)))
        full = np.full((len(rows), len(PERF_TIERS)), 1e-6)
        for j, c in enumerate(self.model.classes_):
            full[:, PERF_TIERS.index(c)] = p[:, j]
        return full / full.sum(axis=1, keepdims=True)


class ValueModel:
    def fit(self, rows: pd.DataFrame) -> "ValueModel":
        rows = rows[rows.value_ratio.notna() & (rows.value_now > 0) & rows.age.notna()]
        if rows.empty:  # no market-value history at all: predictions are NaN rather than an error
            self.models = None
            return self
        x, y = design(rows), np.log(rows.value_ratio.to_numpy())
        self.models = [GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=80, max_depth=2,
                                                 learning_rate=0.05, subsample=0.8, random_state=0).fit(x, y) for q in QS]
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        """Log-ratio quantiles (10/50/90), sorted so they never cross."""
        if self.models is None:
            return np.full((len(rows), len(QS)), np.nan)
        return np.sort(np.column_stack([m.predict(design(rows)) for m in self.models]), axis=1)


# ---------------------------------------------------------------- out-of-time calibration of P(elite)
# The tier model is overconfident for P(elite) between ~20% and ~70% (stable across backtest
# origins). A smooth monotone map fitted on *backtest* predictions (made as of one season, scored
# against what happened later) corrects it without the training-distribution mismatch that made an
# in-sample calibration layer fail. Platt scaling (two parameters) rather than isotonic regression:
# with ~800 out-of-time cases an isotonic fit is a handful of plateaus, which gives different
# players identical probabilities and one-sided uncertainty ranges.

def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_elite_calibration(p_elite: np.ndarray, is_elite: np.ndarray) -> dict:
    m = LogisticRegression(C=100.0).fit(_logit(np.asarray(p_elite, dtype=float))[:, None], np.asarray(is_elite, dtype=int))
    return {"slope": float(m.coef_[0, 0]), "intercept": float(m.intercept_[0])}


def apply_elite_calibration(probs: np.ndarray, cal: dict | None) -> np.ndarray:
    """Replace P(elite) (last column) by its calibrated value; spread the difference over the other tiers pro rata."""
    probs = np.atleast_2d(np.asarray(probs, dtype=float))
    if cal is None:
        return probs
    new = np.clip(1.0 / (1.0 + np.exp(-(cal["slope"] * _logit(probs[:, -1]) + cal["intercept"]))), 0.002, 0.98)
    rest = probs[:, :-1] / probs[:, :-1].sum(axis=1, keepdims=True)
    return np.column_stack([rest * (1 - new)[:, None], new])
