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
