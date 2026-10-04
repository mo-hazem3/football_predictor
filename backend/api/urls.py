from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("meta/", views.MetaView.as_view(), name="meta"),
    path("leagues/", views.LeagueStrengthView.as_view(), name="leagues"),
    path("players/search/", views.PlayerSearchView.as_view(), name="player-search"),
    path("players/<int:player_id>/", views.PlayerProfileView.as_view(), name="player-profile"),
    path("players/<int:player_id>/comps/", views.PlayerCompsView.as_view(), name="player-comps"),
    path("players/<int:player_id>/forecast/", views.PlayerForecastView.as_view(), name="player-forecast"),
]
