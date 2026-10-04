"""The fitted models and precomputed tables behind the API, built once and shared across requests.

`Service` bundles
  * the forecaster (outcomes, similarity engine, learned tier and value models, calibration)
  * the player-name index
  * the value-vs-performance table (price versus output for every ranked forward/winger/midfielder season)
  * the aging curves
  * team style profiles with percentiles
Building it takes a minute or so, so:
  * `manage.py build_forecast_cache` pickles it next to the data;
  * `get_service()` loads that pickle when it is still valid for the current pipeline database, otherwise builds
    in-process on first use (guarded by a lock);
  * with PRELOAD_MODELS=1 the load happens at server start instead of on the first request.
The pickle is our own artefact on a local path; it is never read from user input.
"""
from __future__ import annotations

import pickle
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings

from features import team_style
from ml import aging, recruit, value_lens
from ml.forecast import Forecaster
from ml.outlook import Outlook, build_pairs

from .search import PlayerIndex

CACHE_VERSION = 4


@dataclass
class Service:
    forecaster: Forecaster
    index: PlayerIndex
    value_table: pd.DataFrame | None = None            # player_id, season, price_vs_output_pct, rank
    aging_curves: dict[str, pd.DataFrame] | None = None
    teams: pd.DataFrame | None = None                  # team-season profiles with *_pct columns
    outlook: Outlook | None = None                     # fan-chart models (forwards, wingers, midfielders)
    outlook_rows: pd.DataFrame | None = None           # reliable player-seasons with level and features, indexed for lookup
    _candidate_cache: dict = field(default_factory=dict, repr=False, compare=False)

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

    def candidates(self, season: int) -> pd.DataFrame:
        """Recruitment candidates for a season (cached), with price-versus-output where the value lens covers them."""
        if season not in self._candidate_cache:
            c = recruit.candidates(self.out, season, max_age=31.0)
            if self.value_table is not None:
                v = self.value_table[self.value_table.season == season].set_index("player_id").price_vs_output_pct
                c = c.join(v.rename("price_vs_output"), on="player_id")
            self._candidate_cache[season] = c
        return self._candidate_cache[season]


def build_value_table(out: pd.DataFrame) -> pd.DataFrame:
    """Cross-fitted (by player) price-versus-output for every ranked forward/winger/midfielder season.

    Fitted on all seasons together: fine for showing a player's current standing, but not a backtest (the pricing
    function has seen the future); the honest evaluation is ml.evaluate_value_lens."""
    panel = value_lens.build_panel(out)
    if panel.empty:
        return pd.DataFrame(columns=["player_id", "season", "position_group", "price_vs_output_pct", "rank"])
    resid = value_lens.crossfit_residual(panel, panel)
    t = panel[["player_id", "season", "position_group"]].assign(resid=resid)
    t["price_vs_output_pct"] = (np.exp(t.resid) - 1) * 100
    t["rank"] = t.groupby(["season", "position_group"]).resid.rank(pct=True)   # 0 = most underpriced
    return t.drop(columns="resid")


def build_aging(out: pd.DataFrame, n_boot: int = 60) -> dict[str, pd.DataFrame]:
    p = aging.panel(out, "attack")
    return {g: aging.fit_curve(p[p.position_group == g], n_boot=n_boot) for g in aging.GROUPS if (p.position_group == g).sum() > 50}


def build_service(forecaster: Forecaster, matches: pd.DataFrame | None = None, style: pd.DataFrame | None = None,
                  aging_boot: int = 60) -> Service:
    out = forecaster.out
    teams = None
    if matches is not None and style is not None and len(matches) and len(style):
        teams = team_style.add_percentiles(team_style.build_profiles(matches, style))
    outlook, rows = None, None
    try:
        pairs = build_pairs(out, forecaster.as_of)
        outlook = Outlook().fit(pairs)
        rows = pairs.set_index(["player_id", "season"], drop=False).rename_axis([None, None])  # unnamed levels: no clash with the columns
    except ValueError:   # too little history to fit (tiny databases): the endpoint then reports "not available"
        pass
    return Service(forecaster, PlayerIndex(out), build_value_table(out), build_aging(out, aging_boot), teams, outlook, rows)


# What the cached service is built from. The pipeline database also holds tables that change often and that the
# service never reads (value history, transfers, FBref); fingerprinting only these means a long-running scrape
# elsewhere in the file does not invalidate the cache. Cheap aggregates, not a hash of the rows.
FINGERPRINT_SQL = {
    "player_season_features": "SELECT COUNT(*), ROUND(SUM(minutes), 3), ROUND(SUM(npxg), 6), ROUND(SUM(COALESCE(age, 0)), 6), "
                              "ROUND(SUM(COALESCE(tackles_won_p90, 0)), 6) FROM player_season_features",
    "transfermarkt_squads": "SELECT COUNT(*), SUM(market_value_eur), SUM(tm_player_id) FROM transfermarkt_squads",
    "team_matches": "SELECT COUNT(*), ROUND(SUM(xg), 6), SUM(ppda_att) FROM team_matches",
    "team_style": "SELECT COUNT(*), ROUND(SUM(xg), 6) FROM team_style",
}


def data_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        out = {}
        for table, sql in FINGERPRINT_SQL.items():
            try:
                out[table] = list(conn.execute(sql).fetchone())
            except sqlite3.OperationalError:  # table not there (e.g. team data not ingested)
                out[table] = None
        return out
    finally:
        conn.close()


def _table_or_empty(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(sql, conn)
    except Exception:  # table missing: the optional team data has not been ingested
        return pd.DataFrame()


def build_from_database(db_path: Path, n_boot: int) -> Service:
    conn = sqlite3.connect(db_path)
    try:
        features = pd.read_sql("SELECT * FROM player_season_features", conn)
        squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
        matches = _table_or_empty(conn, "SELECT * FROM team_matches")
        style = _table_or_empty(conn, "SELECT * FROM team_style")
    finally:
        conn.close()
    return build_service(Forecaster(features, squads, n_boot=n_boot), matches, style)


def write_cache(service: Service, cache_path: Path, db_path: Path, n_boot: int) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"version": CACHE_VERSION, "n_boot": n_boot, "data": data_fingerprint(db_path)}
    service._candidate_cache.clear()
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
    expected = {"version": CACHE_VERSION, "n_boot": n_boot, "data": data_fingerprint(db_path)}
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
