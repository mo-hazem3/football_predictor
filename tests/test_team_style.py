import numpy as np
import pandas as pd
import pytest

from features import team_style as ts


def _matches():
    rows = []
    for team, xga, ppda_att in (("A", 0.8, 80), ("B", 1.2, 140), ("C", 1.6, 200), ("D", 1.0, 100)):
        for i in range(2):
            rows.append(dict(league="EPL", season=2020, team=team, match_date=f"2020-09-0{i + 1}", home=i, xg=1.5, xga=xga,
                             npxg=1.4, npxga=xga, ppda_att=ppda_att, ppda_def=10, ppda_allowed_att=100, ppda_allowed_def=10,
                             deep=8 if team == "A" else 4, deep_allowed=3 if team == "A" else 7, scored=2, missed=1, xpts=2.0, pts=3))
    return pd.DataFrame(rows)


def _style(open_xga=None):
    rows = []
    for team in "ABCD":
        xga = {"A": 0.8, "B": 1.2, "C": 1.6, "D": 1.0}[team]
        spec = {("situation", "OpenPlay"): (20, 10.0, 8.0 * xga), ("situation", "FromCorner"): (6, 2.0, 2.0 * xga),
                ("situation", "SetPiece"): (2, 0.5, 0.5 * xga), ("situation", "DirectFreekick"): (2, 0.5, 0.5 * xga),
                ("attackSpeed", "Fast"): (4, 1.0, 1.0 * xga), ("attackSpeed", "Slow"): (10, 4.0, 3.0 * xga),
                ("attackSpeed", "Normal"): (16, 6.0, 5.0 * xga), ("attackSpeed", "Standard"): (0, 0.0, 0.0)}
        for (grp, stat), (shots, xg, xga_) in spec.items():
            rows.append(dict(league="EPL", season=2020, team=team, grp=grp, stat=stat, time=None, shots=shots, goals=0, xg=xg,
                             against_shots=5, against_goals=0, against_xg=xga_))
    return pd.DataFrame(rows)


def test_profiles_are_per_match_and_ppda_is_the_season_ratio():
    p = ts.build_profiles(_matches(), _style()).set_index("team")
    assert p.loc["A", "matches"] == 2
    assert p.loc["A", "ppda"] == pytest.approx(80 / 10) and p.loc["C", "ppda"] == pytest.approx(20)
    assert p.loc["A", "open_play_xg"] == pytest.approx(10.0 / 2)                    # season total / matches
    assert p.loc["A", "set_piece_xg"] == pytest.approx((2.0 + 0.5 + 0.5) / 2)       # corners + set pieces + direct free kicks
    assert p.loc["A", "transition_xg"] == pytest.approx(1.0 / 2)
    assert p.loc["A", "shot_quality"] == pytest.approx(11.0 / 30)                   # xG over shots across attack speeds
    assert p.loc["A", "deep_completions"] == 8.0 and p.loc["A", "deep_allowed"] == 3.0


def test_percentiles_are_oriented_so_higher_is_always_better():
    pr = ts.add_percentiles(ts.build_profiles(_matches(), _style())).set_index("team")
    assert pr.loc["A", "open_play_xga_pct"] == 100 and pr.loc["C", "open_play_xga_pct"] == 25   # concedes least -> best
    assert pr.loc["A", "pressing_pct"] == 100 and pr.loc["C", "pressing_pct"] == 25              # lowest PPDA -> most pressing
    assert pr.loc["A", "deep_completions_pct"] == 100                                            # more is better in attack
    assert pr.loc["A", "deep_allowed_pct"] == 100                                                # fewer conceded is better


def test_gaps_lists_bottom_quartile_dimensions_weakest_first():
    pr = ts.add_percentiles(ts.build_profiles(_matches(), _style())).set_index("team")
    g = ts.gaps(pr.loc["C"], threshold=25)
    assert len(g) and set(g.dimension) <= set(ts.DIMENSIONS) and g.percentile.is_monotonic_increasing
    assert "pressing" in set(g.dimension) and g[g.dimension == "pressing"].value.iloc[0] == pytest.approx(20.0)  # shows PPDA
    assert ts.gaps(pr.loc["A"], threshold=25).empty
