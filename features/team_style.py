"""Team tactical-style profiles and gap detection, from Understat team data (all five leagues, 2014-2025).

For every team-season we build a vector of per-match dimensions that a signing could plausibly change,
then rank each dimension against the league that season (percentile among its ~20 teams, oriented so
that higher is always better for the team). A "gap" is a dimension where a team is in the bottom quartile.

Dimensions (per match unless stated)
  ATTACK
    open_play_xg     xG created from open play
    transition_xg    xG created from fast attacks (Understat attack speed = Fast): counter / direct play
    set_piece_xg     xG from corners, set pieces and direct free kicks
    deep_completions completed passes/crosses within ~20 yards of goal (territorial penetration)
    shot_quality     xG per shot
  DEFENCE (oriented so higher = better, i.e. less conceded)
    open_play_xga    xG conceded from open play
    transition_xga   xG conceded from fast attacks (counter vulnerability)
    set_piece_xga    xG conceded from corners/set pieces
    deep_allowed     deep completions conceded (territory)
  PRESSING
    pressing         PPDA, inverted: opponent passes allowed per defensive action (lower PPDA = more pressing)

Limits worth knowing: this is a profile of what a team does, not a verdict on whether it should do more of
it, and gaps are relative to league peers. Understat has no possession share, so build-up style is only
visible through transition vs open-play shares and deep completions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEYS = ["league", "season", "team"]
ATTACK = ["open_play_xg", "transition_xg", "set_piece_xg", "deep_completions", "shot_quality"]
DEFENCE = ["open_play_xga", "transition_xga", "set_piece_xga", "deep_allowed"]
PRESSING = ["pressing"]
DIMENSIONS = ATTACK + DEFENCE + PRESSING

LABELS = {
    "open_play_xg": "Open-play chance creation", "transition_xg": "Transition / counter-attack threat",
    "set_piece_xg": "Set-piece threat", "deep_completions": "Penetration near goal",
    "shot_quality": "Shot quality (xG per shot)", "open_play_xga": "Open-play defending",
    "transition_xga": "Defending against counters", "set_piece_xga": "Set-piece defending",
    "deep_allowed": "Territory conceded near goal", "pressing": "Pressing intensity",
}
SET_PIECES = ["FromCorner", "SetPiece", "DirectFreekick"]


def _style_pivot(style: pd.DataFrame) -> pd.DataFrame:
    """Season totals per team from the long team_style table (for and against, split by situation/speed)."""
    def tot(grp: str, stats, col: str):
        s = style[(style.grp == grp) & style.stat.isin(stats)]
        return s.groupby(KEYS)[col].sum()

    parts = {
        "xg_open": tot("situation", ["OpenPlay"], "xg"), "xga_open": tot("situation", ["OpenPlay"], "against_xg"),
        "xg_setp": tot("situation", SET_PIECES, "xg"), "xga_setp": tot("situation", SET_PIECES, "against_xg"),
        "xg_fast": tot("attackSpeed", ["Fast"], "xg"), "xga_fast": tot("attackSpeed", ["Fast"], "against_xg"),
        "shots_all": tot("attackSpeed", ["Normal", "Standard", "Slow", "Fast"], "shots"),
        "xg_all": tot("attackSpeed", ["Normal", "Standard", "Slow", "Fast"], "xg"),
    }
    return pd.DataFrame(parts)


def build_profiles(matches: pd.DataFrame, style: pd.DataFrame) -> pd.DataFrame:
    """One row per team-season with raw dimensions (per match; higher = more of the thing) and results.

    `matches` = team_matches, `style` = team_style. Teams missing from `style` (failed downloads) are dropped."""
    g = matches.groupby(KEYS)
    m = g.agg(matches=("xg", "size"), deep=("deep", "sum"), deep_allowed=("deep_allowed", "sum"), xg=("xg", "sum"),
              xga=("xga", "sum"), pts=("pts", "sum"), xpts=("xpts", "sum"), ppda_att=("ppda_att", "sum"), ppda_def=("ppda_def", "sum"))
    d = m.join(_style_pivot(style), how="inner")
    n = d.matches
    prof = pd.DataFrame({
        "matches": n,
        "open_play_xg": d.xg_open / n, "transition_xg": d.xg_fast / n, "set_piece_xg": d.xg_setp / n,
        "deep_completions": d.deep / n, "shot_quality": d.xg_all / d.shots_all,
        "open_play_xga": d.xga_open / n, "transition_xga": d.xga_fast / n, "set_piece_xga": d.xga_setp / n,
        "deep_allowed": d.deep_allowed / n,
        "ppda": d.ppda_att / d.ppda_def,
        "xg_pm": d.xg / n, "xga_pm": d.xga / n, "pts_pm": d.pts / n, "xpts_pm": d.xpts / n,
    })
    return prof.reset_index()


def add_percentiles(prof: pd.DataFrame) -> pd.DataFrame:
    """Percentile (0-100) of every dimension within its league-season, oriented so higher = better.

    Defensive dimensions and PPDA are 'lower is better' in raw units, so their ranks are flipped; pressing is
    the inverse of PPDA."""
    out = prof.copy()
    lower_is_better = {"open_play_xga", "transition_xga", "set_piece_xga", "deep_allowed", "ppda"}
    for dim in ATTACK + DEFENCE + ["ppda"]:
        r = out.groupby(["league", "season"])[dim].rank(pct=True) * 100
        out[f"{dim}_pct"] = 100 - r + 100 / out.groupby(["league", "season"])[dim].transform("size") if dim in lower_is_better else r
    out["pressing_pct"] = out["ppda_pct"]
    return out.drop(columns=["ppda_pct"])


def gaps(profile_row: pd.Series, threshold: float = 25.0) -> pd.DataFrame:
    """Dimensions where the team is at or below the `threshold` percentile, weakest first."""
    rows = [{"dimension": d, "label": LABELS[d], "percentile": float(profile_row[f"{d}_pct"]), "value": float(profile_row["ppda" if d == "pressing" else d])}
            for d in DIMENSIONS if profile_row[f"{d}_pct"] <= threshold]
    return pd.DataFrame(rows).sort_values("percentile").reset_index(drop=True) if rows else pd.DataFrame(columns=["dimension", "label", "percentile", "value"])
