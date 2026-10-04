import numpy as np
import pandas as pd

from features import build, league_strength
from features.positions import position_group


def test_position_group_prefers_transfermarkt_then_understat():
    assert position_group("Left Winger", "F M S") == "WING_AM"
    assert position_group("Centre-Back", None) == "DEF"
    assert position_group(None, "S D") == "DEF"      # 'S' (substitute) is skipped
    assert position_group(None, "S") is None
    assert position_group("Second Striker", "M") == "FWD"


def _frame(**cols):
    base = dict(player_id=1, league="EPL", season=2023, minutes=900, tm_position="Centre-Forward",
                understat_position="F S", birth_date="2000-01-01", tm_player_id=1)
    base.update({c: 0.0 for c in build.COUNTS})
    base.update(cols)
    return pd.DataFrame([base])


def test_base_features_age_and_per90():
    df = build.add_base_features(_frame(npxg=9.0, season=2023))
    assert df.age.iloc[0] == (pd.Timestamp("2024-01-01") - pd.Timestamp("2000-01-01")).days / 365.25
    assert df.npxg_p90.iloc[0] == 0.9 and df.position_group.iloc[0] == "FWD" and df.linked.iloc[0] == 1


def test_percentiles_rank_only_eligible_players_within_group():
    rows = [dict(player_id=i, league="EPL", season=2023, position_group="FWD", minutes=m,
                 league_factor=1.0, **{f"{c}_p90": float(i) for c in build.PERCENTILED},
                 **{f"{c}_p90_adj": float(i) for c in build.PERCENTILED})
            for i, m in [(1, 900), (2, 900), (3, 900), (4, 100)]]
    out = build.add_percentiles(pd.DataFrame(rows), min_minutes=450)
    assert np.allclose(out.npxg_pct_league.tolist()[:3], [100 / 3, 200 / 3, 100.0])
    assert np.isnan(out.npxg_pct_league.iloc[3])  # too few minutes: not ranked


def test_league_strength_recovers_known_effect_from_movers():
    rng = np.random.default_rng(1)
    true = {"A": np.log(0.8), "B": np.log(1.25)}  # B is 'easier': 1.25/0.8 = 1.56x output
    rows = []
    for pid in range(400):
        skill = rng.normal(np.log(0.5), 0.4)
        for season, lg in [(2020, "A"), (2021, "B")] if pid % 2 else [(2020, "B"), (2021, "A")]:
            rows.append(dict(player_id=pid, league=lg, season=season, minutes=1500, age=24.0 + (season - 2020),
                             position_group="MID", npxg_p90=np.exp(skill + true[lg] + rng.normal(0, 0.1)) * 0.6,
                             xa_p90=np.exp(skill + true[lg] + rng.normal(0, 0.1)) * 0.4))
    obs = league_strength.mover_observations(pd.DataFrame(rows))
    assert obs.player_id.nunique() == 400
    f = league_strength.estimate(obs, n_boot=40).set_index("league")
    ratio = f.loc["B", "factor"] / f.loc["A", "factor"]
    assert abs(ratio - 1.25 / 0.8) < 0.1
    assert f.loc["B", "ci_low"] <= f.loc["B", "factor"] <= f.loc["B", "ci_high"]


def test_mover_observations_ignores_players_who_never_changed_league():
    df = pd.DataFrame([dict(player_id=1, league="A", season=s, minutes=1000, age=25.0, position_group="MID",
                            npxg_p90=0.2, xa_p90=0.1) for s in (2020, 2021)])
    assert league_strength.mover_observations(df).empty


def test_fbref_features_merge_per90_and_keeper_ratios():
    base = pd.DataFrame([
        dict(tm_player_id=1, league="EPL", season=2023, minutes=1800, position_group="DEF"),
        dict(tm_player_id=2, league="EPL", season=2023, minutes=2700, position_group="GK"),
        dict(tm_player_id=None, league="EPL", season=2023, minutes=900, position_group="MID"),  # unlinked
    ])
    fb = pd.DataFrame([
        dict(tm_player_id=1, league="EPL", season=2023, fb_minutes=1800, tackles_won=40, interceptions=20,
             crosses=10, fouls=15, fouled=5, gk_minutes=None, goals_against=None, shots_on_target_against=None,
             saves=None, clean_sheets=None),
        dict(tm_player_id=2, league="EPL", season=2023, fb_minutes=None, tackles_won=None, interceptions=None,
             crosses=None, fouls=None, fouled=None, gk_minutes=2700, goals_against=30, shots_on_target_against=120,
             saves=90, clean_sheets=10),
    ])
    out = build.add_fbref_features(base, fb)
    assert out.tackles_won_p90.iloc[0] == 2.0 and out.interceptions_p90.iloc[0] == 1.0
    assert out.save_pct.iloc[1] == 0.75 and out.gk_sota_p90.iloc[1] == 4.0
    assert out.tackles_won_p90.iloc[2] != out.tackles_won_p90.iloc[2]  # unlinked player: NaN, not matched to anything


def test_group_percentiles_respect_position_filter_and_minutes():
    df = pd.DataFrame([
        dict(league="EPL", season=2023, position_group="DEF", minutes=900, tackles_won_p90=v) for v in (1.0, 2.0, 3.0)
    ] + [dict(league="EPL", season=2023, position_group="GK", minutes=900, tackles_won_p90=9.0),
         dict(league="EPL", season=2023, position_group="DEF", minutes=100, tackles_won_p90=9.0)])
    out = build.add_group_percentiles(df, ["tackles_won_p90"], 450, lambda d: d.position_group != "GK")
    assert np.allclose(out.tackles_won_pct_league.iloc[:3], [100 / 3, 200 / 3, 100.0])
    assert out.tackles_won_pct_league.iloc[3:].isna().all()  # goalkeeper filtered out, low-minutes player unranked


def test_career_context_league_jump_uses_previous_season_and_main_league():
    rows = [
        dict(player_id=1, season=2020, league="EPL", league_factor=0.85, minutes=2000),
        dict(player_id=1, season=2021, league="Ligue_1", league_factor=1.10, minutes=2500),   # moved to easier league
        dict(player_id=1, season=2023, league="Ligue_1", league_factor=1.10, minutes=2500),   # gap 2: still same league
        dict(player_id=2, season=2020, league="EPL", league_factor=0.85, minutes=100),
        dict(player_id=2, season=2020, league="Ligue_1", league_factor=1.10, minutes=900),     # two leagues: main = Ligue_1
        dict(player_id=2, season=2021, league="EPL", league_factor=0.85, minutes=2000),
        dict(player_id=3, season=2022, league="EPL", league_factor=0.85, minutes=2000),        # no history
        dict(player_id=3, season=2025, league="EPL", league_factor=0.85, minutes=2000),        # gap 3: ignored
    ]
    out = build.add_career_context(pd.DataFrame(rows)).league_jump.round(4).tolist()
    assert out == [0.0, round(np.log(1.10 / 0.85), 4), 0.0, 0.0, 0.0, round(np.log(0.85 / 1.10), 4), 0.0, 0.0]
