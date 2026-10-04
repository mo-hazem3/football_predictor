import numpy as np
import pandas as pd
import pytest

from ml.outcomes import add_composite, build_outcomes
from ml.similarity import ATTACK, DEFENCE, SimilarityEngine
from ml.trajectory import class_rates, posterior, project


def _row(pid, season, age=21.0, comp=60.0, minutes=2000, **over):
    r = {"player_id": pid, "player_name": f"P{pid}", "season": season, "league": "EPL", "team": "T", "position_group": "FWD",
         "age": age, "minutes": minutes, "log_league_factor": 0.0, "league_jump": 0.0, "tm_player_id": pid}
    r.update({c: 0.3 for c in ATTACK + DEFENCE})
    r.update({f"{c}_pct_global": comp for c in ["npxg", "xa", "xg_chain"]})
    r.update(over)
    return r


def _world():
    """40 comp players in 2016 (half of them become elite by 2019, half drop out), plus a target in 2020."""
    rows = []
    for i in range(40):
        rows.append(_row(100 + i, 2016, age=21 + (i % 3) * 0.2))
        if i % 2 == 0:
            rows.append(_row(100 + i, 2018, age=23, comp=95))      # inside the 2017-2019 window -> elite
    rows.append(_row(1, 2020))
    return pd.DataFrame(rows)


def test_posterior_is_shrunk_and_sums_to_one():
    counts, base = np.array([0.0, 5.0, 0.0, 0.0]), np.array([0.1, 0.5, 0.3, 0.1])
    mean, lo, hi = posterior(counts, base, prior_strength=10)
    assert mean.sum() == pytest.approx(1.0) and (lo < mean).all() and (mean < hi).all()
    assert mean[0] > 0 and mean[2] > 0          # unseen classes keep some probability
    assert np.allclose(class_rates(pd.Series(["a", "a", "b"]), ["a", "b", "c"]), [2 / 3, 1 / 3, 0])


def test_projection_reads_comp_outcomes_and_respects_the_as_of_date():
    df = add_composite(_world())
    outcomes = build_outcomes(df, {}, horizon=3, last_season=2025)
    eng = SimilarityEngine(df)
    p = project(eng, outcomes, 1, 2020, horizon=3, k=30, as_of=2020)
    assert p.n_comps == 30 and (p.comps.season + 3 <= 2020).all()
    probs = dict(zip(p.classes, p.probs))
    assert probs["elite"] == pytest.approx(0.5, abs=0.12) and probs["out"] == pytest.approx(0.5, abs=0.12)
    assert p.table().probability.sum() == pytest.approx(1.0)


def test_comps_whose_windows_are_unfinished_are_never_used():
    df = add_composite(_world())
    outcomes = build_outcomes(df, {}, horizon=3, last_season=2025)
    eng = SimilarityEngine(df)
    # as of 2018 the 2016 comps' windows (2017-2019) are NOT finished: no usable comps at all
    p = project(eng, outcomes, 1, 2020, horizon=3, k=30, as_of=2018)
    assert p.n_comps == 0 and p.counts.sum() == 0
