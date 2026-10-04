import numpy as np
import pandas as pd
import pytest

from ml.gap_analysis import gap_analysis
from ml.similarity import ATTACK, DEFENCE, SimilarityEngine


def _row(pid, season, group="FWD", age=24.0, minutes=2000, league="EPL", **over):
    r = {"player_id": pid, "player_name": f"P{pid}", "season": season, "league": league, "team": "T",
         "position_group": group, "age": age, "minutes": minutes, "log_league_factor": 0.0, "league_jump": 0.0}
    r.update({c: 0.3 for c in ATTACK + DEFENCE})
    r.update(over)
    return r


def _pool(n=60, seed=0):
    """A background of random forwards so z-scoring has variance."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        rows.append(_row(1000 + i, 2020, age=24 + rng.uniform(-1, 1), **{c: abs(rng.normal(0.3, 0.15)) for c in ATTACK + DEFENCE}))
    return rows


def test_nearest_comp_is_the_most_similar_profile_in_same_group_and_age_window():
    twin = {c: 0.9 for c in ATTACK}
    rows = _pool() + [
        _row(1, 2021, **twin),                                   # target: elite attacker
        _row(2, 2021, **{c: 0.88 for c in ATTACK}),              # near twin
        _row(3, 2021, **{c: 0.5 for c in ATTACK}),               # middling
        _row(4, 2021, group="DEF", **twin),                      # same stats, other position: excluded
        _row(5, 2021, age=31.0, **twin),                         # same stats, outside age window: excluded
        _row(6, 2021, minutes=300, **twin),                      # too few minutes to be a comp: excluded
    ]
    eng = SimilarityEngine(pd.DataFrame(rows))
    comps = eng.comps(1, 2021, k=3)
    assert comps.player_id.iloc[0] == 2
    assert not {4, 5, 6, 1} & set(comps.player_id)


def test_unique_players_keeps_only_the_closest_season_of_each_player():
    rows = _pool() + [_row(1, 2021, **{c: 0.9 for c in ATTACK}),
                      _row(2, 2021, **{c: 0.89 for c in ATTACK}), _row(2, 2022, age=25.0, **{c: 0.7 for c in ATTACK})]
    eng = SimilarityEngine(pd.DataFrame(rows))
    assert eng.comps(1, 2021, k=5).player_id.tolist().count(2) == 1
    assert eng.comps(1, 2021, k=5, unique_players=False).player_id.tolist().count(2) == 2


def test_query_uses_only_features_the_target_has():
    """Seasons without FBref defensive stats are compared on attacking stats only, against candidates that have them."""
    no_def = {c: np.nan for c in DEFENCE}
    rows = _pool() + [_row(1, 2015, **no_def, **{c: 0.9 for c in ATTACK}), _row(2, 2021, **{c: 0.88 for c in ATTACK})]
    eng = SimilarityEngine(pd.DataFrame(rows))
    comps = eng.comps(1, 2015, k=3)
    assert set(comps.attrs["features_used"]) == set(ATTACK)
    assert 2 in set(comps.player_id)


def test_missing_target_raises():
    with pytest.raises(KeyError):
        SimilarityEngine(pd.DataFrame(_pool())).comps(999, 2020)


def test_gap_analysis_flags_weaknesses_and_orders_weakest_first():
    target = pd.Series({"position_group": "FWD", "npxg_pct_global": 95.0, "xa_pct_global": 40.0, "fouls_pct_league": 10.0})
    comps = pd.DataFrame({"npxg_pct_global": [90, 92, 94], "xa_pct_global": [70, 75, 80], "fouls_pct_league": [60, 70, 80]})
    g = gap_analysis(target, comps).set_index("metric")
    assert list(g.index)[0] == "fouls"                       # biggest negative gap first ...
    assert g.loc["xa", "flag"] == "weakness" and g.loc["npxg", "flag"] == ""
    assert g.loc["fouls", "flag"] == ""                      # ... but fouls committed is never a 'weakness'
    assert g.loc["xa", "gap"] == pytest.approx(40 - 75)


def test_pca_axes_are_oriented_for_readability():
    pytest.importorskip("matplotlib")
    pytest.importorskip("adjustText")
    from ml.visualize import pca_coords

    eng = SimilarityEngine(pd.DataFrame(_pool(n=120, seed=3)), use_context=False)
    x, xy, (explained, loadings) = pca_coords(eng, "FWD")
    assert xy.shape == (len(x), 2) and 0 < explained.sum() <= 1
    assert loadings[0, :len(ATTACK)].sum() >= 0   # more attacking output points right
    assert loadings[1, 1] >= 0                    # chance-creators (xA) point up
