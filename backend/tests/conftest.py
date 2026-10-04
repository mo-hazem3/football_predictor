import pytest
from django.db import connections

import factories
from api import services
from data_pipeline.db import SCHEMA
from ml.forecast import Forecaster

LEAGUE_STRENGTH_DDL = """CREATE TABLE IF NOT EXISTS league_strength (league TEXT, factor REAL, ci_low REAL, ci_high REAL, n_obs INTEGER, n_movers INTEGER);"""


@pytest.fixture(scope="session")
def world():
    features = factories.make_features()
    matches, style = factories.make_team_tables()
    return features, factories.make_squads(features), matches, style


@pytest.fixture(scope="session")
def built_service(world):
    """The real forecaster, value table, aging curves and team profiles, fitted once on the synthetic world."""
    features, squads, matches, style = world
    forecaster = Forecaster(features, squads, horizon=3, as_of=2019, n_boot=3, calibration=None)
    return services.build_service(forecaster, matches, style, aging_boot=3)


@pytest.fixture
def service(built_service):
    services.set_service(built_service)
    yield built_service
    services.set_service(None)


@pytest.fixture
def pipeline_tables():
    """The pipeline's tables in the in-memory `pipeline` test database (Django does not create unmanaged models)."""
    raw = connections["pipeline"].connection
    raw.executescript(SCHEMA)               # executescript commits, so the tables outlive the test's transaction:
    raw.executescript(LEAGUE_STRENGTH_DDL)  # create-if-missing and start every test from empty tables
    for table in ("league_strength", "transfermarkt_squads"):
        raw.execute(f"DELETE FROM {table}")
    raw.executemany("INSERT INTO league_strength VALUES (?,?,?,?,?,?)",
                    [("EPL", 0.85, 0.82, 0.89, 617, 903), ("Ligue_1", 1.09, 1.04, 1.14, 526, 903)])
    raw.execute("INSERT INTO transfermarkt_squads VALUES (1004, 2019, 'EPL', 1, 'Alpha FC', 'Player 4 Test', 'Centre-Forward', "
                "'2001-05-17', 'Egypt', 'Egypt|France', 181, 'right', 20000000)")
    return raw


def pick(service, group, season=None):
    """(player_id, season) of a ranked player in a position group, preferring the latest season."""
    d = service.engine.d
    d = d[d.position_group == group]
    season = season or int(d.season.max())
    return int(d[d.season == season].player_id.iloc[0]), season
