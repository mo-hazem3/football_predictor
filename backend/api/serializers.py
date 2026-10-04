"""Response shapes. Views build plain dicts; these serializers fix the contract and drive the OpenAPI schema."""
from rest_framework import serializers


class PlayerSearchResultSerializer(serializers.Serializer):
    player_id = serializers.IntegerField(help_text="Understat player id (the id used by every other endpoint)")
    name = serializers.CharField()
    latest_season = serializers.IntegerField(help_text="Start year of the most recent season, e.g. 2024 = 2024/25")
    team = serializers.CharField(allow_null=True)
    league = serializers.CharField()
    position_group = serializers.CharField(allow_null=True, help_text="GK, DEF, MID, WING_AM or FWD")
    age = serializers.FloatField(allow_null=True, help_text="Age in that season (decimal years, mid-season)")
    minutes = serializers.FloatField()


class SeasonStatsSerializer(serializers.Serializer):
    season = serializers.IntegerField()
    league = serializers.CharField()
    team = serializers.CharField(allow_null=True)
    position_group = serializers.CharField(allow_null=True)
    age = serializers.FloatField(allow_null=True)
    minutes = serializers.FloatField()
    games = serializers.IntegerField(allow_null=True)
    market_value_eur = serializers.FloatField(allow_null=True, help_text="Transfermarkt squad value at the end of that season")
    per90 = serializers.DictField(child=serializers.FloatField(allow_null=True),
                                  help_text="Per-90 rates; *_adj are league-adjusted")
    percentiles = serializers.DictField(
        child=serializers.FloatField(allow_null=True),
        help_text="0-100 within position group and season. *_pct_global ranks across leagues on league-adjusted "
                  "rates; *_pct_league ranks within the league. Empty below 450 minutes.")


class PlayerProfileSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    name = serializers.CharField()
    position_group = serializers.CharField(allow_null=True)
    tm_player_id = serializers.IntegerField(allow_null=True, help_text="Linked Transfermarkt id, when the link exists")
    birth_date = serializers.CharField(allow_null=True)
    nationalities = serializers.ListField(child=serializers.CharField())
    height_cm = serializers.IntegerField(allow_null=True)
    foot = serializers.CharField(allow_null=True)
    tm_position = serializers.CharField(allow_null=True)
    latest_season = serializers.IntegerField(allow_null=True, help_text="Latest season usable for comps/forecast (450+ minutes, age known)")
    seasons = SeasonStatsSerializer(many=True)


class CompSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    name = serializers.CharField()
    season = serializers.IntegerField()
    league = serializers.CharField()
    team = serializers.CharField(allow_null=True)
    age = serializers.FloatField()
    minutes = serializers.FloatField()
    distance = serializers.FloatField(help_text="Smaller = more similar (not comparable across different targets)")
    outcome = serializers.CharField(
        allow_null=True,
        help_text="What this comp became over the next horizon seasons: elite, good, regular, out (or retained/out "
                  "for defenders and goalkeepers). Null when that window is not finished yet.")
    value_ratio = serializers.FloatField(allow_null=True, help_text="Peak market value over the horizon / value at the time")
    per90 = serializers.DictField(child=serializers.FloatField(allow_null=True))


class TargetSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    name = serializers.CharField()
    season = serializers.IntegerField()
    league = serializers.CharField()
    team = serializers.CharField(allow_null=True)
    position_group = serializers.CharField()
    age = serializers.FloatField()
    minutes = serializers.FloatField()


class GapSerializer(serializers.Serializer):
    metric = serializers.CharField()
    label = serializers.CharField()
    target_pct = serializers.FloatField()
    comp_median_pct = serializers.FloatField()
    comp_p25 = serializers.FloatField()
    comp_p75 = serializers.FloatField()
    gap = serializers.FloatField(help_text="Target percentile minus comp median, in percentile points")
    flag = serializers.CharField(allow_blank=True, help_text="'weakness' or 'strength' beyond +-15 points, else empty")
    n_comps = serializers.IntegerField()


