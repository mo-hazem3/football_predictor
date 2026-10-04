"""Read-only admin for browsing pipeline output: check links, spot-check a player, inspect league factors."""
from django.contrib import admin

from .models import LeagueStrength, MarketValue, PlayerSeason, Transfer, TransfermarktSquad, UnderstatLink


class ReadOnlyAdmin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = False  # COUNT(*) over tens of thousands of rows is wasted work per page

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlayerSeason)
class PlayerSeasonAdmin(ReadOnlyAdmin):
    list_display = ("player_name", "season", "league", "team", "position_group", "age", "minutes", "tm_player_id")
    list_filter = ("league", "season", "position_group")
    search_fields = ("player_name", "team")


@admin.register(LeagueStrength)
class LeagueStrengthAdmin(ReadOnlyAdmin):
    list_display = ("league", "factor", "ci_low", "ci_high", "n_obs", "n_movers")


@admin.register(TransfermarktSquad)
class TransfermarktSquadAdmin(ReadOnlyAdmin):
    list_display = ("player_name", "season", "club_name", "league", "position", "birth_date", "nationality", "market_value_eur")
    list_filter = ("league", "season")
    search_fields = ("player_name", "club_name")


@admin.register(UnderstatLink)
class UnderstatLinkAdmin(ReadOnlyAdmin):
    """Browse entity-resolution output; filter by stage='club' to review the relaxed matches."""

    list_display = ("understat_player_id", "tm_player_id", "league", "season", "score", "stage")
    list_filter = ("stage", "league", "season")
    search_fields = ("understat_player_id", "tm_player_id")


@admin.register(Transfer)
class TransferAdmin(ReadOnlyAdmin):
    list_display = ("tm_player_id", "date", "from_club", "to_club", "fee_text")
    search_fields = ("from_club", "to_club")


@admin.register(MarketValue)
class MarketValueAdmin(ReadOnlyAdmin):
    list_display = ("tm_player_id", "date", "value_eur", "club", "age")
    search_fields = ("club",)
