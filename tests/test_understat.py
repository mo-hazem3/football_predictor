from data_pipeline.sources.understat import to_frame

SAMPLE = [{
    "id": "8260", "player_name": "Erling Haaland", "games": "31", "time": "2581", "goals": "27",
    "xG": "31.65", "assists": "5", "xA": "4.75", "shots": "122", "key_passes": "29",
    "yellow_cards": "1", "red_cards": "0", "position": "F S", "team_title": "Manchester City",
    "npg": "20", "npxG": "25.56", "xGChain": "30.19", "xGBuildup": "3.12",
}]


def test_to_frame_types_and_names():
    df = to_frame(SAMPLE, "EPL", 2023)
    r = df.iloc[0]
    assert r["understat_player_id"] == 8260 and r["minutes"] == 2581
    assert r["xg"] == 31.65 and r["xg_chain"] == 30.19 and r["xg_buildup"] == 3.12
    assert r["league"] == "EPL" and r["season"] == 2023


def test_to_frame_unescapes_html_entities():
    row = {**SAMPLE[0], "player_name": "Nathan N&#039;Goumou Minpol", "team_title": "Borussia M.Gladbach"}
    assert to_frame([row], "Bundesliga", 2023).iloc[0]["player_name"] == "Nathan N'Goumou Minpol"
