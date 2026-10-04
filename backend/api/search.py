"""Player name search: accent-insensitive, token-wise, ranked by match quality then by career minutes.

Built in memory from the feature table (about 9,000 distinct players): small enough that a
pandas scan per keystroke is a few milliseconds, and it avoids SQL collation tricks for accents.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd


def fold(text: str) -> str:
    """'Álex Grimaldo' -> 'alex grimaldo' (accents stripped, lower-case, punctuation to spaces)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).split())


class PlayerIndex:
    COLUMNS = ["player_id", "player_name", "season", "league", "team", "position_group", "age", "minutes"]

    def __init__(self, rows: pd.DataFrame):
        """`rows`: player-season rows (needs the columns above)."""
        r = rows.sort_values(["season", "minutes"])
        latest = r.groupby("player_id", sort=False).tail(1)[self.COLUMNS]
        career = rows.groupby("player_id").minutes.sum().rename("career_minutes")
        self.players = latest.merge(career, on="player_id").reset_index(drop=True)
        self.players["folded"] = self.players.player_name.map(fold)

    def __len__(self) -> int:
        return len(self.players)

    def search(self, query: str, limit: int = 10) -> pd.DataFrame:
        """Players whose name contains every query token. Exact name first, then names that start
        with the query, then the rest; within a tier, the player with more career minutes first."""
        q = fold(query)
        if not q:
            return self.players.iloc[0:0]
        names = self.players.folded
        mask = pd.Series(True, index=names.index)
        for token in q.split():
            mask &= names.str.contains(re.escape(token), regex=True)
        hits = self.players[mask].copy()
        tier = pd.Series(2, index=hits.index)
        tier[hits.folded.str.startswith(q)] = 1
        tier[hits.folded == q] = 0
        # a token that starts a word beats one buried inside another word ("mus" in "musiala" vs "grimaldo")
        starts = pd.Series(True, index=hits.index)
        for token in q.split():
            starts &= hits.folded.str.contains(r"\b" + re.escape(token), regex=True)
        tier[(tier == 2) & ~starts] = 3
        hits = hits.assign(_tier=tier).sort_values(["_tier", "career_minutes"], ascending=[True, False])
        return hits.head(limit).drop(columns=["_tier", "folded"])
