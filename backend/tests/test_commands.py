import importlib
import sqlite3
from pathlib import Path

import pytest
from django.core.management import call_command, get_commands

from api import services

WRAPPERS = {
    "ingest_statsbomb": "data_pipeline.ingest_statsbomb", "ingest_understat": "data_pipeline.ingest_understat",
    "ingest_understat_teams": "data_pipeline.ingest_understat_teams", "ingest_transfermarkt": "data_pipeline.ingest_transfermarkt",
    "ingest_fbref": "data_pipeline.ingest_fbref", "link_understat_tm": "data_pipeline.link_understat_tm",
    "link_fbref_tm": "data_pipeline.link_fbref_tm", "build_features": "features.build", "run_backtest": "ml.backtest",
    "evaluate_value_lens": "ml.evaluate_value_lens",
}


@pytest.mark.parametrize("name,module", sorted(WRAPPERS.items()))
def test_every_wrapper_command_is_registered_and_points_at_a_real_cli(name, module):
    assert name in get_commands()
    cmd = importlib.import_module(f"api.management.commands.{name}").Command()
    assert cmd.module == module and callable(importlib.import_module(module).main)


def test_wrapper_hands_the_raw_command_line_to_the_pipeline_cli(monkeypatch):
    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr("data_pipeline.ingest_understat.main", fake_main)
    cmd = importlib.import_module("api.management.commands.ingest_understat").Command()
    with pytest.raises(SystemExit) as exc:
        cmd.run_from_argv(["manage.py", "ingest_understat", "--leagues", "EPL", "--seasons", "2020", "2021"])
    assert seen["argv"] == ["--leagues", "EPL", "--seasons", "2020", "2021"] and exc.value.code == 0


def test_wrapper_propagates_a_failing_exit_code(monkeypatch):
    monkeypatch.setattr("data_pipeline.ingest_understat.main", lambda argv: 3)
    with pytest.raises(SystemExit) as exc:
        importlib.import_module("api.management.commands.ingest_understat").Command().run_from_argv(["manage.py", "x"])
    assert exc.value.code == 3


# ---------------------------------------------------------------- forecast cache
@pytest.fixture
def pipeline_file(tmp_path, settings, world):
    """A real SQLite pipeline database holding the synthetic world."""
    features, squads, matches, style = world
    db = tmp_path / "football.sqlite"
    conn = sqlite3.connect(db)
    features.to_sql("player_season_features", conn, index=False)
    squads.to_sql("transfermarkt_squads", conn, index=False)
    matches.to_sql("team_matches", conn, index=False)
    style.to_sql("team_style", conn, index=False)
    conn.execute("CREATE TABLE transfermarkt_market_values (tm_player_id INTEGER, date TEXT, value_eur INTEGER)")
    conn.commit()
    conn.close()
    settings.PIPELINE_DB_PATH, settings.FORECAST_CACHE_PATH, settings.FORECAST_BOOTSTRAPS = db, tmp_path / "forecaster.pkl", 3
    services.set_service(None)
    yield db
    services.set_service(None)


def test_build_forecast_cache_writes_a_pickle_that_get_service_reuses(pipeline_file, settings, monkeypatch):
    call_command("build_forecast_cache", bootstraps=3, output=str(settings.FORECAST_CACHE_PATH))
    assert Path(settings.FORECAST_CACHE_PATH).exists()

    def must_not_rebuild(*args, **kwargs):
        pytest.fail("rebuilt instead of loading the pickle")

    monkeypatch.setattr(services, "build_from_database", must_not_rebuild)
    svc = services.get_service()
    assert len(svc.index) > 100 and svc.teams is not None and svc.aging_curves is not None and svc.value_table is not None


def test_cache_survives_writes_to_tables_the_service_does_not_read(pipeline_file, settings):
    """Regression: a long scrape appending value history kept invalidating a whole-file mtime check."""
    call_command("build_forecast_cache", bootstraps=3, output=str(settings.FORECAST_CACHE_PATH))
    conn = sqlite3.connect(pipeline_file)
    conn.execute("INSERT INTO transfermarkt_market_values VALUES (1, '2024-01-01', 5000000)")
    conn.commit()
    conn.close()
    assert services.read_cache(Path(settings.FORECAST_CACHE_PATH), pipeline_file, 3) is not None


def test_cache_is_invalidated_when_the_data_it_was_built_from_changes(pipeline_file, settings):
    call_command("build_forecast_cache", bootstraps=3, output=str(settings.FORECAST_CACHE_PATH))
    cache = Path(settings.FORECAST_CACHE_PATH)
    conn = sqlite3.connect(pipeline_file)
    conn.execute("UPDATE player_season_features SET minutes = minutes + 1 WHERE rowid = 1")
    conn.commit()
    conn.close()
    assert services.read_cache(cache, pipeline_file, 3) is None                    # features changed
    call_command("build_forecast_cache", bootstraps=3, output=str(cache))
    assert services.read_cache(cache, pipeline_file, 3) is not None
    assert services.read_cache(cache, pipeline_file, 50) is None                   # built for a different bootstrap count


def test_unusable_caches_are_ignored_not_fatal(pipeline_file, tmp_path):
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(b"not a pickle")
    assert services.read_cache(bad, pipeline_file, 3) is None
    assert services.read_cache(tmp_path / "missing.pkl", pipeline_file, 3) is None
    assert services.read_cache(bad, tmp_path / "no.sqlite", 3) is None


def test_fingerprint_tolerates_a_database_without_the_team_tables(tmp_path, world):
    features, squads, *_ = world
    db = tmp_path / "x.sqlite"
    conn = sqlite3.connect(db)
    features.to_sql("player_season_features", conn, index=False)
    squads.to_sql("transfermarkt_squads", conn, index=False)
    conn.close()
    fp = services.data_fingerprint(db)
    assert fp["team_matches"] is None and fp["player_season_features"][0] == len(features)
