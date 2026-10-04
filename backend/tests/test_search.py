import pandas as pd

from api.search import PlayerIndex, fold


def _rows():
    return pd.DataFrame([
        dict(player_id=1, player_name="Álex Grimaldo", season=2023, league="Bundesliga", team="Bayer Leverkusen", position_group="DEF", age=28.0, minutes=2800),
        dict(player_id=1, player_name="Álex Grimaldo", season=2022, league="La_liga", team="Benfica", position_group="DEF", age=27.0, minutes=2000),
        dict(player_id=2, player_name="Alejandro Garnacho", season=2023, league="EPL", team="Manchester United", position_group="WING_AM", age=19.0, minutes=1500),
        dict(player_id=3, player_name="Jamal Musiala", season=2023, league="Bundesliga", team="Bayern Munich", position_group="WING_AM", age=20.0, minutes=1800),
        dict(player_id=4, player_name="Musa Al-Taamari", season=2023, league="Ligue_1", team="Rennes", position_group="WING_AM", age=26.0, minutes=3000),
        dict(player_id=5, player_name="Rodri", season=2023, league="EPL", team="Manchester City", position_group="MID", age=27.0, minutes=3000),
        dict(player_id=6, player_name="Rodrigo Bentancur", season=2023, league="EPL", team="Tottenham", position_group="MID", age=26.0, minutes=1000),
    ])


def test_fold_strips_accents_case_and_punctuation():
    assert fold("Álex Grimaldo") == "alex grimaldo" and fold("N'Golo  Kanté") == "n golo kante" and fold("") == "" and fold(None) == ""


def test_search_returns_one_row_per_player_with_the_latest_season():
    idx = PlayerIndex(_rows())
    hit = idx.search("grimaldo")
    assert len(hit) == 1 and hit.iloc[0].season == 2023 and hit.iloc[0].team == "Bayer Leverkusen"


def test_search_requires_every_token_and_ignores_accents():
    idx = PlayerIndex(_rows())
    assert idx.search("alex grim").player_name.tolist() == ["Álex Grimaldo"]
    assert idx.search("grimaldo garnacho").empty and idx.search("   ").empty


def test_exact_and_prefix_matches_outrank_substrings_and_ties_go_to_career_minutes():
    idx = PlayerIndex(_rows())
    assert idx.search("rodri").player_name.tolist() == ["Rodri", "Rodrigo Bentancur"]          # exact first
    assert idx.search("mus").player_name.tolist()[:2] == ["Musa Al-Taamari", "Jamal Musiala"]  # both prefixes: more minutes first
    assert len(idx.search("a", limit=2)) == 2
