from django.urls import path

from . import views, views_insight

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("meta/", views.MetaView.as_view(), name="meta"),
    path("leagues/", views.LeagueStrengthView.as_view(), name="leagues"),
    path("aging/", views_insight.AgingView.as_view(), name="aging"),
    path("players/search/", views.PlayerSearchView.as_view(), name="player-search"),
    path("players/<int:player_id>/", views.PlayerProfileView.as_view(), name="player-profile"),
    path("players/<int:player_id>/comps/", views.PlayerCompsView.as_view(), name="player-comps"),
    path("players/<int:player_id>/forecast/", views.PlayerForecastView.as_view(), name="player-forecast"),
    path("players/<int:player_id>/value/", views_insight.PlayerValueView.as_view(), name="player-value"),
    path("players/<int:player_id>/outlook/", views_insight.PlayerOutlookView.as_view(), name="player-outlook"),
    path("teams/search/", views_insight.TeamSearchView.as_view(), name="team-search"),
    path("teams/profile/", views_insight.TeamProfileView.as_view(), name="team-profile"),
    path("teams/shortlist/", views_insight.TeamShortlistView.as_view(), name="team-shortlist"),
]
