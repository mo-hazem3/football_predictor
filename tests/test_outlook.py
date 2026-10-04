import numpy as np
import pandas as pd
import pytest

from ml.outlook import HORIZONS, QUANTILES, Outlook, build_pairs, pinball


def _world(n=700, seed=0, first=2014, last=2022):
    """Skill that drifts (a random walk) plus noise, so the future is more uncertain the further out it is; players with a
    low level are more likely to disappear (fewer than 900 minutes)."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(n):
        skill, start = rng.normal(0, 1), int(rng.integers(first, last - 3))
        age0 = rng.uniform(19, 31)
        for k, season in enumerate(range(start, last + 1)):
            skill += rng.normal(0, 0.25)
            comp = float(np.clip(50 + 17 * skill + rng.normal(0, 9), 1, 99))
            if rng.uniform() < 0.05 + 0.25 * (1 - comp / 100) ** 2:
                break                                                        # drops out: later seasons never appear
            rows.append(dict(player_id=pid, season=season, position_group=["FWD", "WING_AM", "MID"][pid % 3], minutes=2000.0,
                             composite=comp, age=age0 + k, value_now=1e6 * np.exp(2 + 0.03 * comp), log_league_factor=0.0,
                             league_jump=0.0, trend=np.nan))
    out = pd.DataFrame(rows)
    prev = out.assign(season=out.season + 1)[["player_id", "season", "composite"]].rename(columns={"composite": "prev"})
    out = out.merge(prev, on=["player_id", "season"], how="left")
    out["trend"] = out.composite - out.prev
    return out.drop(columns="prev")


def test_pairs_align_each_row_with_the_same_players_later_seasons():
    out = pd.DataFrame([
        dict(player_id=1, season=2018, position_group="FWD", minutes=2000, composite=60.0, age=22.0),
        dict(player_id=1, season=2019, position_group="FWD", minutes=2000, composite=70.0, age=23.0),
        dict(player_id=1, season=2021, position_group="FWD", minutes=2000, composite=80.0, age=25.0),
        dict(player_id=2, season=2018, position_group="MID", minutes=500, composite=55.0, age=22.0),    # too few minutes to be a base row
        dict(player_id=3, season=2018, position_group="DEF", minutes=2000, composite=np.nan, age=22.0),  # no composite for defenders
    ])
    p = build_pairs(out, last_season=2021).set_index(["player_id", "season"])
    assert list(p.index) == [(1, 2018), (1, 2019), (1, 2021)]
    r = p.loc[(1, 2018)]
    assert r.y1 == 70.0 and np.isnan(r.y2) and r.y3 == 80.0           # 2020 missing: not a top-5 regular that year
    assert bool(r.known1) and bool(r.known2) and bool(r.known3)
    assert p.loc[(1, 2021)][["known1", "known2", "known3"]].tolist() == [False, False, False]   # not yet happened, unlike "missing"


def test_a_missing_future_season_is_distinguishable_from_one_that_has_not_happened():
    out = pd.DataFrame([dict(player_id=1, season=2019, position_group="FWD", minutes=2000, composite=60.0, age=22.0)])
    p = build_pairs(out, last_season=2020)
    assert bool(p.known1.iloc[0]) and np.isnan(p.y1.iloc[0])           # 2020 happened and he is absent: left / lost his place
    assert not bool(p.known2.iloc[0])                                   # 2021 has not happened


@pytest.fixture(scope="module")
def fitted():
    out = _world()
    pairs = build_pairs(out, last_season=2022)
    return Outlook(n_estimators=40).fit(pairs), pairs[pairs.season == 2020].reset_index(drop=True)


def test_predictions_are_ordered_bounded_and_widen_with_the_horizon(fitted):
    model, targets = fitted
    q = model.predict(targets)
    assert q.shape == (len(targets), len(HORIZONS), len(QUANTILES))
    assert (np.diff(q, axis=2) >= 0).all() and q.min() >= 0 and q.max() <= 100
    width = q[:, :, 2] - q[:, :, 0]
    assert width[:, 2].mean() > width[:, 0].mean()                      # more uncertainty three seasons out than one


def test_a_better_player_is_forecast_higher_and_less_likely_to_vanish(fitted):
    model, targets = fitted
    q, p = model.predict(targets), model.predict_observed(targets)
    hi, lo = targets.composite >= targets.composite.quantile(0.8), targets.composite <= targets.composite.quantile(0.2)
    assert q[hi.to_numpy(), 1, 1].mean() > q[lo.to_numpy(), 1, 1].mean() + 10
    assert p[hi.to_numpy(), 1].mean() > p[lo.to_numpy(), 1].mean()
    assert ((p >= 0) & (p <= 1)).all() and p[:, 2].mean() < p[:, 0].mean()   # survival falls with the horizon


def test_baselines_have_the_same_shape_and_the_shrinkage_baseline_regresses_to_the_mean(fitted):
    model, targets = fitted
    b = model.predict_baselines(targets)
    assert set(b) == {"persistence", "shrinkage"} and b["shrinkage"].shape == model.predict(targets).shape
    extreme = (targets.composite >= targets.composite.quantile(0.95)).to_numpy()
    assert b["shrinkage"][extreme, 1, 1].mean() < targets.composite[extreme].mean()      # high levels are pulled back down


def test_too_little_training_data_is_an_error_not_a_silent_fit():
    out = _world(n=20)
    with pytest.raises(ValueError, match="too few"):
        Outlook(n_estimators=10).fit(build_pairs(out, last_season=2022))


def test_pinball_matches_the_definition():
    y = np.array([10.0, 10.0])
    q = np.array([[5.0, 10.0, 20.0], [15.0, 10.0, 12.0]])
    # row 0: tau.1*(5)=0.5, tau.5*0=0, tau.9: (0.9-1)*(10-20)=1.0 -> mean 0.5 ; row 1: (0.1-1)*(10-15)=4.5, 0, (0.9-1)*(10-12)=0.2 -> mean 1.5667
    assert pinball(y, q) == pytest.approx([0.5, (4.5 + 0.0 + 0.2) / 3])
