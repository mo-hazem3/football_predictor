"""Endpoints for the analyses built around the forecast: value vs performance, aging curves, team needs."""
from __future__ import annotations

import math

import pandas as pd
from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from features import team_style as ts
from ml import aging, recruit

from . import serializers as S
from . import services
from .views import clean, int_param, resolve_target, target_dict

POSITION_LABELS = {"FWD": "Forwards", "WING_AM": "Wingers & attacking mids", "MID": "Midfielders", "DEF": "Defenders"}


def _exp(x):
    """exp() of a log-scale bound; None when the bootstrap band is unavailable."""
    return None if x is None or pd.isna(x) else math.exp(x)


def standing(rank: float) -> str:
    """Where a player's price sits among the same position that season (rank 0 = most underpriced)."""
    return ("among the most underpriced 10%" if rank <= 0.1 else "underpriced" if rank <= 0.3
            else "among the most overpriced 10%" if rank > 0.9 else "overpriced" if rank > 0.7 else "fairly priced")


class PlayerValueView(APIView):
    @extend_schema(
        summary="Price versus output",
        description=("For forwards, wingers and midfielders: how far each season's market value sat below or above what "
                     "peers with the same output and age are valued at. Backtested: players priced lowest for their "
                     "output gained roughly 19% more value over the next season than the highest-priced "
                     "(33% over two), counting players who left the five leagues. It is about Transfermarkt's value "
                     "estimate, not transfer fees."),
        responses=S.PlayerValueSerializer)
    def get(self, request, player_id: int):
        svc = services.get_service()
        rows = svc.out[svc.out.player_id == player_id].sort_values(["season", "minutes"]).groupby("season", as_index=False).tail(1)
        if rows.empty:
            raise NotFound(f"No player with id {player_id}.")
        vt = svc.value_table[svc.value_table.player_id == player_id].set_index("season") if svc.value_table is not None else pd.DataFrame()
        covered = bool(rows.position_group.isin(["FWD", "WING_AM", "MID"]).any())
        seasons = []
        for r in rows.itertuples():
            v = vt.loc[r.season] if len(vt) and r.season in vt.index else None
            seasons.append({"season": r.season, "team": r.team, "market_value_eur": r.value_now,
                            "price_vs_output_pct": v.price_vs_output_pct if v is not None else None,
                            "standing": standing(v["rank"]) if v is not None else None})
        data = {"player_id": player_id, "name": rows.iloc[-1].player_name, "position_group": rows.iloc[-1].position_group,
                "covered": covered, "seasons": seasons,
                "reading": ("Negative = priced below peers with the same output and age. A screen to look at, not a buy signal: "
                            "value is revised a few times a year, so part of any gap is lag." if covered else
                            "The value lens covers forwards, wingers and midfielders; defenders and goalkeepers need defensive data the free sources lack.")}
        return Response(S.PlayerValueSerializer(clean(data)).data)


OUTLOOK_NOTES = [
    "Level is the position-specific composite percentile (league-adjusted attacking output) among players of that position that season.",
    "The band is conditional on the player still getting 900+ minutes in the five leagues; p_observed is the chance he does.",
    "Backtested on 2018-2022: the 10-90% band covered about 78% of outcomes (nominal 80%) and beat simpler baselines; see the README.",
]


