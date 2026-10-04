import numpy as np
import pandas as pd

from ml.outcomes import add_composite, build_outcomes, classes_for, value_series


def _row(pid, season, group="FWD", minutes=2000, comp=60.0, tm=None, league="EPL"):
    r = {"player_id": pid, "season": season, "league": league, "position_group": group, "minutes": minutes,
         "tm_player_id": tm}
    r.update({f"{c}_pct_global": comp for c in ["npxg", "xa", "xg_chain", "key_passes", "xg_buildup"]})
    return r


def _out(rows, values=None, horizon=3, last=2025):
    return build_outcomes(add_composite(pd.DataFrame(rows)), values or {}, horizon, last).reset_index(drop=True)


def test_tiers_use_peak_composite_over_the_next_h_seasons_only():
    rows = [_row(1, 2018), _row(1, 2019, comp=40), _row(1, 2020, comp=80), _row(1, 2021, comp=50), _row(1, 2022, comp=99)]
    o = _out(rows)
    assert o.peak_composite[0] == 80 and o.tier[0] == "good"      # window 2019-2021; the 99 in 2022 is outside it
    assert o.peak_composite[1] == 99 and o.tier[1] == "elite"     # window 2020-2022 includes it
    assert o.tier[4] == "out"                                      # 2022 window (2023-2025) is observable and empty


def test_incomplete_windows_are_not_scored_and_empty_windows_are_out():
    rows = [_row(1, 2019), _row(2, 2022), _row(2, 2023, minutes=300)]   # player 2: only 300 min afterwards
    o = _out(rows, last=2025)
    assert o.observable.tolist() == [True, True, False]
    assert o.tier[0] == "out"                       # player 1 never appears again
    assert o.tier[1] == "out"                       # 300 minutes does not qualify
    assert pd.isna(o.tier[2])                       # 2023 + 3 > 2025: never scored


def test_defenders_only_get_retained_or_out():
    rows = [_row(1, 2018, group="DEF"), _row(1, 2019, group="DEF"), _row(2, 2018, group="GK")]
    o = _out(rows)
    # player 1 plays on (retained); his last row and the goalkeeper have no later 900+ minute season (out)
    assert o.tier.tolist() == ["retained", "out", "out"] and classes_for("DEF") == ["out", "retained"]


def test_value_ratio_uses_peak_future_value_and_requires_squad_presence():
    squads = pd.DataFrame([dict(tm_player_id=7, season=s, market_value_eur=v) for s, v in [(2018, 10e6), (2019, 25e6), (2020, 40e6), (2021, 30e6)]])
    values = value_series(squads)
    rows = [_row(1, 2018, tm=7, comp=50)] + [_row(1, s, tm=7) for s in (2019, 2020, 2021)]
    o = _out(rows, values)
    assert o.value_now[0] == 10e6 and o.peak_value[0] == 40e6 and o.value_ratio[0] == 4.0
    gone = _out([_row(2, 2018, tm=8)], value_series(pd.DataFrame([dict(tm_player_id=8, season=2018, market_value_eur=5e6)])))
    assert np.isnan(gone.value_ratio[0])            # not on a top-5 squad afterwards: censored, not zero


def test_horizon_changes_the_window():
    rows = [_row(1, 2018, comp=50), _row(1, 2019, comp=50), _row(1, 2021, comp=95)]
    assert _out(rows, horizon=1).tier[0] == "regular"
    assert _out(rows, horizon=3).tier[0] == "elite"
