"""Read-only endpoints. Views stay thin: the modelling lives in ml/, the fitted models in services.py."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ml.gap_analysis import gap_analysis
from pipeline_data.models import LeagueStrength, TransfermarktSquad

from . import serializers as S
from . import services

PER90 = ["goals_p90", "assists_p90", "npxg_p90", "xa_p90", "shots_p90", "key_passes_p90", "xg_chain_p90", "xg_buildup_p90",
         "npxg_p90_adj", "xa_p90_adj", "tackles_won_p90", "interceptions_p90", "crosses_p90", "fouls_p90", "fouled_p90",
         "save_pct", "gk_sota_p90"]
COMP_STATS = ["npxg_p90", "xa_p90", "shots_p90", "key_passes_p90", "xg_chain_p90", "tackles_won_p90", "interceptions_p90"]

OUTCOME_LABELS = {
    "elite": "Elite (peak in the top 10% of the position)",
    "good": "Good (peak in the top 25%)",
    "regular": "Regular top-5-league player",
    "out": "Out (no 900+ minute top-5-league season)",
    "retained": "Still a top-5-league regular",
}
CAVEATS = [
    "Outcomes are measured in the five covered leagues only; 'out' includes injury, retirement and moves to other leagues.",
    "Performance tiers use attacking output (a position-specific composite). Defenders and goalkeepers only get retained/out.",
    "Market value is conditional on staying on a top-5 squad and is capped at the highest value in the data.",
    "The ranges show model uncertainty, not outcome randomness. See the README backtest for calibration and failure cases.",
]


# ---------------------------------------------------------------- helpers
def clean(value):
    """JSON-safe copy: numpy scalars to Python, NaN/inf to None."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return [clean(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return v if math.isfinite(v) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def int_param(request, name: str, default: int | None, lo: int, hi: int) -> int | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise ValidationError({name: "must be an integer"})
    if not lo <= v <= hi:
        raise ValidationError({name: f"must be between {lo} and {hi}"})
    return v


def per90(row: pd.Series, cols=PER90) -> dict:
    return {c: row.get(c) for c in cols if c in row.index}


def target_dict(row: pd.Series) -> dict:
    return {"player_id": row.player_id, "name": row.player_name, "season": row.season, "league": row.league, "team": row.team,
            "position_group": row.position_group, "age": row.age, "minutes": row.minutes}


def comp_dict(row: pd.Series) -> dict:
    observable = bool(row.get("observable")) if pd.notna(row.get("observable")) else False
    return {"player_id": row.player_id, "name": row.player_name, "season": row.season, "league": row.league, "team": row.team,
            "age": row.age, "minutes": row.minutes, "distance": row.get("distance"),
            "outcome": row.get("tier") if observable else None,
            "value_ratio": row.get("value_ratio") if observable else None,
            "per90": per90(row, COMP_STATS)}


def resolve_target(svc: services.Service, player_id: int, season: int | None):
    """(season, target row) or a 404 that says what to do about it."""
    if season is None:
        season = svc.latest_season(player_id)
        if season is None:
            known = (svc.out.player_id == player_id).any()
            raise NotFound("This player has no season with enough minutes (450+) and a known age to compare."
                           if known else f"No player with id {player_id}.")
    try:
        return season, svc.engine.target_row(player_id, season)
    except KeyError:
        raise NotFound(f"Player {player_id} has no ranked season {season} (needs 450+ minutes and a known age).")


