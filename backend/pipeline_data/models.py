"""Unmanaged models over the data pipeline's SQLite tables (read-only).

The pipeline tables have composite natural keys and no integer id, so every model uses SQLite's
implicit `rowid` as its primary key. Only the columns the API and admin need are declared;
the feature table alone has 83 columns.
"""
from django.db import models


class PipelineTable(models.Model):
    id = models.IntegerField(primary_key=True, db_column="rowid")

    class Meta:
        abstract = True
        managed = False


class PlayerSeason(PipelineTable):
    """One row per Understat player-season: identity, age, position, per-90 rates, percentiles."""

    player_id = models.IntegerField(help_text="Understat player id")
    player_name = models.TextField()
    league = models.TextField()
    season = models.IntegerField(help_text="Start year: 2023 = 2023/24")
    team = models.TextField(null=True)
    position_group = models.TextField(null=True)
    age = models.FloatField(null=True)
    minutes = models.FloatField()
    tm_player_id = models.IntegerField(null=True, help_text="Linked Transfermarkt player id")
    npxg_p90 = models.FloatField(null=True)
    xa_p90 = models.FloatField(null=True)
    npxg_pct_global = models.FloatField(null=True)
    xa_pct_global = models.FloatField(null=True)

    class Meta(PipelineTable.Meta):
        db_table = "player_season_features"
        ordering = ["-season", "player_name"]

    def __str__(self):
        return f"{self.player_name} {self.season} ({self.league})"


class LeagueStrength(PipelineTable):
    league = models.TextField()
    factor = models.FloatField(help_text="Same player's attacking output per 90 relative to the five-league average")
    ci_low = models.FloatField(null=True)
    ci_high = models.FloatField(null=True)
    n_obs = models.IntegerField()
    n_movers = models.IntegerField()

    class Meta(PipelineTable.Meta):
        db_table = "league_strength"
        ordering = ["factor"]

    def __str__(self):
        return f"{self.league}: {self.factor:.3f}"


class TransfermarktSquad(PipelineTable):
    tm_player_id = models.IntegerField()
    season = models.IntegerField()
    league = models.TextField()
    club_id = models.IntegerField()
    club_name = models.TextField()
    player_name = models.TextField()
    position = models.TextField(null=True)
    birth_date = models.TextField(null=True)
    nationality = models.TextField(null=True)
    nationalities = models.TextField(null=True, help_text="All nationalities, '|' separated")
    height_cm = models.IntegerField(null=True)
    foot = models.TextField(null=True)
    market_value_eur = models.IntegerField(null=True, help_text="Season-end snapshot")

    class Meta(PipelineTable.Meta):
        db_table = "transfermarkt_squads"
        ordering = ["-season", "club_name", "player_name"]

    def __str__(self):
        return f"{self.player_name} {self.season} ({self.club_name})"


class UnderstatLink(PipelineTable):
    understat_player_id = models.IntegerField()
    tm_player_id = models.IntegerField()
    league = models.TextField()
    season = models.IntegerField()
    score = models.FloatField()
    stage = models.TextField(help_text="'name' = global name match, 'club' = relaxed match inside a learned club")

    class Meta(PipelineTable.Meta):
        db_table = "understat_tm_links"
        ordering = ["-season", "league"]


class Transfer(PipelineTable):
    tm_player_id = models.IntegerField()
    transfer_id = models.IntegerField()
    date = models.TextField(null=True)
    season = models.TextField(null=True)
    from_club = models.TextField(null=True)
    to_club = models.TextField(null=True)
    fee_text = models.TextField(null=True)
    fee_eur = models.IntegerField(null=True)
    market_value_eur = models.IntegerField(null=True)

    class Meta(PipelineTable.Meta):
        db_table = "transfermarkt_transfers"
        ordering = ["-date"]


class MarketValue(PipelineTable):
    tm_player_id = models.IntegerField()
    date = models.TextField()
    value_eur = models.IntegerField()
    club = models.TextField(null=True)
    age = models.IntegerField(null=True)

    class Meta(PipelineTable.Meta):
        db_table = "transfermarkt_market_values"
        ordering = ["tm_player_id", "date"]
