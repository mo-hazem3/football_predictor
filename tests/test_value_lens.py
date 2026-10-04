import numpy as np
import pandas as pd
import pytest

from ml.value_lens import (FEATURES, VALUE_FLOOR, PricingModel, complete_changes, crossfit_residual, future_log_change,
                            history_index, season_end_value)


def _panel(n=400, seed=0):
    """Value is a clear function of output and age plus noise."""
    rng = np.random.default_rng(seed)
    comp = rng.uniform(5, 95, n)
    age = rng.uniform(19, 33, n)
    logv = 13 + 0.03 * comp - 0.04 * (age - 24) ** 2 / 4 + rng.normal(0, 0.3, n)
    return pd.DataFrame({"player_id": np.arange(n), "tm_player_id": np.arange(n), "season": 2020, "composite": comp,
                         "prev_composite": comp, "age": age, "minutes": 2000.0, "log_league_factor": 0.0, "is_wing": 0.0,
                         "is_mid": 0.0, "log_value": logv, "value_now": np.exp(logv)})


def test_residual_is_negative_for_a_player_priced_below_peers_with_the_same_output():
    p = _panel()
    p.loc[0, ["composite", "age", "prev_composite"]] = [80.0, 24.0, 80.0]
    p.loc[0, "log_value"] = 12.0                       # far cheaper than similar players
    resid = crossfit_residual(p, p)
    assert resid[0] < -0.8 and abs(np.median(resid)) < 0.15


def test_crossfit_residuals_come_from_models_that_never_saw_the_player():
    p = _panel(n=300)
    p.loc[5, "log_value"] += 3.0                       # an outlier the model would otherwise partly absorb
    in_sample = PricingModel().fit(p).residual(p)[5]
    crossfit = crossfit_residual(p, p)[5]
    assert crossfit > in_sample > 1.5                  # held-out residual is larger: no self-fitting


def test_future_change_needs_the_player_to_have_a_value_then():
    p = pd.DataFrame({"tm_player_id": [1, 2], "season": [2020, 2020], "log_value": np.log([10e6, 5e6])})
    values = {1: {2021: 20e6}, 2: {2022: 5e6}}        # player 2 has no 2021 value: left the top-5 squads
    d = future_log_change(p, values, 1)
    assert d.iloc[0] == pytest.approx(np.log(2.0)) and np.isnan(d.iloc[1])


def test_leavers_get_their_change_from_the_history_at_the_june_cutoff():
    history = pd.DataFrame({"tm_player_id": [2, 2, 2, 3],
                            "date": ["2020-10-01", "2021-05-20", "2021-09-01", "2021-01-01"],
                            "value_eur": [4_000_000, 3_000_000, 1_000_000, 0]})
    idx = history_index(history)
    assert season_end_value(idx, 2, 2020) == 3_000_000        # 15 Jun 2021 picks the May value, not September's
    assert np.isnan(season_end_value(idx, 9, 2020))           # unknown player
    res = pd.DataFrame({"tm_player_id": [1, 2, 3, 9], "season": 2020, "log_value": np.log([10e6, 4e6, 2e6, 1e6]),
                        "delta": [0.2, np.nan, np.nan, np.nan]})
    out = complete_changes(res, idx, 1)
    assert out.leaver.tolist() == [False, True, True, True]
    assert out.delta_full.iloc[0] == 0.2                      # stayers keep the squad-page change
    assert out.delta_full.iloc[1] == pytest.approx(np.log(1e6 / 4e6))   # end of 2021 = 15 Jun 2022: the Sept 2021 value stands
    assert out.delta_full.iloc[2] == pytest.approx(np.log(VALUE_FLOOR / 2e6))   # value 0 is floored, not -inf
    assert np.isnan(out.delta_full.iloc[3])                   # no history: stays unknown, never guessed
