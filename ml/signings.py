"""Do the players a team signs and loses explain how its style changes? (evidence for recruitment suggestions)

A recruitment tool that says "you lack transition threat, sign someone with profile X" needs profile X to
actually move that dimension. This module tests it observationally:

  for every team-season with a previous season, take the minutes-weighted contribution of
    arrivals    (ranked players at the club now, not there last season)
    departures  (ranked players there last season, not now)
  on each player metric (percentile within position, centred at 50), and ask whether those contributions
  explain the change in each team style dimension (percentile within league-season), controlling for the
  team's previous level (regression to the mean).

Everything is observational: teams that sign well improve everywhere, managers change, and squads change
for reasons that also change style. We therefore score the explanatory value out of sample (grouped by team)
against a controls-only baseline, and read coefficients only as associations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

from features import team_style as ts

KEYS = ["league", "season", "team"]
METRICS = ["npxg_pct_global", "xa_pct_global", "xg_chain_pct_global", "xg_buildup_pct_global", "key_passes_pct_global",
           "shots_pct_global", "tackles_won_pct_league", "interceptions_pct_league", "crosses_pct_league"]
MIN_MINUTES = 450


def _season_metrics(features: pd.DataFrame) -> pd.DataFrame:
    """One row per (player_id, season): the player's own percentiles centred at 50 and total minutes that season."""
    f = features.sort_values("minutes").groupby(["player_id", "season"], as_index=False).tail(1)
    cols = [m for m in METRICS if m in f]
    out = f[["player_id", "season", "minutes"] + cols].copy()
    out[cols] = out[cols].sub(50.0)
    return out.rename(columns={"minutes": "season_minutes"}).set_index(["player_id", "season"])


def changes(team_players: pd.DataFrame, features: pd.DataFrame, minutes_cap: float = 3000.0) -> pd.DataFrame:
    """Per team-season (with a previous season): what the squad gained and lost, as a recruiter could have seen it.

      departures  ranked players of last season's squad who are gone: their last-season percentiles, weighted by
                  the minutes they played at the club
      arrivals    ranked players of this season's squad who were not there: their *previous-season* percentiles
                  (wherever they played), weighted by those previous minutes. Using the arrival's current-season
                  output would be an accounting identity (a team's xG is the sum of its players' xG), not a signal.
      arr_unknown arrivals with no previous top-5 season (promoted youngsters, imports): share of last season's squad
                  minutes they replace, so that "unknown" is not silently treated as "average"

    All contributions are divided by the team's total ranked minutes last season, so +5 means "adds 5 percentile
    points to the squad's minutes-weighted average"."""
    cols = [m for m in METRICS if m in features]
    ranked = team_players[team_players.minutes >= MIN_MINUTES][KEYS + ["understat_player_id", "minutes"]]
    sm = _season_metrics(features)

    last = ranked.assign(season=ranked.season + 1).rename(columns={"minutes": "club_minutes"})  # last season's squad, keyed by the season it feeds
    cur_keys = ranked.set_index(KEYS + ["understat_player_id"]).index
    last_keys = last.set_index(KEYS + ["understat_player_id"]).index
    total_last = last.groupby(KEYS).club_minutes.sum().rename("total_last")

    def with_metrics(df: pd.DataFrame, season_col: pd.Series) -> pd.DataFrame:
        idx = pd.MultiIndex.from_arrays([df.understat_player_id, season_col])
        return pd.concat([df.reset_index(drop=True), sm.reindex(idx).reset_index(drop=True)], axis=1)

    # departures: last season's squad members who are not in this season's squad
    dep = last[~last_keys.isin(cur_keys)]
    dep = with_metrics(dep, dep.season - 1).join(total_last, on=KEYS)
    w = np.minimum(dep.club_minutes, minutes_cap) / dep.total_last
    departures = (dep[cols].fillna(0.0).mul(w, axis=0)).assign(**{k: dep[k] for k in KEYS}).groupby(KEYS)[cols].sum().add_prefix("dep_")

    # arrivals: this season's squad members who were not in last season's squad
    arr = ranked[~cur_keys.isin(last_keys)]
    arr = with_metrics(arr, arr.season - 1).join(total_last, on=KEYS)
    arr = arr[arr.total_last.notna()]                      # teams without a previous season carry no change
    known = arr.season_minutes.notna()
    prior_w = np.minimum(arr.season_minutes.fillna(0.0), minutes_cap) / arr.total_last
    arrivals = (arr[cols].fillna(0.0).mul(prior_w, axis=0)).assign(**{k: arr[k] for k in KEYS}).groupby(KEYS)[cols].sum().add_prefix("arr_")
    unknown = (np.minimum(arr.minutes, minutes_cap) / arr.total_last).where(~known, 0.0)
    arrivals["arr_unknown"] = unknown.groupby([arr[k] for k in KEYS]).sum()

    base = total_last.reset_index().set_index(KEYS)[[]]
    out = base.join(arrivals).join(departures).fillna(0.0)
    cur = ranked.groupby(KEYS).size().index
    return out[out.index.isin(cur)].reset_index()


