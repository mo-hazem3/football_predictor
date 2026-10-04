import numpy as np
import pandas as pd
import pytest

from ml import aging


def _synthetic(n_players=600, seed=0, noise=0.25):
    """Players with persistent skill and a known hump-shaped age effect, peaking at 27."""
    rng = np.random.default_rng(seed)
    f = lambda a: -0.004 * (a - 27) ** 2
    rows = []
    for pid in range(n_players):
        skill, start = rng.normal(0, 0.5), int(rng.integers(19, 28))
        for k in range(rng.integers(3, 8)):
            age = start + k
            if age > 35:
                break
            rows.append({"player_id": pid, "season": 2014 + k + (start - 19) % 4, "position_group": "MID", "age_i": age,
                         "minutes": 2000, "y": skill + f(age) + rng.normal(0, noise)})
    return pd.DataFrame(rows), f


def test_fit_curve_recovers_the_known_age_effect_relative_to_25():
    p, f = _synthetic(n_players=2500)
    c = aging.fit_curve(p, n_boot=10).set_index("age")
    for age in (20, 23, 27, 31):                      # ages with hundreds of observations
        assert c.loc[age, "effect"] == pytest.approx(f(age) - f(25), abs=0.05)
    assert c.loc[25, "effect"] == 0.0
    assert (c.lo <= c.effect + 1e-9).all() and (c.effect <= c.hi + 1e-9).all()
    assert aging.peak_age(c.reset_index(), min_obs=100) in (26, 27, 28)
    assert c.loc[34, "n_obs"] == 0                    # no data at an age: effect is meaningless there, and n_obs says so


def test_panel_divides_by_the_same_season_position_mean():
    rows = []
    for season, scale in ((2019, 1.0), (2020, 3.0)):  # a league-wide rise in output must not look like an age effect
        for pid in range(40):
            rows.append(dict(player_id=pid, season=season, league="EPL", position_group="MID", minutes=1500, age=24.4,
                             npxg_p90_adj=0.1 * scale * (1 + pid / 40), xa_p90_adj=0.05 * scale * (1 + pid / 40)))
    p = aging.panel(pd.DataFrame(rows), "attack")
    assert np.allclose(np.exp(p.y).groupby([p.season]).mean(), 1.0)
    assert p.age_i.eq(24).all()


def test_pairs_link_a_players_seasons_by_lag():
    p = pd.DataFrame({"player_id": [1, 1, 1, 2], "season": [2018, 2019, 2021, 2018], "position_group": "MID",
                      "age_i": [20, 21, 23, 30], "minutes": 1000, "y": [0.0, 0.1, 0.3, 0.5]})
    assert len(aging._pairs(p, 1)) == 1 and len(aging._pairs(p, 2)) == 1 and len(aging._pairs(p, 3)) == 1
    assert aging._pairs(p, 3).iloc[0][["y0", "y1"]].tolist() == [0.0, 0.3]


def test_shrinkage_beats_persistence_when_seasons_are_noisy():
    p, _ = _synthetic(n_players=900, noise=0.5)
    ev = aging.evaluate(p, origins=range(2017, 2019))
    s = aging.summarise(ev, []).set_index("model")
    assert s.loc["shrunk persistence", "MAE"] < s.loc["persistence", "MAE"]


def test_plateau_is_a_contiguous_range_around_the_peak_and_ignores_sparse_ages():
    ages = np.arange(18, 36)
    effect = np.where(ages <= 27, -0.004 * (ages - 27) ** 2, -0.004 * (ages - 27) ** 2 * 3)
    c = pd.DataFrame({"age": ages, "effect": effect, "n_obs": 100})
    lo, hi = aging.plateau(c, tol=0.03)
    assert lo <= 27 <= hi and (lo, hi) == (25, 28)
    c.loc[c.age == 18, ["effect", "n_obs"]] = [5.0, 2]     # a wild estimate from 2 observations must not define the peak
    assert aging.plateau(c, tol=0.03) == (25, 28)


def test_plateau_of_a_sparse_curve_is_none_not_an_error():
    c = pd.DataFrame({"age": [20, 21, 22], "effect": [0.0, 0.1, 0.2], "n_obs": [3, 5, 2]})
    assert aging.plateau(c, min_obs=30) is None
