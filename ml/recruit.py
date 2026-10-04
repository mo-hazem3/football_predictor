"""Recruitment shortlist: from a team's style gaps to candidate players. A heuristic, labelled as one.

Chain: team style profile -> gap dimensions (bottom quartile in the league that season, features.team_style)
-> candidates whose own metrics bear on that dimension -> shown with price-vs-output (value lens) and age.

How much to trust the middle link. ml.signings found that what a team signs and loses, as a recruiter could have
seen it beforehand, explains only a few points of R^2 of next season's style change; the one clearly supported
association is that creative / progressive arrivals (xA, xG build-up) raise open-play chance creation. So the
mapping below from gap to player metrics is a transparent design assumption, not an estimated effect:
  * it ranks players by how strong they are, for their position, on the metrics that plausibly drive the gap;
  * it does not predict that signing one of them closes the gap;
  * set-piece defending has no mapping (no aerial or marking data in the free sources) and says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features.team_style import LABELS

# gap dimension -> (positions that can address it, percentile columns of the player metrics that bear on it)
GAP_PROFILE: dict[str, tuple[list[str], list[str]] | None] = {
    "open_play_xg": (["WING_AM", "MID", "FWD"], ["xa_pct_global", "key_passes_pct_global", "xg_chain_pct_global"]),
    "transition_xg": (["WING_AM", "FWD"], ["npxg_pct_global", "xa_pct_global"]),
    "set_piece_xg": (["WING_AM", "MID", "DEF"], ["xa_pct_global", "crosses_pct_league"]),
    "deep_completions": (["MID", "WING_AM", "FWD"], ["xg_buildup_pct_global", "xg_chain_pct_global", "key_passes_pct_global"]),
    "shot_quality": (["FWD", "WING_AM"], ["xg_per_shot_pct", "npxg_pct_global"]),
    "open_play_xga": (["DEF", "MID"], ["tackles_won_pct_league", "interceptions_pct_league"]),
    "transition_xga": (["DEF", "MID"], ["tackles_won_pct_league", "interceptions_pct_league"]),
    "deep_allowed": (["DEF", "MID"], ["tackles_won_pct_league", "interceptions_pct_league"]),
    "pressing": (["MID", "WING_AM", "DEF"], ["tackles_won_pct_league", "interceptions_pct_league"]),
    "set_piece_xga": None,
}
NOTES = {"set_piece_xga": "No mapping: the free data has no aerial duels or marking, so no player can be ranked on this."}
# attacking output plateau by position (ages within 3% of the estimated maximum; see ml.aging)
PLATEAU = {"FWD": (23, 30), "WING_AM": (24, 29), "MID": (24, 27), "DEF": (23, 26)}


def candidates(out: pd.DataFrame, season: int, min_minutes: int = 900, max_age: float = 31.0) -> pd.DataFrame:
    """One row per player in `season`: main-league row, with percentiles, value and age filters applied."""
    d = out[(out.season == season) & (out.minutes >= min_minutes) & out.age.notna() & (out.age <= max_age)
            & out.position_group.isin(["FWD", "WING_AM", "MID", "DEF"])]
    d = d.sort_values("minutes").groupby("player_id", as_index=False).tail(1).reset_index(drop=True)
    # xG per shot (shot quality, not volume): percentile within position among players who shoot at least occasionally
    xps = (d.npxg_p90 / d.shots_p90).where(d.shots_p90 >= 0.5)
    d["xg_per_shot_pct"] = xps.groupby(d.position_group).rank(pct=True) * 100
    return d


def age_note(position: str, age: float) -> str:
    lo, hi = PLATEAU[position]
    return "before the usual output plateau" if age < lo else "inside the plateau" if age <= hi else "past the plateau"


def shortlist(cands: pd.DataFrame, dimension: str, team: str, n: int = 8, max_value_eur: float | None = None,
              max_age: float | None = None, min_percentile: float = 60.0) -> pd.DataFrame:
    """Candidates for one gap, best first.

    fit = mean percentile (within position) on the metrics that bear on the gap; players already at `team`
    are excluded. `min_percentile` keeps the list to people who are actually strong at it."""
    spec = GAP_PROFILE.get(dimension)
    if spec is None:
        return pd.DataFrame()
    positions, metrics = spec
    d = cands[cands.position_group.isin(positions) & ~cands.team.fillna("").str.contains(team, regex=False)].copy()
    metrics = [m for m in metrics if m in d]
    d["fit"] = d[metrics].mean(axis=1, skipna=False)   # a missing metric means 'cannot rank', not 'average'
    d = d[d.fit >= min_percentile]
    if max_value_eur is not None:
        d = d[d.value_now <= max_value_eur]
    if max_age is not None:
        d = d[d.age <= max_age]
    d["age_note"] = [age_note(p, a) for p, a in zip(d.position_group, d.age)]
    cols = ["player_id", "player_name", "team", "league", "position_group", "age", "age_note", "minutes", "fit", "value_now"]
    cols += [c for c in ("price_vs_output",) if c in d]
    return d.sort_values("fit", ascending=False)[cols].head(n).reset_index(drop=True)