class CompsResponseSerializer(serializers.Serializer):
    target = TargetSerializer()
    features_used = serializers.ListField(child=serializers.CharField(),
                                          help_text="Stats the comparison used; seasons before 2016 lack FBref defensive stats")
    horizon = serializers.IntegerField()
    comps = CompSerializer(many=True)
    gap_analysis = GapSerializer(many=True)


class OutcomeProbabilitySerializer(serializers.Serializer):
    outcome = serializers.CharField()
    label = serializers.CharField()
    probability = serializers.FloatField()
    p10 = serializers.FloatField(allow_null=True)
    p90 = serializers.FloatField(allow_null=True)
    comps_alone = serializers.FloatField(help_text="The same outcome read straight off the comps (backtested as the weaker estimate)")
    base_rate = serializers.FloatField(help_text="Share of players of that position and age who ended up here")


class ValueProjectionSerializer(serializers.Serializer):
    now_eur = serializers.FloatField()
    p10_eur = serializers.FloatField()
    p50_eur = serializers.FloatField()
    p90_eur = serializers.FloatField()
    ceiling_eur = serializers.FloatField(allow_null=True, help_text="Highest value in the data; projections are capped here")
    conditional_on = serializers.CharField()


class ForecastResponseSerializer(serializers.Serializer):
    player = TargetSerializer()
    horizon = serializers.IntegerField(help_text="Seasons ahead")
    as_of = serializers.IntegerField(help_text="Latest season of information used")
    retrospective = serializers.BooleanField(
        help_text="True when the outcome window is already complete, so this is not a true forecast")
    headline_source = serializers.CharField(help_text="'learned model' or 'comps + base rate' (defenders and goalkeepers)")
    range_kind = serializers.CharField()
    calibrated = serializers.BooleanField()
    probabilities = OutcomeProbabilitySerializer(many=True)
    value = ValueProjectionSerializer(allow_null=True)
    evidence_comps = CompSerializer(many=True)
    n_comps_used = serializers.IntegerField()
    caveats = serializers.ListField(child=serializers.CharField())


class LeagueStrengthSerializer(serializers.Serializer):
    league = serializers.CharField()
    factor = serializers.FloatField()
    ci_low = serializers.FloatField(allow_null=True)
    ci_high = serializers.FloatField(allow_null=True)
    n_obs = serializers.IntegerField()
    n_movers = serializers.IntegerField()


class MetaSerializer(serializers.Serializer):
    players = serializers.IntegerField()
    player_seasons = serializers.IntegerField()
    seasons = serializers.ListField(child=serializers.IntegerField())
    leagues = serializers.ListField(child=serializers.CharField())
    horizon = serializers.IntegerField()
    as_of = serializers.IntegerField()
    calibrated = serializers.BooleanField()
    forecast_bootstrap_fits = serializers.IntegerField()
    backtest_report = serializers.CharField(help_text="Path of the backtest report in the repository")


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    models_loaded = serializers.BooleanField()


# ---------------------------------------------------------------- value lens, aging, teams
class PricePointSerializer(serializers.Serializer):
    season = serializers.IntegerField()
    team = serializers.CharField(allow_null=True)
    market_value_eur = serializers.FloatField(allow_null=True)
    price_vs_output_pct = serializers.FloatField(
        allow_null=True, help_text="% by which his value sits below (negative) or above (positive) that of peers with the "
                                   "same output and age; null for seasons the lens does not cover")
    standing = serializers.CharField(allow_null=True)


class PlayerValueSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    name = serializers.CharField()
    position_group = serializers.CharField(allow_null=True)
    covered = serializers.BooleanField(help_text="False for defenders and goalkeepers, which the lens does not cover")
    seasons = PricePointSerializer(many=True)
    reading = serializers.CharField()