class PlayerOutlookView(APIView):
    @extend_schema(
        summary="Fan-chart outlook",
        description=("Where the player's level (composite percentile, 0-100) is likely to be 1, 2 and 3 seasons from the chosen season, as a "
                     "10/50/90% band, plus the probability he is still a regular top-5-league player at each point. Forwards, wingers and "
                     "midfielders with 900+ minutes in the season."),
        parameters=[OpenApiParameter("season", int, description="Start year; default: the player's latest season with 900+ minutes")],
        responses=S.OutlookResponseSerializer)
    def get(self, request, player_id: int):
        svc = services.get_service()
        season = int_param(request, "season", None, 2000, 2100)
        rows = svc.outlook_rows
        skipped = None
        if season is None and rows is not None:
            # default to the latest season the model can use (900+ minutes), not merely the latest ranked one:
            # a player who was injured last season should still get an outlook from the one before
            mine = rows[rows.player_id == player_id]
            latest_ranked = svc.latest_season(player_id)
            if len(mine):
                season = int(mine.season.max())
                if latest_ranked is not None and latest_ranked > season:
                    skipped = latest_ranked
        season, target = resolve_target(svc, player_id, season)
        key = (player_id, season)
        covered = svc.outlook is not None and rows is not None and key in rows.index
        history, horizons, level_now = [], [], None
        if covered:
            row = rows.loc[[key]]
            q, p = svc.outlook.predict(row)[0], svc.outlook.predict_observed(row)[0]
            level_now = float(row.composite.iloc[0])
            hist = rows[rows.player_id == player_id].sort_values("season")
            history = [{"season": int(r.season), "level": float(r.composite)} for r in hist.itertuples()]
            horizons = [{"horizon": h, "season": season + h, "p10": q[i, 0], "p50": q[i, 1], "p90": q[i, 2], "p_observed": p[i]}
                        for i, h in enumerate((1, 2, 3))]
        notes = list(OUTLOOK_NOTES)
        if not covered:
            if target.position_group in ("DEF", "GK"):
                why = "defenders and goalkeepers have no composite level"
            else:
                why = f"he played {int(target.minutes)} minutes in {season}, below the 900 the model needs to read a level"
            notes.insert(0, f"No outlook: it covers forwards, wingers and midfielders with 900+ minutes in the season ({why}).")
        else:
            if skipped:
                notes.insert(0, f"His latest season ({skipped}) had fewer than 900 minutes, so the outlook starts from {season}.")
            if season + 1 <= svc.as_of:
                notes.insert(0, f"Season {season + 1} onwards has already been played as of {svc.as_of}: this is a retrospective forecast.")
        data = {"player": target_dict(target), "covered": bool(covered), "level_now": level_now, "history": history,
                "horizons": horizons, "model": "gradient-boosted quantile regression on current level, trend, age, minutes, league and value",
                "notes": notes}
        return Response(S.OutlookResponseSerializer(clean(data)).data)


class AgingView(APIView):
    @extend_schema(
        summary="Aging curves by position",
        description=("A player's attacking output at each age as a multiple of his own output at 25 (within-player estimate, "
                     "league-adjusted, 95% bootstrap band). Descriptive: the backtest found the curves add no forecasting value "
                     "beyond regression to the mean."),
        responses=S.AgingResponseSerializer)
    def get(self, request):
        curves = services.get_service().aging_curves
        if not curves:
            raise NotFound("Aging curves are not available.")
        min_obs = getattr(settings, "AGING_MIN_OBS", 30)
        groups = []
        for g, c in curves.items():
            plat = aging.plateau(c, min_obs=min_obs)
            if plat is None:      # too little data at every age: report nothing rather than a meaningless curve
                continue
            lo, hi = plat
            ok = c[c.n_obs >= min_obs]
            groups.append({"position_group": g, "label": POSITION_LABELS.get(g, g), "plateau_from": lo, "plateau_to": hi,
                           "points": [{"age": r.age, "multiple_of_25": r.multiple_of_25, "lo": _exp(r.lo),
                                       "hi": _exp(r.hi), "n_obs": r.n_obs} for r in ok.itertuples()]})
        notes = ["Survivorship: players who decline lose their 900+ minutes and drop out, so the older ages are optimistic.",
                 "Single-age peaks are not well determined; the plateau is the range within 3% of the smoothed maximum.",
                 "Measured on league-adjusted npxG + xA per 90, so it describes attacking involvement, including for defenders."]
        return Response(S.AgingResponseSerializer(clean({"groups": groups, "notes": notes})).data)


def _teams(svc: services.Service) -> pd.DataFrame:
    if svc.teams is None or svc.teams.empty:
        raise NotFound("Team data has not been ingested (run the ingest_understat_teams command).")
    return svc.teams


def _resolve_team(svc: services.Service, request) -> pd.Series:
    teams = _teams(svc)
    name = request.query_params.get("team", "").strip()
    if not name:
        raise ValidationError({"team": "required"})
    hit = teams[teams.team.str.casefold() == name.casefold()]
    if hit.empty:
        raise NotFound(f"No team named '{name}'. Use /teams/search/ to find the exact name.")
    season = int_param(request, "season", None, 2000, 2100)
    row = hit[hit.season == season] if season else hit.sort_values("season").tail(1)
    if row.empty:
        raise NotFound(f"No data for {hit.team.iloc[0]} in {season}.")
    return row.iloc[0]


def _dimensions(row: pd.Series, threshold: float) -> list[dict]:
    return [{"dimension": d, "label": ts.LABELS[d], "percentile": row[f"{d}_pct"],
             "value": row["ppda" if d == "pressing" else d], "is_gap": bool(row[f"{d}_pct"] <= threshold),
             "noisy": d in ts.NOISY_DIMENSIONS} for d in ts.DIMENSIONS]


