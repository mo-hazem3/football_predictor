from data_pipeline import db
from data_pipeline.link_understat_tm import drop_conflicts


def test_drop_conflicts_keeps_only_one_to_one_links(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    rows = [
        (1, 100, "EPL", 2020, 95, "name"), (1, 100, "EPL", 2021, 95, "name"),  # consistent across seasons: keep
        (2, 200, "EPL", 2020, 90, "name"), (2, 201, "EPL", 2021, 90, "name"),  # one understat id -> two tm ids
        (3, 300, "EPL", 2020, 90, "name"), (4, 300, "EPL", 2020, 90, "club"),  # two understat ids -> one tm id
    ]
    conn.executemany("INSERT INTO understat_tm_links VALUES (?,?,?,?,?,?)", rows)
    assert drop_conflicts(conn) == 4
    assert {r[0] for r in conn.execute("SELECT understat_player_id FROM understat_tm_links")} == {1}
