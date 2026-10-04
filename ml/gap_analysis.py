"""Weakness / gap analysis: where does a player lag their comparable players?

Reuses percentiles already computed in features.build, so it is a presentation layer, not
new modelling. For each metric it compares the target's percentile with the distribution of
the comp set's percentiles (and with the position median, 50).

Which percentile: attacking metrics use the cross-league percentile on league-adjusted
rates (`*_pct_global`); defensive and goalkeeping metrics use the within-league percentile
(`*_pct_league`) because no validated league adjustment exists for them.
Percentiles rank raw values: a higher percentile means *more* of the thing (e.g. more
fouls), not necessarily better, so fouls is reported but never flagged as a weakness.
"""
from __future__ import annotations

import pandas as pd

# metric -> (label, percentile column, higher_is_better)
ATTACK_METRICS = {
    "npxg": ("Non-penalty xG", "npxg_pct_global", True),
    "xa": ("Expected assists", "xa_pct_global", True),
    "shots": ("Shots", "shots_pct_global", True),
    "key_passes": ("Key passes", "key_passes_pct_global", True),
    "xg_chain": ("xG chain", "xg_chain_pct_global", True),
    "xg_buildup": ("xG build-up", "xg_buildup_pct_global", True),
}
DEFENCE_METRICS = {
    "tackles_won": ("Tackles won", "tackles_won_pct_league", True),
    "interceptions": ("Interceptions", "interceptions_pct_league", True),
    "crosses": ("Crosses", "crosses_pct_league", True),
    "fouled": ("Fouls drawn", "fouled_pct_league", True),
    "fouls": ("Fouls committed", "fouls_pct_league", False),
}
GK_METRICS = {
    "save_pct": ("Save %", "save_pct_pct_league", True),
    "gk_sota": ("Shots on target faced", "gk_sota_pct_league", True),
}


def metrics_for(group: str) -> dict:
    return GK_METRICS if group == "GK" else {**ATTACK_METRICS, **DEFENCE_METRICS}


def gap_analysis(target: pd.Series, comps: pd.DataFrame, threshold: float = 15.0) -> pd.DataFrame:
    """Per-metric target percentile vs comp-set percentiles; sorted weakest first.

    `gap` = target percentile minus comp median. Flagged 'weakness' / 'strength' when the gap
    is beyond +-`threshold` percentile points (only for metrics where higher is better).
    """
    rows = []
    for key, (label, col, higher_is_better) in metrics_for(target.position_group).items():
        if col not in comps or pd.isna(target.get(col)):
            continue
        c = comps[col].dropna()
        if c.empty:
            continue
        gap = target[col] - c.median()
        flag = ""
        if higher_is_better:
            flag = "weakness" if gap <= -threshold else "strength" if gap >= threshold else ""
        rows.append({
            "metric": key, "label": label, "target_pct": target[col],
            "comp_median_pct": c.median(), "comp_p25": c.quantile(0.25), "comp_p75": c.quantile(0.75),
            "gap": gap, "vs_position_median": target[col] - 50.0, "flag": flag, "n_comps": len(c),
        })
    return pd.DataFrame(rows).sort_values("gap").reset_index(drop=True) if rows else pd.DataFrame()