# ---------------------------------------------------------------- endpoints
class PlayerSearchView(APIView):
    @extend_schema(
        summary="Search players by name",
        description="Accent-insensitive; every query word must appear in the name. Exact and prefix matches rank first, "
                    "then by career minutes. Intended for autocomplete.",
        parameters=[OpenApiParameter("q", str, required=True, description="At least 2 characters"),
                    OpenApiParameter("limit", int, description="1-25, default 10")],
        responses=S.PlayerSearchResultSerializer(many=True))
    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            raise ValidationError({"q": "at least 2 characters"})
        limit = int_param(request, "limit", 10, 1, 25)
        hits = services.get_service().index.search(q, limit)
        rows = [{"player_id": r.player_id, "name": r.player_name, "latest_season": r.season, "team": r.team,
                 "league": r.league, "position_group": r.position_group, "age": r.age, "minutes": r.minutes}
                for r in hits.itertuples()]
        return Response(S.PlayerSearchResultSerializer(clean(rows), many=True).data)


class PlayerProfileView(APIView):
    @extend_schema(
        summary="Player profile",
        description="Bio from Transfermarkt (when linked) and every season with per-90 rates and percentiles.",
        responses=S.PlayerProfileSerializer)
    def get(self, request, player_id: int):
        svc = services.get_service()
        rows = svc.out[svc.out.player_id == player_id].sort_values(["season", "minutes"])
        if rows.empty:
            raise NotFound(f"No player with id {player_id}.")
        pct_cols = [c for c in rows.columns if c.endswith("_pct_global") or c.endswith("_pct_league")]
        seasons = [{
            "season": r.season, "league": r.league, "team": r.team, "position_group": r.position_group, "age": r.age,
            "minutes": r.minutes, "games": r.games, "market_value_eur": r.value_now,
            "per90": per90(r), "percentiles": {c: r[c] for c in pct_cols if pd.notna(r[c])},
        } for _, r in rows.iterrows()]

        last = rows.iloc[-1]
        tm_id = rows.tm_player_id.dropna()
        tm_id = int(tm_id.iloc[-1]) if len(tm_id) else None
        bio = TransfermarktSquad.objects.filter(tm_player_id=tm_id).order_by("-season").first() if tm_id else None
        data = {
            "player_id": player_id, "name": last.player_name, "position_group": last.position_group, "tm_player_id": tm_id,
            "birth_date": bio.birth_date if bio else None,
            "nationalities": (bio.nationalities or bio.nationality or "").split("|") if bio and (bio.nationalities or bio.nationality) else [],
            "height_cm": bio.height_cm if bio else None, "foot": bio.foot if bio else None,
            "tm_position": bio.position if bio else None,
            "latest_season": svc.latest_season(player_id), "seasons": seasons,
        }
        return Response(S.PlayerProfileSerializer(clean(data)).data)


class PlayerCompsView(APIView):
    @extend_schema(
        summary="Comparable players",
        description=("The player-seasons most similar to this one, controlled for position, age (+-1.5 years) and league "
                     "quality, one row per distinct player, with what each went on to become and a gap analysis "
                     "against the comp set. Similarity is by statistical profile; the backtest found it adds no "
                     "predictive power beyond current level, so use it as evidence, not as the probability."),
        parameters=[OpenApiParameter("season", int, description="Start year; default: the player's latest ranked season"),
                    OpenApiParameter("k", int, description="Number of comps, 1-50, default 10")],
        responses=S.CompsResponseSerializer)
    def get(self, request, player_id: int):
        svc = services.get_service()
        season = int_param(request, "season", None, 2000, 2100)
        k = int_param(request, "k", 10, 1, 50)
        season, target = resolve_target(svc, player_id, season)
        try:
            comps = svc.engine.comps(player_id, season, k=k)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        gaps = gap_analysis(target, comps)
        data = {
            "target": target_dict(target), "features_used": comps.attrs.get("features_used", []), "horizon": svc.horizon,
            "comps": [comp_dict(r) for _, r in comps.iterrows()],
            "gap_analysis": gaps.to_dict("records") if len(gaps) else [],
        }
        return Response(S.CompsResponseSerializer(clean(data)).data)


