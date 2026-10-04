import numpy as np
import pandas as pd
import pytest

from ml.forecast import Forecaster
from ml.similarity import ATTACK, DEFENCE

SQUADS = pd.DataFrame(columns=["tm_player_id", "season", "market_value_eur"])


def _row(pid, season, comp, group="FWD", age=21.0, minutes=2000):
    r = {"player_id": pid, "player_name": f"P{pid}", "season": season, "league": "EPL", "team": "T", "position_group": group,
         "age": age, "minutes": minutes, "log_league_factor": 0.0, "league_jump": 0.0, "tm_player_id": np.nan}
    r.update({c: 0.3 + comp / 400 for c in ATTACK + DEFENCE})
    r.update({f"{c}_pct_global": comp for c in ["npxg", "xa", "xg_chain", "key_passes", "xg_buildup"]})
    return r


def _world(seed=0):
    """Composite is persistent: what a player shows in 2016 predicts what he shows in 2018."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(400):
        comp = rng.uniform(5, 95)
        rows.append(_row(i, 2016, comp, age=20 + rng.uniform(0, 2)))
        later = float(np.clip(comp + rng.normal(0, 8), 0, 100))
        rows.append(_row(i, 2018, later, age=22 + rng.uniform(0, 2)))
    rows.append(_row(9001, 2019, 92.0, age=21.0))                    # strong target
    rows.append(_row(9002, 2019, 12.0, age=21.0))                    # weak target
    rows.append(_row(9003, 2019, 50.0, group="DEF", age=21.0))       # defender: no performance tier
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def fc():
    return Forecaster(_world(), SQUADS, horizon=3, as_of=2019, n_boot=10, calibration=None)


def test_probabilities_are_valid_and_ordered_by_the_underlying_signal(fc):
    hi, lo = fc.forecast(9001, 2019), fc.forecast(9002, 2019)
    for f in (hi, lo):
        assert f.source == "learned model" and f.probs.sum() == pytest.approx(1.0)
        assert (f.lo <= f.hi).all() and len(f.probs) == 4
    elite = hi.classes.index("elite")
    assert hi.probs[elite] > lo.probs[elite]


def test_only_comps_with_finished_windows_are_shown(fc):
    f = fc.forecast(9001, 2019)
    assert (f.comps_view.comps.season + 3 <= 2019).all() and f.comps_view.n_comps > 0


def test_defenders_fall_back_to_comps_and_base_rate(fc):
    f = fc.forecast(9003, 2019)
    assert f.source == "comps + base rate" and f.classes == ["out", "retained"]
    assert f.probs.sum() == pytest.approx(1.0)


def test_value_projection_is_capped_at_the_highest_value_in_the_data():
    world = _world()
    world["tm_player_id"] = np.arange(len(world), dtype=float)
    squads = pd.DataFrame({"tm_player_id": world.tm_player_id, "season": world.season,
                           "market_value_eur": np.where(world.season == 2016, 10e6, 90e6)})
    squads.loc[squads.tm_player_id == world.index[world.player_id == 9001][0], "market_value_eur"] = 180e6   # target near the top
    f = Forecaster(world, squads, horizon=3, as_of=2019, n_boot=3, calibration=None).forecast(9001, 2019)
    assert f.value_ceiling == 180e6
    assert f.value_range is None or max(f.value_range.values()) <= 180e6


def test_calibration_map_is_applied_to_the_headline_probability():
    cal = {"slope": 1.0, "intercept": -2.0}                      # strongly shrinks P(elite)
    raw = Forecaster(_world(), SQUADS, horizon=3, as_of=2019, n_boot=3, calibration=None).forecast(9001, 2019)
    shrunk = Forecaster(_world(), SQUADS, horizon=3, as_of=2019, n_boot=3, calibration=cal).forecast(9001, 2019)
    e = raw.classes.index("elite")
    assert shrunk.probs[e] < raw.probs[e] and shrunk.probs.sum() == pytest.approx(1.0)
