import pytest
from conftest import pick

pytestmark = pytest.mark.django_db(databases=["default", "pipeline"])


def get(client, url, **params):
    return client.get(url, params)


# ---------------------------------------------------------------- health, meta, leagues
def test_health_does_not_need_the_models(client):
    r = get(client, "/api/v1/health/")
    assert r.status_code == 200 and r.json() == {"status": "ok", "models_loaded": False}


def test_health_reports_loaded_models(client, service):
    assert get(client, "/api/v1/health/").json()["models_loaded"] is True


def test_meta_describes_coverage(client, service):
    j = get(client, "/api/v1/meta/").json()
    assert j["horizon"] == 3 and j["as_of"] == 2019 and j["seasons"] == [2016, 2017, 2018, 2019] and j["leagues"] == ["EPL"]
    assert j["players"] > 100 and j["calibrated"] is False


def test_league_strength_comes_from_the_pipeline_database(client, pipeline_tables):
    j = get(client, "/api/v1/leagues/").json()
    assert [(x["league"], x["factor"]) for x in j] == [("EPL", 0.85), ("Ligue_1", 1.09)]   # ordered by factor, hardest first
    assert j[0]["ci_low"] == 0.82 and j[0]["n_movers"] == 903


# ---------------------------------------------------------------- search
def test_search_is_accent_insensitive_and_returns_the_latest_season(client, service):
    j = get(client, "/api/v1/players/search/", q="alvaro").json()
    assert j and j[0]["name"].startswith("Player 7") and j[0]["latest_season"] <= 2019
    assert set(j[0]) == {"player_id", "name", "latest_season", "team", "league", "position_group", "age", "minutes"}


def test_search_validates_its_input(client, service):
    assert get(client, "/api/v1/players/search/", q="a").status_code == 400
    assert get(client, "/api/v1/players/search/").status_code == 400
    assert get(client, "/api/v1/players/search/", q="player", limit=100).status_code == 400
    assert get(client, "/api/v1/players/search/", q="player", limit="x").status_code == 400
    assert len(get(client, "/api/v1/players/search/", q="player", limit=3).json()) == 3


def test_search_with_no_match_is_an_empty_list(client, service):
    assert get(client, "/api/v1/players/search/", q="zzzzzz").json() == []


# ---------------------------------------------------------------- profile
def test_profile_has_seasons_percentiles_and_transfermarkt_bio(client, service, pipeline_tables):
    j = get(client, "/api/v1/players/4/").json()
    assert j["name"].startswith("Player 4") and j["tm_player_id"] == 1004
    assert j["birth_date"] == "2001-05-17" and j["nationalities"] == ["Egypt", "France"] and j["height_cm"] == 181
    assert len(j["seasons"]) >= 2 and j["seasons"] == sorted(j["seasons"], key=lambda s: s["season"])
    ranked = [s for s in j["seasons"] if s["percentiles"]]
    assert ranked and all(0 <= v <= 100 for v in ranked[0]["percentiles"].values())
    assert "npxg_p90" in j["seasons"][0]["per90"]


def test_profile_without_a_transfermarkt_link_still_works(client, service, pipeline_tables):
    j = get(client, "/api/v1/players/5/").json()      # no squad row inserted for this one
    assert j["birth_date"] is None and j["nationalities"] == [] and j["seasons"]


def test_unknown_player_is_a_404_with_a_message(client, service):
    r = get(client, "/api/v1/players/999999/")
    assert r.status_code == 404 and "999999" in r.json()["detail"]


# ---------------------------------------------------------------- comps
def test_comps_are_ordered_by_distance_exclude_the_target_and_carry_outcomes(client, service):
    pid, season = pick(service, "MID")
    j = get(client, f"/api/v1/players/{pid}/comps/", k=6).json()
    assert j["target"]["player_id"] == pid and j["target"]["season"] == season and j["horizon"] == 3
    d = [c["distance"] for c in j["comps"]]
    assert 1 <= len(d) <= 6 and d == sorted(d) and pid not in {c["player_id"] for c in j["comps"]}
    assert len({c["player_id"] for c in j["comps"]}) == len(j["comps"])           # one row per distinct player
    assert {"outcome", "value_ratio", "per90"} <= set(j["comps"][0])
    assert j["features_used"] and all(g["metric"] for g in j["gap_analysis"])


