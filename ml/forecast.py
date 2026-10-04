"""User-facing trajectory forecast: calibrated probabilities plus the comps as visible evidence.

Why two views. The backtest (ml.backtest, docs/backtest_h3.txt) found that probabilities read
straight off the comps' outcomes are *worse* than a regularised learned model on a few summary
features, and no better than simply matching on current level. So:

  * HEADLINE probabilities come from the learned tier model (logistic regression on current
    level, age, minutes, last season's change, league strength and jump, current market value).
    The 10-90% range is a bootstrap over players and shows *model* uncertainty only: the
    probabilities themselves already are the outcome distribution.
  * The COMPS are shown as evidence: who the closest comparable players were and what each of
    them actually became. Their empirical outcome mix is displayed too, labelled as such.
  * P(elite) is passed through an Platt-scaling map fitted on out-of-time backtest predictions
    (docs/elite_calibration.json, written by ml.backtest), because the raw model overstates it.
  * The market-value range comes from gradient-boosted quantile models, conditional on the
    player staying on a top-5 squad.

Only comps whose whole outcome window has finished by `as_of` are used (see ml.trajectory).
The learned model covers forwards, wingers/attacking mids and midfielders; defenders and
goalkeepers get retention from the comps and the base rate only, because no performance
outcome is defined for them (see ml.outcomes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import json
from pathlib import Path

from ml.learned import TierModel, ValueModel, add_trend, apply_elite_calibration
from ml.outcomes import COMPOSITES, PERF_TIERS, add_composite, build_outcomes, value_series
from ml.similarity import SimilarityEngine
from ml.trajectory import Projection, project


DEFAULT_CALIBRATION = Path(__file__).resolve().parent.parent / "docs" / "elite_calibration.json"


@dataclass
class Forecast:
    name: str
    season: int
    group: str
    age: float
    horizon: int
    as_of: int
    classes: list[str]
    probs: np.ndarray                 # headline (learned model) when available, else comps posterior
    lo: np.ndarray                    # 10th percentile across bootstrap fits (NaN when not available)
    hi: np.ndarray
    source: str                       # 'learned model' | 'comps + base rate'
    comps_view: Projection = field(repr=False)
    value_now: float | None = None
    value_range: dict | None = None   # {0.1: €, 0.5: €, 0.9: €}, capped at value_ceiling
    value_ceiling: float | None = None

    def table(self) -> pd.DataFrame:
        t = pd.DataFrame({"outcome": self.classes, "probability": self.probs, "p10": self.lo, "p90": self.hi,
                          "comps_said": self.comps_view.probs, "base_rate": self.comps_view.base_rate})
        return t


class Forecaster:
    def __init__(self, features: pd.DataFrame, squads: pd.DataFrame, horizon: int = 3, as_of: int = 2025,
                 tier_c: float = 0.03, n_boot: int = 100, seed: int = 0, calibration: dict | str | Path | None = "default"):
        self.horizon, self.as_of = horizon, as_of
        if calibration == "default":
            calibration = DEFAULT_CALIBRATION if DEFAULT_CALIBRATION.exists() else None
        self.calibration = json.loads(Path(calibration).read_text(encoding="utf-8")) if isinstance(calibration, (str, Path)) else calibration
        feats = features[features.season <= as_of]
        self.out = add_trend(build_outcomes(add_composite(feats), value_series(squads[squads.season <= as_of]),
                                            horizon, last_season=as_of))
        self.engine = SimilarityEngine(self.out)
        known = self.out[self.out.observable & (self.out.minutes >= 900)]
        train = known[known.tier.notna()]
        self.tier = TierModel(c=tier_c).fit(train)
        self.value = ValueModel().fit(known)
        # too few players are valued near the top for the model to learn a ceiling, so cap projections
        # at the highest value in the data rather than extrapolate (e.g. a EUR 200m player to EUR 600m)
        sq = squads[squads.season <= as_of].market_value_eur.dropna()
        self.value_ceiling = float(sq.max()) if len(sq) else None
        # bootstrap over players (all of a player's rows move together)
        rng = np.random.default_rng(seed)
        perf = train[train.position_group.isin(COMPOSITES) & train.age.notna()]
        by_player = {pid: g for pid, g in perf.groupby("player_id")}
        ids = np.array(list(by_player))
        self.boot = [TierModel(c=tier_c).fit(pd.concat([by_player[p] for p in rng.choice(ids, len(ids))]))
                     for _ in range(n_boot)]

    def forecast(self, player_id: int, season: int, k: int = 30) -> Forecast:
        t = self.engine.target_row(player_id, season)
        comps_view = project(self.engine, self.out, player_id, season, self.horizon, k=k, as_of=self.as_of)
        row = pd.DataFrame([t]).infer_objects()

        if t.position_group in COMPOSITES:
            probs = apply_elite_calibration(self.tier.predict(row), self.calibration)[0]
            draws = (np.vstack([apply_elite_calibration(m.predict(row), self.calibration) for m in self.boot])
                     if self.boot else probs[None, :])
            lo, hi = np.percentile(draws, 10, axis=0), np.percentile(draws, 90, axis=0)
            classes, source = PERF_TIERS, "learned model"
        else:
            classes, probs, lo, hi = comps_view.classes, comps_view.probs, comps_view.lo, comps_view.hi
            source = "comps + base rate"

        value_now = float(t.value_now) if pd.notna(t.value_now) and t.value_now > 0 else None
        value_range = None
        if value_now:
            q = np.exp(self.value.predict(row)[0])
            if not np.isnan(q).any():
                value_range = {k: value_now * r for k, r in zip((0.1, 0.5, 0.9), q)}
                if self.value_ceiling:
                    value_range = {k: min(v, self.value_ceiling) for k, v in value_range.items()}
        return Forecast(t.player_name, season, t.position_group, float(t.age), self.horizon, self.as_of, classes,
                        np.asarray(probs), np.asarray(lo), np.asarray(hi), source, comps_view, value_now, value_range,
                        self.value_ceiling)
