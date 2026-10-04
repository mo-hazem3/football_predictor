from data_pipeline import db
from data_pipeline.ingest_understat_teams import _insert
from data_pipeline.sources.understat_teams import STYLE_GROUPS, match_rows, style_rows, team_titles

PAYLOAD = {"teams": {"83": {"id": "83", "title": "Arsenal", "history": [
    {"h_a": "h", "xG": 0.71, "xGA": 1.07, "npxG": 0.71, "npxGA": 1.07, "ppda": {"att": 176, "def": 29},
     "ppda_allowed": {"att": 226, "def": 27}, "deep": 3, "deep_allowed": 6, "scored": 1, "missed": 2, "xpts": 1.02,
     "result": "l", "date": "2023-08-11 19:30:00", "pts": 0},
    {"h_a": "a", "xG": 2.0, "xGA": 0.5, "npxG": 1.3, "npxGA": 0.5, "ppda": {"att": 100, "def": 10},
     "ppda_allowed": {"att": 90, "def": 15}, "deep": 9, "deep_allowed": 1, "scored": 3, "missed": 0, "xpts": 2.6,
     "result": "w", "date": "2023-08-19 15:00:00", "pts": 3}]}}}

STATS = {
    "situation": {"OpenPlay": {"shots": 502, "goals": 62, "xG": 65.2, "against": {"shots": 249, "goals": 20, "xG": 23.3}}},
    "formation": {"4-3-3": {"stat": "4-3-3", "time": 3598, "shots": 645, "goals": 91, "xG": 90.5,
                            "against": {"shots": 311, "goals": 29, "xG": 31.5}}},
    "attackSpeed": {"Fast": {"shots": 22, "goals": 8, "xG": 5.8, "against": {"shots": 9, "goals": 2, "xG": 1.9}}},
}


def test_match_rows_flatten_the_per_match_history():
    rows = match_rows(PAYLOAD, "EPL", 2023)
    assert len(rows) == 2 and team_titles(PAYLOAD) == ["Arsenal"]
    away = rows[1]
    assert away["home"] == 0 and away["ppda_att"] == 100 and away["ppda_def"] == 10 and away["deep"] == 9 and away["pts"] == 3
    assert rows[0]["team"] == "Arsenal" and rows[0]["league"] == "EPL" and rows[0]["season"] == 2023


def test_style_rows_keep_for_and_against_and_minutes_where_given():
    rows = {(r["grp"], r["stat"]): r for r in style_rows(STATS, "EPL", 2023, "Arsenal")}
    assert set(g for g, _ in rows) <= set(STYLE_GROUPS) and len(rows) == 3
    f = rows[("attackSpeed", "Fast")]
    assert f["shots"] == 22 and f["against_xg"] == 1.9 and f["time"] is None
    assert rows[("formation", "4-3-3")]["time"] == 3598


def test_rows_round_trip_through_the_schema_and_are_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    for _ in range(2):  # re-running an ingest must not duplicate rows
        _insert(conn, "team_matches", match_rows(PAYLOAD, "EPL", 2023))
        _insert(conn, "team_style", style_rows(STATS, "EPL", 2023, "Arsenal"))
    assert conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM team_style").fetchone()[0] == 3


def test_player_rows_are_club_level_and_typed():
    from data_pipeline.sources.understat_teams import player_rows

    data = {"players": [{"id": "7322", "player_name": "Bukayo Saka", "games": "35", "time": "2990", "goals": "16",
                         "xG": "16.8", "assists": "8", "xA": "11.3", "shots": "107", "key_passes": "89", "position": "F",
                         "npxG": "12.2", "xGChain": "30.4", "xGBuildup": "13.2"}]}
    r = player_rows(data, "EPL", 2023, "Arsenal")[0]
    assert r["understat_player_id"] == 7322 and r["minutes"] == 2990 and r["team"] == "Arsenal" and r["xg_buildup"] == 13.2