def test_comps_outcomes_are_withheld_until_the_window_has_finished(client, service):
    pid, _ = pick(service, "FWD")
    comps = get(client, f"/api/v1/players/{pid}/comps/", k=20).json()["comps"]
    for c in comps:
        assert (c["outcome"] is None) == (c["season"] + 3 > 2019)       # as_of is 2019: a 2017+ comp has no outcome yet


@pytest.mark.parametrize("params", [{"k": 0}, {"k": 51}, {"k": "x"}, {"season": "abc"}])
def test_comps_reject_bad_parameters(client, service, params):
    pid, _ = pick(service, "FWD")
    assert get(client, f"/api/v1/players/{pid}/comps/", **params).status_code == 400


def test_comps_for_a_season_without_a_ranked_row_is_a_404(client, service):
    pid, _ = pick(service, "FWD")
    r = get(client, f"/api/v1/players/{pid}/comps/", season=2000)
    assert r.status_code == 404 and "2000" in r.json()["detail"]


# ---------------------------------------------------------------- forecast
def test_forecast_for_an_attacker_uses_the_learned_model(client, service):
    pid, season = pick(service, "FWD")
    j = get(client, f"/api/v1/players/{pid}/forecast/").json()
    assert j["headline_source"] == "learned model" and j["retrospective"] is False and j["calibrated"] is False
    assert [p["outcome"] for p in j["probabilities"]] == ["out", "regular", "good", "elite"]
    assert sum(p["probability"] for p in j["probabilities"]) == pytest.approx(1.0)
    assert all(p["p10"] <= p["p90"] for p in j["probabilities"]) and j["caveats"]
    assert len(j["evidence_comps"]) <= 10 and j["n_comps_used"] >= 1
    assert j["player"]["season"] == season


def test_forecast_for_a_defender_falls_back_to_comps_and_base_rate(client, service):
    pid, _ = pick(service, "DEF")
    j = get(client, f"/api/v1/players/{pid}/forecast/").json()
    assert j["headline_source"] == "comps + base rate"
    assert [p["outcome"] for p in j["probabilities"]] == ["out", "retained"] and j["calibrated"] is False


def test_forecast_flags_a_season_whose_outcome_is_already_known_as_retrospective(client, service):
    pid, _ = pick(service, "FWD", season=2016)
    assert get(client, f"/api/v1/players/{pid}/forecast/", season=2016).json()["retrospective"] is True


def test_forecast_only_offers_the_fitted_horizon(client, service):
    pid, _ = pick(service, "FWD")
    assert get(client, f"/api/v1/players/{pid}/forecast/", horizon=2).status_code == 400
    assert get(client, f"/api/v1/players/{pid}/forecast/", horizon=3).status_code == 200


def test_forecast_value_range_is_ordered_and_capped(client, service):
    pid, _ = pick(service, "FWD")
    v = get(client, f"/api/v1/players/{pid}/forecast/").json()["value"]
    if v is not None:                                              # a value needs a market value and enough value history
        assert v["p10_eur"] <= v["p50_eur"] <= v["p90_eur"] <= v["ceiling_eur"]


# ---------------------------------------------------------------- outlook (fan chart)
def test_outlook_gives_an_ordered_bounded_band_for_each_of_the_next_three_seasons(client, service):
    pid, season = pick(service, "FWD")
    j = get(client, f"/api/v1/players/{pid}/outlook/").json()
    assert j["covered"] is True and j["player"]["season"] == season and 0 <= j["level_now"] <= 100
    assert [h["horizon"] for h in j["horizons"]] == [1, 2, 3] and [h["season"] for h in j["horizons"]] == [season + 1, season + 2, season + 3]
    for h in j["horizons"]:
        assert 0 <= h["p10"] <= h["p50"] <= h["p90"] <= 100 and 0 < h["p_observed"] < 1
    assert j["history"] == sorted(j["history"], key=lambda p: p["season"])
    assert j["history"][-1] == {"season": season, "level": j["level_now"]}          # the chart ends at the current level
    assert any("conditional" in n for n in j["notes"])