class TeamSearchView(APIView):
    @extend_schema(summary="Search teams by name",
                   parameters=[OpenApiParameter("q", str, required=True), OpenApiParameter("limit", int)],
                   responses=S.TeamSearchResultSerializer(many=True))
    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            raise ValidationError({"q": "at least 2 characters"})
        limit = int_param(request, "limit", 10, 1, 25)
        teams = _teams(services.get_service())
        hit = teams[teams.team.str.contains(q, case=False, regex=False)]
        latest = hit.sort_values("season").groupby("team", as_index=False).tail(1).sort_values("team").head(limit)
        return Response(S.TeamSearchResultSerializer(
            clean([{"team": r.team, "league": r.league, "latest_season": r.season} for r in latest.itertuples()]), many=True).data)


class TeamProfileView(APIView):
    @extend_schema(
        summary="Team style profile and gaps",
        description=("Ten tactical-style dimensions ranked against the league that season (higher = better), from Understat "
                     "team data. A gap is a dimension in the bottom quartile (threshold adjustable). Pressing and penetration "
                     "are stable year to year; transition and set-piece threat are noisy and flagged as such."),
        parameters=[OpenApiParameter("team", str, required=True, description="Exact team name (see /teams/search/)"),
                    OpenApiParameter("season", int, description="Start year; default: latest"),
                    OpenApiParameter("threshold", int, description="Percentile at or below which a dimension is a gap, default 25")],
        responses=S.TeamProfileSerializer)
    def get(self, request):
        svc = services.get_service()
        row = _resolve_team(svc, request)
        threshold = int_param(request, "threshold", 25, 1, 50)
        data = {"team": row.team, "league": row.league, "season": row.season, "points_per_match": row.pts_pm,
                "xpts_per_match": row.xpts_pm, "xg_per_match": row.xg_pm, "xga_per_match": row.xga_pm,
                "dimensions": _dimensions(row, threshold)}
        return Response(S.TeamProfileSerializer(clean(data)).data)


class TeamShortlistView(APIView):
    @extend_schema(
        summary="Candidate players for a team gap (heuristic)",
        description=("Ranks players in suitable positions by their percentile on the metrics that plausibly bear on the gap, "
                     "capped by default at the market value of the club's most valuable player, with price-versus-output "
                     "and where the age sits on the position's output plateau. A labelled heuristic: an observational test "
                     "found that signings explain only a few points of R-squared of next season's style change, so it does "
                     "not predict that a signing closes the gap. Set-piece defending has no mapping."),
        parameters=[OpenApiParameter("team", str, required=True), OpenApiParameter("season", int),
                    OpenApiParameter("gap", str, description="A style dimension; default: the team's weakest"),
                    OpenApiParameter("max_value_m", float, description="Budget ceiling in EUR millions"),
                    OpenApiParameter("max_age", int, description="Default 29"), OpenApiParameter("n", int, description="1-25, default 8")],
        responses=S.ShortlistResponseSerializer)
    def get(self, request):
        svc = services.get_service()
        row = _resolve_team(svc, request)
        dims = {d["dimension"]: d for d in _dimensions(row, 25)}
        gap = request.query_params.get("gap") or min(dims, key=lambda d: dims[d]["percentile"])
        if gap not in dims:
            raise ValidationError({"gap": f"one of {sorted(dims)}"})
        try:
            max_value_m = float(request.query_params["max_value_m"]) if request.query_params.get("max_value_m") else None
        except ValueError:
            raise ValidationError({"max_value_m": "must be a number"})
        max_age = int_param(request, "max_age", 29, 16, 45)
        n = int_param(request, "n", 8, 1, 25)

        season = int(row.season)
        squad_values = svc.out[(svc.out.season == season) & svc.out.team.fillna("").str.contains(row.team, regex=False)].value_now
        default_ceiling = float(squad_values.max()) if squad_values.notna().any() else None
        ceiling = max_value_m * 1e6 if max_value_m else default_ceiling
        mapped = recruit.GAP_PROFILE.get(gap) is not None
        sl = recruit.shortlist(svc.candidates(season), gap, row.team, n=n, max_value_eur=ceiling, max_age=max_age) if mapped else pd.DataFrame()
        cands = [{"player_id": r.player_id, "name": r.player_name, "team": r.team, "league": r.league, "position_group": r.position_group,
                  "age": r.age, "age_note": r.age_note, "minutes": r.minutes, "fit": r.fit, "market_value_eur": r.value_now,
                  "price_vs_output_pct": getattr(r, "price_vs_output", None)} for r in sl.itertuples()]
        data = {"team": row.team, "season": season, "gap": dims[gap], "mapped": mapped, "note": recruit.NOTES.get(gap, ""),
                "ceiling_eur": ceiling, "candidates": cands,
                "method": "Heuristic ranking by position-relative percentile on gap-relevant metrics; not a prediction that a signing closes the gap."}
        return Response(S.ShortlistResponseSerializer(clean(data)).data)
