"""Value-versus-performance lens: is a player priced low (or high) for what he produces?

A pricing model predicts log market value from performance and context:
    current composite percentile, last season's composite, age, minutes, league, position
Residual = log(actual value) - log(predicted value). Negative = valued below what peers with the same
output and age are valued at ("underpriced"), positive = above ("overpriced").

What the residual can and cannot mean. Market value is a Transfermarkt editors'/community estimate
updated a few times a year, so a part of any residual is simply lag: a player who just had a big season
has not been repriced yet. Whether the residual predicts *later* value growth (the market catching up)
is an empirical question, answered by `backtest` / ml.evaluate_value_lens with the pricing model refit
at every origin on data up to that season only.

Covers forwards, wingers/attacking mids and midfielders: the positions with an attacking composite
(ml.outcomes). Defenders and goalkeepers would need defensive data we do not have.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from ml.outcomes import COMPOSITES

FEATURES = ["composite", "prev_composite", "age", "minutes", "log_league_factor", "is_wing", "is_mid"]


def build_panel(out: pd.DataFrame) -> pd.DataFrame:
    """Player-seasons with a composite, a season-end value and 900+ minutes (one row per player-season).

    `out` is the output of ml.outcomes.build_outcomes + ml.learned.add_trend (has composite, trend, value_now)."""
    d = out[out.position_group.isin(COMPOSITES) & (out.minutes >= 900) & out.age.notna()
            & out.composite.notna() & (out.value_now > 0)].copy()
    d = d.sort_values("minutes").groupby(["player_id", "season"], as_index=False).tail(1)  # main league
    d["prev_composite"] = (d.composite - d.trend).fillna(d.composite)  # no previous season: assume steady
    d["is_wing"] = (d.position_group == "WING_AM").astype(float)
    d["is_mid"] = (d.position_group == "MID").astype(float)
    d["log_value"] = np.log(d.value_now)
    return d.reset_index(drop=True)


class PricingModel:
    """Gradient-boosted regression of log value; monotone in current output and in minutes."""

    def __init__(self, seed: int = 0):
        cst = [1, 0, 0, 1, 0, 0, 0]  # composite up => value up; minutes up => value up; others free
        self.model = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.06, max_iter=250, min_samples_leaf=40,
                                                   monotonic_cst=cst, random_state=seed)

    def fit(self, panel: pd.DataFrame) -> "PricingModel":
        self.model.fit(panel[FEATURES], panel.log_value)
        return self

    def residual(self, panel: pd.DataFrame) -> np.ndarray:
        return (panel.log_value - self.model.predict(panel[FEATURES])).to_numpy()


def crossfit_residual(train: pd.DataFrame, cross: pd.DataFrame, folds: int = 5, seed: int = 0) -> np.ndarray:
    """Residuals for `cross` rows from models that never saw that player (players split into folds).

    Without this a row's own value pulls the model toward it and residuals look smaller than they are."""
    rng = np.random.default_rng(seed)
    players = train.player_id.unique()
    fold_of = dict(zip(players, rng.integers(0, folds, len(players))))
    train_fold = train.player_id.map(fold_of).to_numpy()
    cross_fold = cross.player_id.map(fold_of).to_numpy()
    resid = np.full(len(cross), np.nan)
    for k in range(folds):
        m = cross_fold == k
        if m.any():
            resid[m] = PricingModel(seed).fit(train[train_fold != k]).residual(cross[m])
    return resid


def future_log_change(panel: pd.DataFrame, values: dict, horizon: int) -> pd.Series:
    """log(value `horizon` seasons later) - log(value now); NaN when the player is not on a top-5 squad then.

    Dropping players who leave the top-5 leagues makes this conditional on staying (stated, not hidden)."""
    later = [values.get(int(t), {}).get(s + horizon, np.nan) if pd.notna(t) else np.nan
             for t, s in zip(panel.tm_player_id, panel.season)]
    return np.log(pd.Series(later, index=panel.index)) - panel.log_value


VALUE_FLOOR = 25_000  # Transfermarkt's lowest listed value; used for players retired or without a value


def history_index(history: pd.DataFrame) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """tm_player_id -> (sorted dates, values) from the market-value history table."""
    h = history.assign(date=pd.to_datetime(history.date)).sort_values(["tm_player_id", "date"])
    return {int(k): (g.date.to_numpy(), g.value_eur.to_numpy(dtype=float)) for k, g in h.groupby("tm_player_id")}


def season_end_value(index: dict, tm_id, season: int):
    """Value on 15 June after `season` (the date that reproduces the squad-page season-end value for 93% of
    players); NaN when there is no history yet at that date."""
    if pd.isna(tm_id) or int(tm_id) not in index:
        return np.nan
    dates, vals = index[int(tm_id)]
    i = np.searchsorted(dates, np.datetime64(f"{season + 1}-06-15"), side="right") - 1
    return float(vals[i]) if i >= 0 else np.nan


def complete_changes(res: pd.DataFrame, index: dict, horizon: int) -> pd.DataFrame:
    """Fill the value change of players who left the top-5 squads from their full Transfermarkt history.

    Adds `delta_full` (squad-page change where observed, history-based otherwise, NaN if no history) and
    `leaver` (True where the squad-page change was missing)."""
    res = res.copy()
    res["leaver"] = res.delta.isna()
    later = [season_end_value(index, t, s + horizon) for t, s in zip(res.tm_player_id, res.season)]
    later = np.where(np.isnan(later), np.nan, np.maximum(later, VALUE_FLOOR))
    res["delta_full"] = res.delta.where(~res.leaver, np.log(later) - res.log_value)
    return res


def backtest(panel: pd.DataFrame, values: dict, origins=range(2016, 2024), horizon: int = 1,
             keep_missing: bool = False) -> pd.DataFrame:
    """Rows (one per target) with the origin-fitted residual and the realised value change.

    At origin t the pricing model is fitted on seasons <= t only; targets are the season-t rows."""
    rows = []
    for t in origins:
        train, cross = panel[panel.season <= t], panel[panel.season == t]
        if len(train) < 500 or len(cross) < 50:
            continue
        r = cross.assign(origin=t, resid=crossfit_residual(train, cross), delta=future_log_change(cross, values, horizon))
        rows.append(r)
    res = pd.concat(rows, ignore_index=True)
    if keep_missing:
        # delta is NaN when the player is no longer on a top-5 squad `horizon` seasons later. Keep those rows,
        # but only for origins whose future season has already happened (NaN must mean "gone", not "not yet").
        return res[res.origin + horizon <= panel.season.max()]
    return res[res.delta.notna()]
