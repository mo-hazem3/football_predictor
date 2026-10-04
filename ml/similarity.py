"""Similarity engine: find the player-seasons most like a target, fairly.

"Fairly" means the comparison is controlled for what matters in football:
  * position   hard filter on position group
  * age        hard window (default +-1.5 years) plus a soft age term
  * league     stats are league-adjusted (features.league_strength), and the league's
               strength and the size of the league jump are *context* features
  * data       a query uses only the features its target actually has (FBref defensive
               stats do not exist before 2016); candidates must have the same ones

Distance (squared) = sum over blocks of  weight_b / dim_b * ||delta_b||^2
  blocks: attack stats, defence stats (outfield) | goalkeeping (GK) | context | age
Within a stats block, z-scored sqrt-rates are compared by Euclidean distance or, after
whitening with a shrunk covariance, Mahalanobis distance (see ml.evaluate_similarity for
which one retrieves better). The block weights below are design judgements, not tuned:
tuning them against "same player in adjacent seasons" would just reward persistent
context features, so only the metric is chosen empirically.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ATTACK = ["npxg_p90_adj", "xa_p90_adj", "shots_p90_adj", "key_passes_p90_adj", "xg_chain_p90_adj", "xg_buildup_p90_adj"]
DEFENCE = ["tackles_won_p90", "interceptions_p90", "fouls_p90", "crosses_p90", "fouled_p90"]
GOALKEEPING = ["save_pct", "gk_sota_p90"]
CONTEXT = ["log_league_factor", "league_jump"]

# block weights per position group: (attack, defence); goalkeepers use a single block
BLOCK_WEIGHTS = {
    "FWD": (1.0, 0.3), "WING_AM": (1.0, 0.3), "MID": (0.7, 1.0), "DEF": (0.5, 1.0),
}
CONTEXT_WEIGHT = 0.2
AGE_WEIGHT = 0.3
SHRINKAGE = 0.2  # covariance shrinkage toward its diagonal before whitening
NO_TRANSFORM = {"save_pct"}  # already a bounded ratio; everything else is a non-negative rate -> sqrt


def _blocks(group: str, cols: list[str]) -> list[tuple[list[str], float]]:
    """Feature blocks (columns, weight) for a position group restricted to the available columns."""
    if group == "GK":
        return [([c for c in GOALKEEPING if c in cols], 1.0)]
    wa, wd = BLOCK_WEIGHTS[group]
    return [b for b in (([c for c in ATTACK if c in cols], wa), ([c for c in DEFENCE if c in cols], wd)) if b[0]]


@dataclass
class SimilarityEngine:
    df: pd.DataFrame
    metric: str = "euclidean"            # 'euclidean' | 'mahalanobis' | 'cosine' (stats only)
    min_minutes_pool: int = 900          # candidates need this many minutes (rates are noisy below)
    min_minutes_target: int = 450
    age_window: float = 1.5
    use_context: bool = True
    _stats: dict = field(default_factory=dict, repr=False)
    _whiten: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        d = self.df
        d = d[d.age.notna() & d.position_group.notna() & (d.minutes >= self.min_minutes_target)].copy()
        all_cols = ATTACK + DEFENCE + GOALKEEPING
        for c in all_cols:
            if c in d:
                d[c + "__t"] = d[c] if c in NO_TRANSFORM else np.sqrt(d[c].clip(lower=0))
        # z-score parameters from the reliable pool only, per position group
        pool = d[d.minutes >= self.min_minutes_pool]
        for g, x in pool.groupby("position_group"):
            for c in all_cols:
                if c + "__t" in x and x[c + "__t"].notna().any():
                    self._stats[(g, c)] = (x[c + "__t"].mean(), x[c + "__t"].std(ddof=0) or 1.0)
        for c in CONTEXT:
            if c in pool:
                self._stats[("ctx", c)] = (pool[c].mean(), pool[c].std(ddof=0) or 1.0)
        self.d = d.reset_index(drop=True)
        self.d["_pool"] = self.d.minutes >= self.min_minutes_pool

    # ------------------------------------------------------------------ embedding
    def _z(self, rows: pd.DataFrame, group: str, cols: list[str]) -> np.ndarray:
        return np.column_stack([(rows[c + "__t"].to_numpy() - self._stats[(group, c)][0]) / self._stats[(group, c)][1] for c in cols])

    def _whitener(self, group: str, cols: tuple[str, ...]) -> np.ndarray:
        key = (group, cols)
        if key not in self._whiten:
            pool = self.d[(self.d.position_group == group) & self.d._pool & self.d[[c + "__t" for c in cols]].notna().all(axis=1)]
            z = self._z(pool, group, list(cols))
            cov = np.atleast_2d(np.cov(z, rowvar=False))
            cov = (1 - SHRINKAGE) * cov + SHRINKAGE * np.diag(np.diag(cov))
            vals, vecs = np.linalg.eigh(cov)
            self._whiten[key] = vecs @ np.diag(1.0 / np.sqrt(np.maximum(vals, 1e-6))) @ vecs.T
        return self._whiten[key]

    def embed(self, rows: pd.DataFrame, group: str, cols: list[str]) -> np.ndarray:
        """Vectors whose squared Euclidean distance is the engine's distance (cosine: stats block only)."""
        parts = []
        for block_cols, weight in _blocks(group, cols):
            z = self._z(rows, group, block_cols)
            if self.metric == "mahalanobis":
                z = z @ self._whitener(group, tuple(block_cols))
            elif self.metric == "cosine":
                z = z / np.linalg.norm(z, axis=1, keepdims=True).clip(min=1e-9)
                parts.append(z * np.sqrt(weight))
                continue
            parts.append(z * np.sqrt(weight / len(block_cols)))
        if self.use_context and self.metric != "cosine":
            ctx = np.column_stack([(rows[c].to_numpy() - self._stats[("ctx", c)][0]) / self._stats[("ctx", c)][1] for c in CONTEXT])
            parts.append(ctx * np.sqrt(CONTEXT_WEIGHT / len(CONTEXT)))
            parts.append((rows[["age"]].to_numpy() / self.age_window) * np.sqrt(AGE_WEIGHT))
        return np.hstack(parts)

    # ------------------------------------------------------------------ query
    def target_row(self, player_id: int, season: int) -> pd.Series:
        rows = self.d[(self.d.player_id == player_id) & (self.d.season == season)]
        if rows.empty:
            raise KeyError(f"no ranked row for player {player_id} in season {season} (>= {self.min_minutes_target} min, age known)")
        return rows.sort_values("minutes").iloc[-1]  # main league if the player appeared in two

    def candidates(self, target: pd.Series, exclude_self: bool = True,
                   max_season: int | None = None) -> tuple[pd.DataFrame, list[str]]:
        group = target.position_group
        cols = [c for c in (GOALKEEPING if group == "GK" else ATTACK + DEFENCE) if pd.notna(target.get(c + "__t"))]
        if len(cols) < 2:
            raise ValueError("target has too few usable features")
        pool = self.d[(self.d.position_group == group) & self.d._pool & ((self.d.age - target.age).abs() <= self.age_window)]
        pool = pool[pool[[c + "__t" for c in cols]].notna().all(axis=1)]
        if exclude_self:
            pool = pool[pool.player_id != target.player_id]
        if max_season is not None:
            pool = pool[pool.season <= max_season]
        return pool, cols

    def comps(self, player_id: int, season: int, k: int = 10, unique_players: bool = True,
              max_season: int | None = None) -> pd.DataFrame:
        """Closest player-seasons to (player, season); one row per distinct player by default.

        `max_season` restricts candidates to seasons <= that value (used to keep comps whose
        outcomes were already known at an as-of date)."""
        t = self.target_row(player_id, season)
        pool, cols = self.candidates(t, max_season=max_season)
        tv = self.embed(t.to_frame().T.infer_objects(), t.position_group, cols)
        pv = self.embed(pool, t.position_group, cols)
        out = pool.assign(distance=np.sqrt(((pv - tv) ** 2).sum(axis=1))).sort_values("distance")
        if unique_players:
            out = out.drop_duplicates("player_id")
        out = out.head(k).copy()
        out.attrs["features_used"] = cols
        return out

    def find(self, name: str, season: int | None = None) -> pd.DataFrame:
        """Rows whose name contains `name` (accent/case-insensitive enough for lookups)."""
        m = self.d[self.d.player_name.str.contains(name, case=False, regex=False)]
        if season is not None:
            m = m[m.season == season]
        return m[["player_id", "player_name", "season", "league", "team", "position_group", "age", "minutes"]]
