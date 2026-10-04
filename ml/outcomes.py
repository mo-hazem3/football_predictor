"""Outcomes: what a player became over the following `horizon` seasons.

Two independent definitions, because each answers a different question:

PERFORMANCE tier (stats-based, what the player actually produced)
  peak composite percentile over the next H seasons (seasons with 900+ minutes in the top-5
  leagues). The composite averages position-relevant cross-league percentiles on
  league-adjusted rates:
      FWD      non-penalty xG, xA, xG chain
      WING_AM  non-penalty xG, xA, key passes, xG chain
      MID      xG chain, xG build-up, xA, key passes
  Tiers: elite >= 90, good >= 75, regular < 75, and "out" when the player has no 900+ minute
  top-5 season in the window (left the five leagues, lost his place, retired, or injured).
  DEFENDERS AND GOALKEEPERS get no performance tier: Understat measures attacking contribution,
  which says little about their quality, so they only get retained / out.

MARKET VALUE (Transfermarkt squad-page value at the end of each season)
  peak value in the next H seasons divided by the value now. Only seasons in which the player is
  on a top-5 squad are observable, so this is conditional on staying in the five leagues; the
  retention outcome reports how often that happens.

An outcome is `observable` only if the whole window ends by `last_season`; incomplete windows
are never scored (no partial credit), so a recent row cannot look like a failure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COMPOSITES = {
    "FWD": ["npxg", "xa", "xg_chain"],
    "WING_AM": ["npxg", "xa", "key_passes", "xg_chain"],
    "MID": ["xg_chain", "xg_buildup", "xa", "key_passes"],
}
ELITE, GOOD = 90.0, 75.0
MIN_MINUTES_OUTCOME = 900
PERF_TIERS = ["out", "regular", "good", "elite"]
RETENTION_TIERS = ["out", "retained"]


def classes_for(group: str) -> list[str]:
    return PERF_TIERS if group in COMPOSITES else RETENTION_TIERS


def add_composite(df: pd.DataFrame) -> pd.DataFrame:
    """Position-specific composite percentile; NaN for DEF/GK or when any component is missing."""
    df = df.copy()
    df["composite"] = np.nan
    for group, comps in COMPOSITES.items():
        cols = [f"{c}_pct_global" for c in comps]
        m = df.position_group == group
        if m.any():
            df.loc[m, "composite"] = df.loc[m].reindex(columns=cols).mean(axis=1, skipna=False)
    return df


def tier_of(peak: float, group: str) -> str | float:
    if group not in COMPOSITES:
        return "retained"
    if pd.isna(peak):
        return np.nan
    return "elite" if peak >= ELITE else "good" if peak >= GOOD else "regular"


def value_series(squads: pd.DataFrame) -> dict[int, dict[int, float]]:
    """tm_player_id -> {season: season-end market value}, from the Transfermarkt squad table."""
    s = squads.dropna(subset=["market_value_eur"]).groupby(["tm_player_id", "season"]).market_value_eur.max()
    out: dict[int, dict[int, float]] = {}
    for (pid, season), v in s.items():
        out.setdefault(int(pid), {})[int(season)] = float(v)
    return out


def build_outcomes(df: pd.DataFrame, values: dict, horizon: int = 3, last_season: int = 2025) -> pd.DataFrame:
    """Outcome columns for every row of `df` (needs composite; see add_composite).

    Added: observable, n_qual_future, peak_composite, tier, value_now, peak_value, value_ratio.
    """
    if "composite" not in df:
        df = add_composite(df)
    # one record per player-season (a player can have two league rows): minutes pooled, main-league composite
    ps = (df.sort_values("minutes").groupby(["player_id", "season"])
            .agg(minutes=("minutes", "sum"), composite=("composite", "last")))
    qualifying = {k: c for k, (m, c) in zip(ps.index, ps[["minutes", "composite"]].itertuples(index=False)) if m >= MIN_MINUTES_OUTCOME}

    rows = []
    for r in df[["player_id", "season", "tm_player_id", "position_group"]].itertuples(index=False):
        window = [s for s in range(r.season + 1, r.season + horizon + 1) if s <= last_season]
        observable = r.season + horizon <= last_season
        q = [(r.player_id, s) for s in window if (r.player_id, s) in qualifying]
        comps = [qualifying[k] for k in q if not pd.isna(qualifying[k])]
        peak = max(comps) if comps else np.nan
        if not observable:
            tier = np.nan
        elif not q:
            tier = "out"
        else:
            tier = tier_of(peak, r.position_group)

        vals = values.get(int(r.tm_player_id), {}) if not pd.isna(r.tm_player_id) else {}
        now = vals.get(r.season, np.nan)
        future = [vals[s] for s in window if s in vals]
        peak_value = max(future) if (future and observable) else np.nan
        ratio = peak_value / now if (not pd.isna(peak_value) and now and now > 0) else np.nan
        rows.append((observable, len(q), peak, tier, now, peak_value, ratio))

    out = df.copy()
    out[["observable", "n_qual_future", "peak_composite", "tier", "value_now", "peak_value", "value_ratio"]] = pd.DataFrame(rows, index=df.index)
    return out
