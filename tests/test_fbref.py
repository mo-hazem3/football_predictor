import pandas as pd

from data_pipeline import db
from data_pipeline.link_fbref_tm import drop_conflicts, minutes_agreement
from data_pipeline.sources.fbref import KEEPER_COLS, OUTFIELD_COLS, keeper_frame, outfield_frame, season_label


def _frame(cols, rows):
    idx = pd.MultiIndex.from_tuples([r[0] for r in rows], names=["league", "season", "team", "player"])
    return pd.DataFrame([r[1] for r in rows], index=idx, columns=pd.MultiIndex.from_tuples(cols))


STD_COLS = [("nation", ""), ("pos", ""), ("age", ""), ("born", ""), ("Playing Time", "MP"), ("Playing Time", "Starts"),
            ("Playing Time", "Min"), ("Performance", "Gls"), ("Performance", "Ast"), ("Performance", "PK"),
            ("Performance", "PKatt"), ("Performance", "CrdY"), ("Performance", "CrdR")]
MISC_COLS = [("nation", ""), ("Performance", "Fls"), ("Performance", "Fld"), ("Performance", "Off"),
             ("Performance", "Crs"), ("Performance", "Int"), ("Performance", "TklW")]


def test_season_label():
    assert season_label(2023) == "2023-2024"


def test_outfield_frame_merges_misc_and_drops_goalkeepers():
    key = lambda team, player: ("GER-Bundesliga", "2324", team, player)
    standard = _frame(STD_COLS, [
        (key("Augsburg", "Arne Engels"), ["BEL", "MF,DF", 19, 2003, 32, 13, 1405, 3, 2, 0, 0, 1, 1]),
        (key("Augsburg", "Finn Dahmen"), ["GER", "GK", 25, 1998, 31, 31, 2790, 0, 0, 0, 0, 0, 0]),
    ])
    misc = _frame(MISC_COLS, [(key("Augsburg", "Arne Engels"), ["BEL", 24, 15, 1, 82, 14, 21])])
    out = outfield_frame(standard, misc, "Bundesliga", 2023)
    assert list(out.columns) == OUTFIELD_COLS and len(out) == 1
    r = out.iloc[0]
    assert r.player_name == "Arne Engels" and r.minutes == 1405 and r.tackles_won == 21 and r.interceptions == 14
    assert r.league == "Bundesliga" and r.season == 2023


def test_keeper_frame_columns():
    cols = [("nation", ""), ("age", ""), ("born", ""), ("Playing Time", "Min"), ("Performance", "GA"),
            ("Performance", "SoTA"), ("Performance", "Saves"), ("Performance", "CS"), ("Penalty Kicks", "PKA")]
    k = _frame(cols, [(("GER-Bundesliga", "2324", "Augsburg", "Finn Dahmen"), ["GER", 25, 1998, 2790, 52, 160, 108, 3, 7])])
    out = keeper_frame(k, "Bundesliga", 2023)
    assert list(out.columns) == KEEPER_COLS
    assert out.iloc[0].saves == 108 and out.iloc[0].pk_allowed == 7 and pd.isna(out.iloc[0].wins)


def test_drop_conflicts_and_minutes_agreement(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    conn.executemany("INSERT INTO understat_player_seasons (understat_player_id, player_name, league, season, team, minutes) VALUES (?,?,?,?,?,?)",
                     [(1, "A", "EPL", 2020, "X", 2000), (2, "B", "EPL", 2020, "X", 2000), (3, "C", "EPL", 2020, "X", 1000)])
    conn.executemany("INSERT INTO understat_tm_links VALUES (?,?,?,?,?,?)",
                     [(1, 11, "EPL", 2020, 95, "name"), (2, 22, "EPL", 2020, 95, "name"), (3, 33, "EPL", 2020, 95, "name")])
    conn.executemany("INSERT INTO fbref_player_seasons (league, season, team, player_name, born, minutes) VALUES (?,?,?,?,?,?)",
                     [("EPL", 2020, "X", "A", 1999, 2010), ("EPL", 2020, "X", "B", 1999, 900), ("EPL", 2020, "X", "C", 0, 1010)])
    conn.executemany("INSERT INTO fbref_tm_links VALUES (?,?,?,?,?,?,?)",
                     [("EPL", 2020, "A", 1999, 11, 95, "name"),   # minutes agree
                      ("EPL", 2020, "B", 1999, 22, 95, "name"),   # minutes disagree -> suspicious link
                      ("EPL", 2020, "C", 0, 33, 95, "name")])
    assert minutes_agreement(conn) == (2, 3)

    conn.executemany("INSERT INTO fbref_tm_links VALUES (?,?,?,?,?,?,?)", [("EPL", 2021, "A", 1999, 99, 90, "name")])
    assert drop_conflicts(conn) == 2   # 'A' (1999) points at tm 11 and tm 99
