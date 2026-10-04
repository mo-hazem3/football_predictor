"""Player outlook: where will his level be in 1, 2 and 3 seasons? A fan chart, not a single line.

Level = the position-specific composite percentile (0-100; ml.outcomes.COMPOSITES), so the chart reads
"a 78th-percentile winger now, likely 70 to 88 in two seasons". Covers forwards, wingers/attacking mids and
midfielders (defenders and goalkeepers have no composite).

For each horizon h in {1, 2, 3} three models are compared in ml.evaluate_outlook:
  persistence   y[t+h] = y[t]                          (+ the empirical spread of what actually happened)
  shrinkage     y[t+h] = a_h + b_h * y[t]              (regression to the position mean, fitted per position)
  quantile GB   gradient-boosted 10/50/90% quantile regressors on level, last season's change, age, minutes,
                league strength and jump, market value, position
Bands are CONDITIONAL on the player still getting 900+ minutes in the five leagues at t+h (otherwise there
is no level to measure), so a second model gives P(still a regular) at each horizon. The two together are
the honest picture: "if he is still playing at this level of competition, here is the range".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.learned import design
from ml.outcomes import COMPOSITES, MIN_MINUTES_OUTCOME

HORIZONS = (1, 2, 3)
QUANTILES = (0.1, 0.5, 0.9)
GROUPS = tuple(COMPOSITES)


def build_pairs(out: pd.DataFrame, last_season: int) -> pd.DataFrame:
    """One row per reliable player-season (900+ minutes, composite known) with his level at t+1, t+2, t+3.

    `out` needs composite, trend, value_now, log_league_factor, league_jump (ml.outcomes + ml.learned.add_trend).
    y{h} is NaN when he has no 900+ minute season at t+h; known{h} says whether t+h has happened by `last_season`
    (so NaN with known = False means "not yet", NaN with known = True means "not a top-5 regular any more")."""
    d = out[out.position_group.isin(GROUPS) & (out.minutes >= MIN_MINUTES_OUTCOME) & out.composite.notna() & out.age.notna()]
    d = d.sort_values("minutes").groupby(["player_id", "season"], as_index=False).tail(1).reset_index(drop=True)
    level = d.set_index(["player_id", "season"]).composite
    for h in HORIZONS:
        idx = pd.MultiIndex.from_arrays([d.player_id, d.season + h])
        d[f"y{h}"] = level.reindex(idx).to_numpy()
        d[f"known{h}"] = (d.season + h) <= last_season
    return d


class Outlook:
    """Fan-chart models, fitted only on pairs whose t+h had already happened (`known`)."""

    def __init__(self, n_estimators: int = 100, seed: int = 0):
        self.n_estimators, self.seed = n_estimators, seed

    # ------------------------------------------------------------------ fit
    def fit(self, pairs: pd.DataFrame) -> "Outlook":
        self.gb, self.retention, self.shrink, self.persist = {}, {}, {}, {}
        for h in HORIZONS:
            known = pairs[pairs[f"known{h}"]]
            seen = known[known[f"y{h}"].notna()]
            if len(seen) < 100:
                raise ValueError(f"too few training pairs for horizon {h}: {len(seen)}")
            x, y = design(seen), seen[f"y{h}"].to_numpy()
            self.gb[h] = [GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=self.n_estimators, max_depth=3,
                                                    learning_rate=0.05, subsample=0.8, min_samples_leaf=20,
                                                    random_state=self.seed).fit(x, y) for q in QUANTILES]
            xk = design(known)
            sc = StandardScaler().fit(xk)
            self.retention[h] = (sc, LogisticRegression(C=0.3, max_iter=2000).fit(sc.transform(xk), known[f"y{h}"].notna().astype(int)))
            for g in GROUPS:
                s = seen[seen.position_group == g]
                if len(s) < 30:
                    s = seen
                slope, intercept = np.polyfit(s.composite, s[f"y{h}"], 1)
                self.shrink[h, g] = (intercept, slope, np.quantile(s[f"y{h}"] - (intercept + slope * s.composite), QUANTILES))
                self.persist[h, g] = np.quantile(s[f"y{h}"] - s.composite, QUANTILES)
        return self

    # ------------------------------------------------------------------ predict
    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        """(n, horizons, quantiles) level forecasts from the quantile GB models, sorted so quantiles never cross."""
        x = design(rows)
        out = np.stack([np.column_stack([m.predict(x) for m in self.gb[h]]) for h in HORIZONS], axis=1)
        return np.clip(np.sort(out, axis=2), 0.0, 100.0)

    def predict_observed(self, rows: pd.DataFrame) -> np.ndarray:
        """(n, horizons): probability he still has a 900+ minute top-5 season at t+h."""
        x = design(rows)
        return np.column_stack([self.retention[h][1].predict_proba(self.retention[h][0].transform(x))[:, 1] for h in HORIZONS])

    def predict_baselines(self, rows: pd.DataFrame) -> dict[str, np.ndarray]:
        """The comparison forecasts, same shape as `predict`."""
        c, g = rows.composite.to_numpy(), rows.position_group.to_numpy()
        pers = np.zeros((len(rows), len(HORIZONS), len(QUANTILES)))
        shr = np.zeros_like(pers)
        for j, h in enumerate(HORIZONS):
            for i in range(len(rows)):
                pers[i, j] = c[i] + self.persist[h, g[i]]
                a, b, spread = self.shrink[h, g[i]]
                shr[i, j] = a + b * c[i] + spread
        return {"persistence": np.clip(pers, 0, 100), "shrinkage": np.clip(shr, 0, 100)}


def pinball(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Mean pinball loss over the quantile columns, per row (y: (n,), q: (n, len(QUANTILES)))."""
    t = np.array(QUANTILES)[None, :]
    d = y[:, None] - q
    return np.maximum(t * d, (t - 1) * d).mean(axis=1)
