"""A small synthetic football world that exercises the real pipeline code (no mocks of ml/ or features/)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.similarity import ATTACK, DEFENCE

TEAMS = ["Alpha FC", "Beta FC", "Gamma FC", "Delta FC"]
SEASONS = [2016, 2017, 2018, 2019]
POSITIONS = ["FWD", "WING_AM", "MID", "DEF"]
PCT_COLS = [f"{m}_pct_global" for m in ("npxg", "xa", "shots", "key_passes", "xg_chain", "xg_buildup")] + \
           [f"{m}_pct_league" for m in ("tackles_won", "interceptions", "crosses", "fouls", "fouled")]
PCT_SOURCE = {"npxg": "npxg_p90_adj", "xa": "xa_p90_adj", "shots": "shots_p90_adj", "key_passes": "key_passes_p90_adj",
              "xg_chain": "xg_chain_p90_adj", "xg_buildup": "xg_buildup_p90_adj", "tackles_won": "tackles_won_p90",
              "interceptions": "interceptions_p90", "crosses": "crosses_p90", "fouls": "fouls_p90", "fouled": "fouled_p90"}


def make_features(n_players: int = 260, seed: int = 0) -> pd.DataFrame:
    """Player-seasons where quality is persistent and position shapes the stats, like the real feature table."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(1, n_players + 1):
        pos = POSITIONS[pid % 4]
        skill, birth_age = rng.normal(0, 1), rng.uniform(18, 29)
        team = TEAMS[pid % len(TEAMS)]
        for k, season in enumerate(SEASONS):
            if rng.uniform() < 0.1:
                continue
            age = birth_age + k
            minutes = float(rng.uniform(900, 3000))
            level = np.exp(0.35 * (skill + rng.normal(0, 0.3)))
            r = {"player_id": pid, "player_name": f"Player {pid} {'Álvaro' if pid == 7 else 'Test'}", "season": season,
                 "league": "EPL", "team": team, "position_group": pos, "age": age, "minutes": minutes,
                 "games": int(minutes / 80), "tm_player_id": 1000 + pid, "log_league_factor": -0.15, "league_jump": 0.0,
                 "understat_position": "F S"}
            attacking = pos in ("FWD", "WING_AM")
            for c in ATTACK:
                r[c] = max(0.01, 0.25 * level * (1.4 if attacking else 0.6) * rng.uniform(0.8, 1.2))
            for c in DEFENCE:
                r[c] = max(0.01, 1.2 * np.exp(0.2 * skill) * (1.5 if pos in ("DEF", "MID") else 0.6) * rng.uniform(0.8, 1.2))
            r.update({"npxg_p90": r["npxg_p90_adj"], "xa_p90": r["xa_p90_adj"], "goals_p90": 0.2 * level, "assists_p90": 0.1 * level,
                      "shots_p90": r["shots_p90_adj"], "key_passes_p90": r["key_passes_p90_adj"],
                      "xg_chain_p90": r["xg_chain_p90_adj"], "xg_buildup_p90": r["xg_buildup_p90_adj"]})
            rows.append(r)
    df = pd.DataFrame(rows)
    df["npxg"] = df.npxg_p90 * df.minutes / 90      # the season total, as in the real feature table
    ranked = df.minutes >= 450
    for m, src in PCT_SOURCE.items():
        suffix = "pct_league" if m in ("tackles_won", "interceptions", "crosses", "fouls", "fouled") else "pct_global"
        col = f"{m}_{suffix}"
        df[col] = np.nan
        df.loc[ranked, col] = df[ranked].groupby(["season", "position_group"])[src].rank(pct=True) * 100
    return df


def make_squads(features: pd.DataFrame, seed: int = 1) -> pd.DataFrame:
    """Season-end market values that grow with output and shrink with age."""
    rng = np.random.default_rng(seed)
    f = features
    comp = f[["npxg_pct_global", "xa_pct_global"]].mean(axis=1).fillna(50)
    value = np.exp(13.5 + 0.03 * (comp - 50) - 0.012 * (f.age - 24) ** 2 + rng.normal(0, 0.25, len(f)))
    return pd.DataFrame({"tm_player_id": f.tm_player_id, "season": f.season, "market_value_eur": np.round(value, -4)})


def make_team_tables(seed: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """team_matches and team_style for the four teams in the last two seasons."""
    rng = np.random.default_rng(seed)
    matches, style = [], []
    for season in SEASONS[-2:]:
        for i, team in enumerate(TEAMS):
            strength = 1.0 + 0.25 * i
            for m in range(6):
                matches.append(dict(league="EPL", season=season, team=team, match_date=f"{season}-09-{m + 1:02d}", home=m % 2,
                                    xg=1.0 * strength, xga=2.0 - 0.3 * i, npxg=0.9 * strength, npxga=1.8 - 0.3 * i,
                                    ppda_att=int(150 - 25 * i), ppda_def=10, ppda_allowed_att=100, ppda_allowed_def=10,
                                    deep=4 + 2 * i, deep_allowed=10 - 2 * i, scored=1 + i % 3, missed=1, xpts=1.2 + 0.3 * i, pts=1 + i % 3))
            spec = {("situation", "OpenPlay"): 6.0 * strength, ("situation", "FromCorner"): 1.5 * strength, ("situation", "SetPiece"): 0.5 * strength,
                    ("situation", "DirectFreekick"): 0.4 * strength, ("attackSpeed", "Fast"): 0.8 * strength,
                    ("attackSpeed", "Slow"): 3.0 * strength, ("attackSpeed", "Normal"): 4.0 * strength, ("attackSpeed", "Standard"): 1.0}
            for (grp, stat), xg in spec.items():
                style.append(dict(league="EPL", season=season, team=team, grp=grp, stat=stat, time=None, shots=int(xg * 8),
                                  goals=0, xg=xg, against_shots=5, against_goals=0, against_xg=(2.5 - 0.4 * i) * xg / 3))
    return pd.DataFrame(matches), pd.DataFrame(style)