class AgingPointSerializer(serializers.Serializer):
    age = serializers.IntegerField()
    multiple_of_25 = serializers.FloatField()
    lo = serializers.FloatField(allow_null=True)
    hi = serializers.FloatField(allow_null=True)
    n_obs = serializers.IntegerField()


class AgingGroupSerializer(serializers.Serializer):
    position_group = serializers.CharField()
    label = serializers.CharField()
    plateau_from = serializers.IntegerField(help_text="Ages within 3% of the estimated maximum (smoothed)")
    plateau_to = serializers.IntegerField()
    points = AgingPointSerializer(many=True)


class AgingResponseSerializer(serializers.Serializer):
    groups = AgingGroupSerializer(many=True)
    notes = serializers.ListField(child=serializers.CharField())


class TeamSearchResultSerializer(serializers.Serializer):
    team = serializers.CharField()
    league = serializers.CharField()
    latest_season = serializers.IntegerField()


class TeamDimensionSerializer(serializers.Serializer):
    dimension = serializers.CharField()
    label = serializers.CharField()
    percentile = serializers.FloatField(help_text="Among the league's teams that season; higher is better")
    value = serializers.FloatField(allow_null=True, help_text="Raw per-match value (PPDA for pressing)")
    is_gap = serializers.BooleanField()
    noisy = serializers.BooleanField(help_text="Low season-to-season persistence: a gap here may be partly noise")


class TeamProfileSerializer(serializers.Serializer):
    team = serializers.CharField()
    league = serializers.CharField()
    season = serializers.IntegerField()
    points_per_match = serializers.FloatField()
    xpts_per_match = serializers.FloatField()
    xg_per_match = serializers.FloatField()
    xga_per_match = serializers.FloatField()
    dimensions = TeamDimensionSerializer(many=True)


class CandidateSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    name = serializers.CharField()
    team = serializers.CharField(allow_null=True)
    league = serializers.CharField()
    position_group = serializers.CharField()
    age = serializers.FloatField()
    age_note = serializers.CharField()
    minutes = serializers.FloatField()
    fit = serializers.FloatField(help_text="Mean percentile within position on the metrics that bear on the gap")
    market_value_eur = serializers.FloatField(allow_null=True)
    price_vs_output_pct = serializers.FloatField(allow_null=True)


class ShortlistResponseSerializer(serializers.Serializer):
    team = serializers.CharField()
    season = serializers.IntegerField()
    gap = TeamDimensionSerializer()
    mapped = serializers.BooleanField(help_text="False when no player metric can address this gap with the free data")
    note = serializers.CharField(allow_blank=True)
    ceiling_eur = serializers.FloatField(allow_null=True)
    candidates = CandidateSerializer(many=True)
    method = serializers.CharField()


# ---------------------------------------------------------------- outlook (fan chart)
class LevelPointSerializer(serializers.Serializer):
    season = serializers.IntegerField()
    level = serializers.FloatField(help_text="Position-specific composite percentile, 0-100")


class OutlookHorizonSerializer(serializers.Serializer):
    horizon = serializers.IntegerField(help_text="Seasons ahead")
    season = serializers.IntegerField(help_text="Start year of the season forecast")
    p10 = serializers.FloatField()
    p50 = serializers.FloatField()
    p90 = serializers.FloatField()
    p_observed = serializers.FloatField(help_text="Probability he is still a 900+ minute top-5-league player then; the band is conditional on it")


class OutlookResponseSerializer(serializers.Serializer):
    player = TargetSerializer()
    covered = serializers.BooleanField(help_text="False for defenders and goalkeepers (no composite level) and players below 900 minutes")
    level_now = serializers.FloatField(allow_null=True)
    history = LevelPointSerializer(many=True)
    horizons = OutlookHorizonSerializer(many=True)
    model = serializers.CharField()
    notes = serializers.ListField(child=serializers.CharField())
