"""FBref loader via `soccerdata` (drives a real Chrome through seleniumbase).

What is still available from FBref (its Opta-based advanced tables are gone):
  standard  minutes, matches, goals, assists, cards, nationality, birth year
  misc      tackles won, interceptions, crosses, fouls committed/drawn, offsides
  keeper    goals against, shots on target against, saves, clean sheets, penalties faced

FBref has no player id, so a row is identified by (league, season, team,
player_name); matching to other sources uses name + birth year + club.
Caveat: tackle/interception definitions appear to change between seasons
(provider change), so compare within a season (percentiles), not across seasons.

soccerdata keeps its own cache in ~/soccerdata/ rather than data/cache/.
"""
from __future__ import annotations

import pandas as pd

LEAGUES = {
    "EPL": "ENG-Premier League",
    "La_liga": "ESP-La Liga",
    "Bundesliga": "GER-Bundesliga",
    "Serie_A": "ITA-Serie A",
    "Ligue_1": "FRA-Ligue 1",
}

OUTFIELD_COLS = [
    "league", "season", "team", "player_name", "nation", "pos", "born", "age",
    "matches", "starts", "minutes", "goals", "assists", "pens_made", "pens_att",
    "yellow_cards", "red_cards", "fouls", "fouled", "offsides", "crosses", "interceptions", "tackles_won",
]
KEEPER_COLS = [
    "league", "season", "team", "player_name", "nation", "born", "age",
    "matches", "starts", "minutes", "goals_against", "shots_on_target_against", "saves",
    "wins", "draws", "losses", "clean_sheets", "pk_att", "pk_allowed", "pk_saved", "pk_missed",
]

_STANDARD = {
    "Playing Time/MP": "matches", "Playing Time/Starts": "starts", "Playing Time/Min": "minutes",
    "Performance/Gls": "goals", "Performance/Ast": "assists", "Performance/PK": "pens_made",
    "Performance/PKatt": "pens_att", "Performance/CrdY": "yellow_cards", "Performance/CrdR": "red_cards",
}
_MISC = {
    "Performance/Fls": "fouls", "Performance/Fld": "fouled", "Performance/Off": "offsides",
    "Performance/Crs": "crosses", "Performance/Int": "interceptions", "Performance/TklW": "tackles_won",
}
_KEEPER = {
    "Playing Time/MP": "matches", "Playing Time/Starts": "starts", "Playing Time/Min": "minutes",
    "Performance/GA": "goals_against", "Performance/SoTA": "shots_on_target_against",
    "Performance/Saves": "saves", "Performance/W": "wins", "Performance/D": "draws",
    "Performance/L": "losses", "Performance/CS": "clean_sheets", "Penalty Kicks/PKatt": "pk_att",
    "Penalty Kicks/PKA": "pk_allowed", "Penalty Kicks/PKsv": "pk_saved", "Penalty Kicks/PKm": "pk_missed",
}


def season_label(start_year: int) -> str:
    return f"{start_year}-{start_year + 1}"


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    """soccerdata returns (group, stat) column pairs; join them as 'group/stat'."""
    out = df.copy()
    out.columns = ["/".join(p for p in c if p) if isinstance(c, tuple) else c for c in out.columns]
    return out


def outfield_frame(standard: pd.DataFrame, misc: pd.DataFrame, league: str, season: int) -> pd.DataFrame:
    """Merge standard + misc into one row per (team, player); misc columns are NULL where misc lacks the player."""
    s = _flatten(standard).reset_index()
    m = _flatten(misc).reset_index()[["team", "player", *_MISC]].rename(columns=_MISC)
    d = s.merge(m, on=["team", "player"], how="left").rename(columns={"player": "player_name", **_STANDARD})
    d["league"], d["season"] = league, season
    d = d[d["pos"] != "GK"]
    return d.reindex(columns=OUTFIELD_COLS)


def keeper_frame(keeper: pd.DataFrame, league: str, season: int) -> pd.DataFrame:
    d = _flatten(keeper).reset_index().rename(columns={"player": "player_name", **_KEEPER})
    d["league"], d["season"] = league, season
    return d.reindex(columns=KEEPER_COLS)


def fetch_league_season(league: str, season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    import soccerdata as sd  # heavy import; only needed when actually scraping

    fb = sd.FBref(LEAGUES[league], season_label(season))
    standard = fb.read_player_season_stats(stat_type="standard")
    misc = fb.read_player_season_stats(stat_type="misc")
    keeper = fb.read_player_season_stats(stat_type="keeper")
    return outfield_frame(standard, misc, league, season), keeper_frame(keeper, league, season)