def design(ch: pd.DataFrame, profiles_pct: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Rows: team-seasons with the change in `dim` percentile, last season's level, and the squad-change features."""
    p = profiles_pct[KEYS + [f"{dim}_pct"]]
    prev = p.assign(season=p.season + 1).rename(columns={f"{dim}_pct": "prev_level"})
    d = ch.merge(p.rename(columns={f"{dim}_pct": "level"}), on=KEYS).merge(prev, on=KEYS)
    d["delta"] = d.level - d.prev_level
    return d


def evaluate(ch: pd.DataFrame, profiles_pct: pd.DataFrame, alpha: float = 30.0, folds: int = 5) -> pd.DataFrame:
    """Out-of-sample R^2 (grouped by team) of change in each style dimension: controls-only vs controls + squad changes."""
    arr = [c for c in ch.columns if c.startswith(("arr_", "dep_"))]
    rows = []
    for dim in ts.DIMENSIONS:
        d = design(ch, profiles_pct, dim).dropna(subset=["delta", "prev_level"])
        y, groups = d.delta.to_numpy(), d.team.to_numpy()
        controls = d[["prev_level"]].to_numpy()
        full = np.column_stack([controls, d[arr].to_numpy()])
        pred_c, pred_f = np.zeros(len(d)), np.zeros(len(d))
        for tr, te in GroupKFold(folds).split(d, groups=groups):
            pred_c[te] = Ridge(alpha=1.0).fit(controls[tr], y[tr]).predict(controls[te])
            mu, sd = full[tr].mean(axis=0), full[tr].std(axis=0) + 1e-9
            pred_f[te] = Ridge(alpha=alpha).fit((full[tr] - mu) / sd, y[tr]).predict((full[te] - mu) / sd)
        sst = ((y - y.mean()) ** 2).sum()
        rows.append({"dimension": dim, "n": len(d), "r2_controls": 1 - ((y - pred_c) ** 2).sum() / sst,
                     "r2_with_squad_changes": 1 - ((y - pred_f) ** 2).sum() / sst})
    r = pd.DataFrame(rows)
    return r.assign(gain=r.r2_with_squad_changes - r.r2_controls)


def coefficients(ch: pd.DataFrame, profiles_pct: pd.DataFrame, dim: str, alpha: float = 30.0, n_boot: int = 200, seed: int = 0) -> pd.DataFrame:
    """Standardised-feature ridge coefficients for one dimension with team-cluster bootstrap intervals.

    Arrival coefficient = effect of squad-average metric points added by arrivals; departures enter with the same
    sign convention (metric points *removed*), so a departing creator should show a negative departures coefficient."""
    arr = [c for c in ch.columns if c.startswith(("arr_", "dep_"))]
    d = design(ch, profiles_pct, dim).dropna(subset=["delta", "prev_level"]).reset_index(drop=True)
    x = np.column_stack([d[["prev_level"]].to_numpy(), d[arr].to_numpy()])
    mu, sd = x.mean(axis=0), x.std(axis=0) + 1e-9

    def fit(idx):
        return Ridge(alpha=alpha).fit((x[idx] - mu) / sd, d.delta.to_numpy()[idx]).coef_ / sd  # per raw unit
    point = fit(np.arange(len(d)))
    rng = np.random.default_rng(seed)
    by_team = {t: np.flatnonzero(d.team.to_numpy() == t) for t in d.team.unique()}
    teams = np.array(list(by_team))
    draws = np.array([fit(np.concatenate([by_team[t] for t in rng.choice(teams, len(teams))])) for _ in range(n_boot)])
    return pd.DataFrame({"feature": ["prev_level"] + arr, "coef": point, "lo": np.percentile(draws, 2.5, axis=0),
                         "hi": np.percentile(draws, 97.5, axis=0)})
