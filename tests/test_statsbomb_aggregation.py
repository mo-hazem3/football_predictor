from data_pipeline.sources.statsbomb import aggregate_match, match_minutes


def ev(type_, player=1, team="A", **extra):
    return {"type": {"name": type_}, "player": {"id": player, "name": f"P{player}"}, "team": {"name": team}, **extra}


def test_shots_goals_and_xg():
    evts = [
        ev("Shot", shot={"statsbomb_xg": 0.3, "outcome": {"name": "Goal"}}),
        ev("Shot", shot={"statsbomb_xg": 0.1, "outcome": {"name": "Saved"}}),
    ]
    a = aggregate_match(evts)[1]
    assert (a["shots"], a["goals"]) == (2, 1)
    assert abs(a["xg"] - 0.4) < 1e-9


def test_pass_completion_and_key_pass():
    evts = [
        ev("Pass", **{"pass": {}}),
        ev("Pass", **{"pass": {"outcome": {"name": "Incomplete"}}}),
        ev("Pass", **{"pass": {"shot_assist": True}}),
    ]
    a = aggregate_match(evts)[1]
    assert (a["passes"], a["passes_completed"], a["key_passes"]) == (3, 2, 1)


def test_events_without_player_are_ignored():
    assert aggregate_match([{"type": {"name": "Half Start"}, "team": {"name": "A"}}]) == {}


def test_minutes_for_starter_and_substitute():
    lineup = [{"lineup": [
        {"player_id": 1, "positions": [{"position": "Striker", "from": "00:00", "to": "60:00"}]},
        {"player_id": 2, "positions": [{"position": "Striker", "from": "60:00", "to": None}]},
        {"player_id": 3, "positions": []},
    ]}]
    out = match_minutes(lineup, 95.0)
    assert out[1][0] == 60 and out[2][0] == 35 and 3 not in out
