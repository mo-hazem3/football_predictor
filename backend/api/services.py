"""The fitted models behind the API, built once and shared across requests.

`Service` bundles the forecaster (outcomes, similarity engine, learned tier and value models,
calibration) with the player-name index. Building it takes tens of seconds, so:
  * `manage.py build_forecast_cache` pickles it next to the data;
  * `get_service()` loads that pickle when it is still valid for the current pipeline database,
    otherwise builds in-process on first use (guarded by a lock);
  * with PRELOAD_MODELS=1 the load happens at server start instead of on the first request.
The pickle is our own artefact on a local path; it is never read from user input.
"""
from __future__ import annotations

import pickle
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from django.conf import settings

from ml.forecast import Forecaster

from .search import PlayerIndex

CACHE_VERSION = 1


@dataclass
class Service:
    forecaster: Forecaster
    index: PlayerIndex

    @property
    def engine(self):
        return self.forecaster.engine

    @property
    def out(self) -> pd.DataFrame:
        """Every player-season (up to as_of) with features, percentiles and outcomes."""
        return self.forecaster.out

    @property
    def horizon(self) -> int:
        return self.forecaster.horizon

    @property
    def as_of(self) -> int:
        return self.forecaster.as_of

    def latest_season(self, player_id: int) -> int | None:
        """Most recent season in which the player is ranked (enough minutes and a known age)."""
        d = self.engine.d
        s = d[d.player_id == player_id].season
        return int(s.max()) if len(s) else None


def build_service(forecaster: Forecaster) -> Service:
    return Service(forecaster, PlayerIndex(forecaster.out))


def _db_stamp(db_path: Path) -> dict:
    st = db_path.stat()
    return {"mtime": st.st_mtime_ns, "size": st.st_size}


def build_from_database(db_path: Path, n_boot: int) -> Service:
    conn = sqlite3.connect(db_path)
    try:
        features = pd.read_sql("SELECT * FROM player_season_features", conn)
        squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    finally:
        conn.close()
    return build_service(Forecaster(features, squads, n_boot=n_boot))


def write_cache(service: Service, cache_path: Path, db_path: Path, n_boot: int) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"version": CACHE_VERSION, "n_boot": n_boot, **_db_stamp(db_path)}
    tmp = cache_path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump({"meta": meta, "service": service}, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(cache_path)


def read_cache(cache_path: Path, db_path: Path, n_boot: int) -> Service | None:
    """The pickled service if it exists and was built from this exact database file."""
    if not cache_path.exists() or not db_path.exists():
        return None
    try:
        with cache_path.open("rb") as f:
            blob = pickle.load(f)
    except Exception:  # corrupt/incompatible pickle: rebuild rather than fail the request
        return None
    expected = {"version": CACHE_VERSION, "n_boot": n_boot, **_db_stamp(db_path)}
    return blob["service"] if blob.get("meta") == expected else None


_lock = threading.Lock()
_service: Service | None = None


def get_service() -> Service:
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                db_path, n_boot = Path(settings.PIPELINE_DB_PATH), settings.FORECAST_BOOTSTRAPS
                _service = read_cache(Path(settings.FORECAST_CACHE_PATH), db_path, n_boot) \
                    or build_from_database(db_path, n_boot)
    return _service


def is_loaded() -> bool:
    return _service is not None


def set_service(service: Service | None) -> None:
    """Install (or clear) the shared service; used by tests and by management commands."""
    global _service
    _service = service