def test_outlook_does_not_cover_defenders_and_says_why(client, service):
    pid, _ = pick(service, "DEF")
    j = get(client, f"/api/v1/players/{pid}/outlook/").json()
    assert j["covered"] is False and j["horizons"] == [] and j["level_now"] is None and "defenders" in j["notes"][0]


def test_outlook_for_a_played_season_is_labelled_retrospective(client, service):
    pid, _ = pick(service, "FWD", season=2016)
    notes = get(client, f"/api/v1/players/{pid}/outlook/", season=2016).json()["notes"]
    assert "retrospective" in notes[0]


def test_outlook_errors(client, service):
    assert get(client, "/api/v1/players/999999/outlook/").status_code == 404
    pid, _ = pick(service, "FWD")
    assert get(client, f"/api/v1/players/{pid}/outlook/", season="x").status_code == 400
    assert get(client, f"/api/v1/players/{pid}/outlook/", season=2000).status_code == 404


# ---------------------------------------------------------------- value lens, aging
def test_value_lens_covers_attackers_and_midfielders_only(client, service):
    fwd, _ = pick(service, "FWD")
    j = get(client, f"/api/v1/players/{fwd}/value/").json()
    assert j["covered"] is True and any(s["price_vs_output_pct"] is not None for s in j["seasons"])
    assert {s["standing"] for s in j["seasons"] if s["standing"]} <= {
        "among the most underpriced 10%", "underpriced", "fairly priced", "overpriced", "among the most overpriced 10%"}
    dfd, _ = pick(service, "DEF")
    j = get(client, f"/api/v1/players/{dfd}/value/").json()
    assert j["covered"] is False and all(s["price_vs_output_pct"] is None for s in j["seasons"])


def test_aging_curves_report_a_plateau_and_only_well_supported_ages(client, service):
    j = get(client, "/api/v1/aging/").json()
    assert {g["position_group"] for g in j["groups"]} <= {"FWD", "WING_AM", "MID", "DEF"} and j["groups"] and j["notes"]
    for g in j["groups"]:
        assert g["plateau_from"] <= g["plateau_to"] and g["points"]
        assert all(p["n_obs"] >= 4 for p in g["points"])      # AGING_MIN_OBS in the test settings
        assert all(p["lo"] is None or p["lo"] <= p["hi"] for p in g["points"])       # a percentile band need not contain the estimate


# ---------------------------------------------------------------- teams
def test_team_search_and_profile(client, service):
    assert [t["team"] for t in get(client, "/api/v1/teams/search/", q="alp").json()] == ["Alpha FC"]
    j = get(client, "/api/v1/teams/profile/", team="alpha fc", season=2019).json()           # case-insensitive
    assert j["team"] == "Alpha FC" and j["season"] == 2019 and len(j["dimensions"]) == 10
    assert all(0 <= d["percentile"] <= 100 for d in j["dimensions"])
    assert {d["dimension"] for d in j["dimensions"] if d["noisy"]} == {"transition_xg", "set_piece_xg"}
    assert j["dimensions"][0]["is_gap"] == (j["dimensions"][0]["percentile"] <= 25)


def test_team_profile_errors_are_specific(client, service):
    assert get(client, "/api/v1/teams/profile/").status_code == 400
    assert get(client, "/api/v1/teams/profile/", team="Nowhere FC").status_code == 404
    assert get(client, "/api/v1/teams/profile/", team="Alpha FC", season=2010).status_code == 404
    assert get(client, "/api/v1/teams/profile/", team="Alpha FC", threshold=99).status_code == 400


