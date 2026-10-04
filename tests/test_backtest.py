import numpy as np
import pandas as pd
import pytest

from ml.backtest import boot_diff, calibration, pinball, tier_losses
from ml.learned import TierModel, ValueModel, add_trend, design
from ml.outcomes import PERF_TIERS


def test_pinball_is_zero_for_a_perfect_forecast_and_penalises_the_wrong_side_more():
    assert pinball(1.0, np.array([1.0, 1.0, 1.0])) == 0.0
    # truth far above the forecast: under-prediction costs tau*|err|, so the 0.9 quantile bites hardest
    assert pinball(2.0, np.array([0.0, 0.0, 0.0])) == pytest.approx((0.1 + 0.5 + 0.9) / 3 * 2.0)


def test_tier_losses_match_hand_computed_brier_and_log_loss():
    recs = pd.DataFrame([{"classes": PERF_TIERS, "truth": "elite", "p_model": np.array([0.1, 0.2, 0.3, 0.4])}])
    r = tier_losses(recs, "model").iloc[0]
    assert r.brier == pytest.approx(0.1**2 + 0.2**2 + 0.3**2 + 0.6**2)
    assert r.logloss == pytest.approx(-np.log(0.4))


def test_boot_diff_detects_a_real_difference_and_not_a_null_one():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(200), 3)
    a = rng.normal(0.0, 1.0, 600)
    m, lo, hi = boot_diff(a, a + 0.5, groups)
    assert m == pytest.approx(-0.5) and hi < 0                   # clearly better
    m, lo, hi = boot_diff(a, rng.permutation(a), groups)
    assert lo < 0 < hi                                           # indistinguishable


def test_calibration_bins_by_predicted_probability():
    p = np.array([0.1] * 50 + [0.9] * 50)
    y = np.array([0] * 45 + [1] * 5 + [1] * 45 + [0] * 5, dtype=float)
    c = calibration(p, y, bins=2)
    assert c.predicted.round(2).tolist() == [0.1, 0.9] and c.observed.round(2).tolist() == [0.1, 0.9]


def _rows(n=300, seed=0):
    rng = np.random.default_rng(seed)
    comp = rng.uniform(0, 100, n)
    tier = np.where(comp > 85, "elite", np.where(comp > 60, "good", "regular"))   # learnable signal
    return pd.DataFrame({
        "player_id": np.arange(n), "season": 2018, "composite": comp, "age": rng.uniform(18, 23, n),
        "value_now": rng.uniform(1e6, 5e7, n), "log_league_factor": 0.0, "league_jump": 0.0, "minutes": 2000.0,
        "position_group": "FWD", "tier": tier, "value_ratio": np.exp(0.01 * comp + rng.normal(0, 0.2, n)),
    }).assign(trend=np.nan)


def test_learned_tier_model_returns_valid_probabilities_and_learns_the_signal():
    rows = _rows()
    p = TierModel().fit(rows).predict(rows)
    assert p.shape == (len(rows), 4) and np.allclose(p.sum(axis=1), 1.0)
    assert p[rows.composite.idxmax(), PERF_TIERS.index("elite")] > p[rows.composite.idxmin(), PERF_TIERS.index("elite")]


def test_learned_value_quantiles_are_ordered_and_follow_the_signal():
    rows = _rows()
    q = ValueModel().fit(rows).predict(rows)
    assert (np.diff(q, axis=1) >= 0).all()
    assert q[rows.composite.idxmax(), 1] > q[rows.composite.idxmin(), 1]


def test_add_trend_is_composite_minus_last_seasons_composite():
    out = pd.DataFrame({"player_id": [1, 1, 2], "season": [2019, 2020, 2020], "minutes": [1000] * 3, "composite": [40.0, 55.0, 70.0]})
    t = add_trend(out).sort_values(["player_id", "season"]).trend.tolist()
    assert t[1] == 15.0 and np.isnan(t[0]) and np.isnan(t[2])
    assert design(add_trend(out).assign(value_now=np.nan, position_group="FWD", age=20.0, log_league_factor=0.0,
                                         league_jump=0.0)).shape[0] == 3


def test_learned_models_skip_training_rows_without_an_age():
    rows = _rows()
    rows.loc[:5, "age"] = np.nan
    assert TierModel().fit(rows).predict(rows.dropna(subset=["age"])).shape[0] == len(rows) - 6
    assert ValueModel().fit(rows).predict(rows.dropna(subset=["age"])).shape == (len(rows) - 6, 3)


def test_elite_calibration_shrinks_overconfident_probabilities_and_keeps_a_valid_distribution():
    from ml.learned import apply_elite_calibration, fit_elite_calibration

    rng = np.random.default_rng(0)
    p = rng.uniform(0.02, 0.98, 4000)
    y = rng.uniform(size=4000) < p * 0.5            # truth is half as likely as the model claims
    cal = fit_elite_calibration(p, y)
    probs = np.column_stack([np.full(3, 0.3), np.full(3, 0.3), np.full(3, 0.2), [0.2, 0.6, 0.9]])
    out = apply_elite_calibration(probs, cal)
    assert np.allclose(out.sum(axis=1), 1.0) and (out[:, 3] < probs[:, 3]).all() and (np.diff(out[:, 3]) > 0).all()
    assert len(np.unique(out[:, 3].round(6))) == 3  # smooth: distinct inputs keep distinct outputs (no plateaus)
    assert np.array_equal(apply_elite_calibration(probs, None), probs)