class PlayerForecastView(APIView):
    @extend_schema(
        summary="Trajectory forecast",
        description=("Probabilities for what the player becomes over the next `horizon` seasons, with a model-uncertainty "
                     "range, a market-value range, and the comps as evidence. The headline comes from a learned model "
                     "(validated in a rolling-origin backtest); `comps_alone` shows the weaker comps-only estimate."),
        parameters=[OpenApiParameter("season", int, description="Start year; default: the player's latest ranked season"),
                    OpenApiParameter("horizon", int, description="Seasons ahead; only the fitted horizon (3) is available")],
        responses=S.ForecastResponseSerializer)
    def get(self, request, player_id: int):
        svc = services.get_service()
        horizon = int_param(request, "horizon", svc.horizon, 1, 10)
        if horizon != svc.horizon:
            raise ValidationError({"horizon": f"only horizon={svc.horizon} is available"})
        season = int_param(request, "season", None, 2000, 2100)
        season, target = resolve_target(svc, player_id, season)
        f = svc.forecaster.forecast(player_id, season)

        view = f.comps_view
        probs = [{"outcome": c, "label": OUTCOME_LABELS.get(c, c), "probability": p, "p10": lo, "p90": hi,
                  "comps_alone": ca, "base_rate": br}
                 for c, p, lo, hi, ca, br in zip(f.classes, f.probs, f.lo, f.hi, view.probs, view.base_rate)]
        value = None
        if f.value_range:
            v = f.value_range
            value = {"now_eur": f.value_now, "p10_eur": v[0.1], "p50_eur": v[0.5], "p90_eur": v[0.9],
                     "ceiling_eur": f.value_ceiling, "conditional_on": "staying on a top-5-league squad"}
        evidence = view.comps.sort_values("distance").head(10)
        data = {
            "player": target_dict(target), "horizon": f.horizon, "as_of": f.as_of,
            "retrospective": bool(f.season + f.horizon <= f.as_of), "headline_source": f.source,
            "range_kind": ("10-90% across bootstrap refits of the model (model uncertainty)" if f.source == "learned model"
                           else "10-90% credible interval of the comps-based estimate"),
            "calibrated": svc.forecaster.calibration is not None and f.source == "learned model",
            "probabilities": probs, "value": value,
            "evidence_comps": [comp_dict(r) for _, r in evidence.iterrows()],
            "n_comps_used": view.n_comps, "caveats": CAVEATS,
        }
        return Response(S.ForecastResponseSerializer(clean(data)).data)


class LeagueStrengthView(APIView):
    @extend_schema(
        summary="League-strength factors",
        description=("Estimated from players who changed league: a factor of 0.85 means the same player typically produces "
                     "~15% less attacking output per 90 there than the five-league average (difficulty mixed with playing style)."),
        responses=S.LeagueStrengthSerializer(many=True))
    def get(self, request):
        rows = [{"league": r.league, "factor": r.factor, "ci_low": r.ci_low, "ci_high": r.ci_high,
                 "n_obs": r.n_obs, "n_movers": r.n_movers} for r in LeagueStrength.objects.all()]
        return Response(S.LeagueStrengthSerializer(clean(rows), many=True).data)


class MetaView(APIView):
    @extend_schema(summary="Data and model coverage", responses=S.MetaSerializer)
    def get(self, request):
        svc = services.get_service()
        out = svc.out
        data = {"players": len(svc.index), "player_seasons": len(out), "seasons": sorted(int(s) for s in out.season.unique()),
                "leagues": sorted(out.league.unique()), "horizon": svc.horizon, "as_of": svc.as_of,
                "calibrated": svc.forecaster.calibration is not None, "forecast_bootstrap_fits": len(svc.forecaster.boot),
                "backtest_report": "docs/backtest_h3.txt"}
        return Response(S.MetaSerializer(clean(data)).data)


class HealthView(APIView):
    throttle_classes: list = []

    @extend_schema(summary="Liveness (does not load the models)", responses=S.HealthSerializer)
    def get(self, request):
        return Response({"status": "ok", "models_loaded": services.is_loaded()})
