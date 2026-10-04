import numpy as np
import pandas as pd

from ml import recruit


def _cands():
    rows = [
        dict(player_id=1, player_name="Creator", team="Other FC", league="EPL", position_group="WING_AM", age=24.0, minutes=2000,
             xa_pct_global=96, key_passes_pct_global=94, xg_chain_pct_global=92, value_now=20e6),
        dict(player_id=2, player_name="Weak", team="Other FC", league="EPL", position_group="MID", age=26.0, minutes=2000,
             xa_pct_global=30, key_passes_pct_global=40, xg_chain_pct_global=50, value_now=5e6),
        dict(player_id=3, player_name="Own player", team="Home FC", league="EPL", position_group="MID", age=26.0, minutes=2000,
             xa_pct_global=95, key_passes_pct_global=95, xg_chain_pct_global=95, value_now=50e6),
        dict(player_id=4, player_name="Wrong position", team="Other FC", league="EPL", position_group="DEF", age=25.0, minutes=2000,
             xa_pct_global=99, key_passes_pct_global=99, xg_chain_pct_global=99, value_now=10e6),
        dict(player_id=5, player_name="Missing metric", team="Other FC", league="EPL", position_group="FWD", age=25.0, minutes=2000,
             xa_pct_global=99, key_passes_pct_global=np.nan, xg_chain_pct_global=99, value_now=10e6),
        dict(player_id=6, player_name="Mover", team="Home FC,Other FC", league="EPL", position_group="FWD", age=27.0, minutes=2000,
             xa_pct_global=88, key_passes_pct_global=88, xg_chain_pct_global=88, value_now=15e6),
        dict(player_id=7, player_name="Expensive", team="Other FC", league="EPL", position_group="FWD", age=27.0, minutes=2000,
             xa_pct_global=88, key_passes_pct_global=88, xg_chain_pct_global=88, value_now=90e6),
    ]
    return pd.DataFrame(rows)


def test_shortlist_ranks_by_gap_metrics_within_suitable_positions_and_excludes_own_players():
    s = recruit.shortlist(_cands(), "open_play_xg", team="Home FC")
    assert s.player_name.tolist()[0] == "Creator"
    names = set(s.player_name)
    assert "Own player" not in names and "Mover" not in names      # includes a mid-season mover who played for the team
    assert "Weak" not in names                                      # below the strength bar for this gap
    assert "Wrong position" not in names                            # defenders do not address chance creation
    assert "Missing metric" not in names                            # unknown is not treated as average
    assert s.fit.is_monotonic_decreasing


def test_budget_and_age_filters_and_unmapped_gaps():
    s = recruit.shortlist(_cands(), "open_play_xg", team="Home FC", max_value_eur=30e6)
    assert "Expensive" not in set(s.player_name) and "Creator" in set(s.player_name)
    assert recruit.shortlist(_cands(), "open_play_xg", team="Home FC", max_age=25).player_name.tolist() == ["Creator"]
    assert recruit.shortlist(_cands(), "set_piece_xga", team="Home FC").empty and "set_piece_xga" in recruit.NOTES


def test_age_note_uses_the_position_plateau():
    assert recruit.age_note("FWD", 20) == "before the usual output plateau"
    assert recruit.age_note("FWD", 27) == "inside the plateau"
    assert recruit.age_note("DEF", 30) == "past the plateau"


def test_candidates_adds_an_xg_per_shot_percentile_within_position():
    out = pd.DataFrame([
        dict(player_id=i, player_name=f"P{i}", season=2020, minutes=2000, age=24.0, position_group="FWD", team="T", league="EPL",
             npxg_p90=0.2 + 0.1 * i, shots_p90=2.0)           # shot volume constant, quality rises with i
        for i in range(5)
    ] + [dict(player_id=9, player_name="Rare shooter", season=2020, minutes=2000, age=24.0, position_group="FWD", team="T",
              league="EPL", npxg_p90=0.2, shots_p90=0.2)])
    c = recruit.candidates(out, 2020).set_index("player_id")
    assert c.loc[4, "xg_per_shot_pct"] > c.loc[0, "xg_per_shot_pct"]
    assert np.isnan(c.loc[9, "xg_per_shot_pct"])                  # too few shots to judge quality