def test_shortlist_respects_budget_age_and_excludes_the_teams_own_players(client, service):
    j = get(client, "/api/v1/teams/shortlist/", team="Delta FC", season=2019, gap="open_play_xg", n=5, max_value_m=30, max_age=27).json()
    assert j["mapped"] is True and j["gap"]["dimension"] == "open_play_xg" and j["ceiling_eur"] == 30e6
    for c in j["candidates"]:
        assert c["team"] != "Delta FC" and c["age"] <= 27 and c["market_value_eur"] <= 30e6 and c["position_group"] in {"WING_AM", "MID", "FWD"}
    assert [c["fit"] for c in j["candidates"]] == sorted((c["fit"] for c in j["candidates"]), reverse=True)


def test_shortlist_defaults_to_the_weakest_gap_and_the_squads_own_scale(client, service):
    j = get(client, "/api/v1/teams/shortlist/", team="Delta FC", season=2019).json()
    dims = get(client, "/api/v1/teams/profile/", team="Delta FC", season=2019).json()["dimensions"]
    assert j["gap"]["percentile"] == min(d["percentile"] for d in dims) and j["ceiling_eur"] > 0 and j["method"]


def test_shortlist_says_so_when_a_gap_cannot_be_mapped(client, service):
    j = get(client, "/api/v1/teams/shortlist/", team="Delta FC", season=2019, gap="set_piece_xga").json()
    assert j["mapped"] is False and j["candidates"] == [] and "aerial" in j["note"]


def test_shortlist_validates_its_parameters(client, service):
    assert get(client, "/api/v1/teams/shortlist/", team="Delta FC", gap="not_a_dimension").status_code == 400
    assert get(client, "/api/v1/teams/shortlist/", team="Delta FC", max_value_m="lots").status_code == 400
    assert get(client, "/api/v1/teams/shortlist/", team="Delta FC", n=99).status_code == 400


# ---------------------------------------------------------------- contract
def test_every_endpoint_is_documented_in_the_openapi_schema(client):
    r = client.get("/api/schema/", {"format": "json"})
    assert r.status_code == 200
    paths = set(r.json()["paths"])
    for p in ("/api/v1/players/search/", "/api/v1/players/{player_id}/", "/api/v1/players/{player_id}/comps/",
              "/api/v1/players/{player_id}/forecast/", "/api/v1/players/{player_id}/value/", "/api/v1/players/{player_id}/outlook/", "/api/v1/aging/",
              "/api/v1/teams/profile/", "/api/v1/teams/shortlist/", "/api/v1/leagues/", "/api/v1/meta/", "/api/v1/health/"):
        assert p in paths


def test_the_api_is_read_only(client, service):
    for url in ("/api/v1/players/search/", "/api/v1/meta/"):
        assert client.post(url, {}).status_code == 405 and client.delete(url).status_code == 405


def test_cors_allows_the_frontend_origin_only(client):
    ok = client.get("/api/v1/health/", HTTP_ORIGIN="http://localhost:5173")
    bad = client.get("/api/v1/health/", HTTP_ORIGIN="http://evil.example")
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in bad.headers


def test_outlook_defaults_to_the_latest_season_with_enough_minutes_and_says_so(client, service):
    """A player with a short latest season (injury) still gets an outlook, from the season before."""
    pid, season = pick(service, "FWD")
    eng_d, rows = service.engine.d, service.outlook_rows
    short = eng_d[(eng_d.player_id == pid) & (eng_d.season == season)].index
    assert len(short) == 1
    saved = rows.copy()
    try:
        service.outlook_rows = rows.drop(index=(pid, season))        # as if that season had too few minutes to be a model row
        j = get(client, f"/api/v1/players/{pid}/outlook/").json()
        if j["covered"]:                                              # he has an earlier qualifying season in the synthetic world
            assert j["player"]["season"] < season and "fewer than 900 minutes" in j["notes"][0] + j["notes"][-1] + " ".join(j["notes"])
        else:
            assert "below the 900" in j["notes"][0]
    finally:
        service.outlook_rows = saved
