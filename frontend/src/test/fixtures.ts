import type { ForecastResponse, CompsResponse, OutlookResponse, PlayerProfile, PlayerValue, Target } from "../api/types";

export const target: Target = { player_id: 7, name: "Test Winger", season: 2024, league: "EPL", team: "Alpha FC", position_group: "WING_AM", age: 22.4, minutes: 2400 };

export const profile: PlayerProfile = {
  player_id: 7,
  name: "Test Winger",
  position_group: "WING_AM",
  tm_player_id: 1007,
  birth_date: "2002-05-17",
  nationalities: ["Egypt", "France"],
  height_cm: 181,
  foot: "right",
  tm_position: "Left Winger",
  latest_season: 2024,
  seasons: [
    { season: 2023, league: "EPL", team: "Alpha FC", position_group: "WING_AM", age: 21.4, minutes: 1800, games: 24, market_value_eur: 12_000_000, per90: { npxg_p90_adj: 0.21, xa_p90_adj: 0.18, tackles_won_p90: 0.9 }, percentiles: { npxg_pct_global: 71 } },
    { season: 2024, league: "EPL", team: "Alpha FC", position_group: "WING_AM", age: 22.4, minutes: 2400, games: 31, market_value_eur: 30_000_000, per90: { npxg_p90_adj: 0.3, xa_p90_adj: 0.25, tackles_won_p90: null }, percentiles: { npxg_pct_global: 88 } },
  ],
};

export const outlook: OutlookResponse = {
  player: target,
  covered: true,
  level_now: 88,
  history: [
    { season: 2023, level: 71 },
    { season: 2024, level: 88 },
  ],
  horizons: [
    { horizon: 1, season: 2025, p10: 70, p50: 86, p90: 95, p_observed: 0.96 },
    { horizon: 2, season: 2026, p10: 62, p50: 84, p90: 95, p_observed: 0.93 },
    { horizon: 3, season: 2027, p10: 55, p50: 82, p90: 94, p_observed: 0.9 },
  ],
  model: "gradient-boosted quantile regression",
  notes: ["Level is ...", "The band is conditional ...", "Backtested ..."],
};

export const comps: CompsResponse = {
  target,
  features_used: ["npxg_p90_adj", "xa_p90_adj"],
  horizon: 3,
  comps: [
    { player_id: 20, name: "Past Star", season: 2018, league: "La_liga", team: "Beta FC", age: 22.1, minutes: 2500, distance: 0.8, outcome: "elite", value_ratio: 2.4, per90: {} },
    { player_id: 21, name: "Recent Kid", season: 2024, league: "Bundesliga", team: "Gamma FC", age: 22.0, minutes: 2000, distance: 1.1, outcome: null, value_ratio: null, per90: {} },
  ],
  gap_analysis: [
    { metric: "tackles_won", label: "Tackles won", target_pct: 20, comp_median_pct: 50, comp_p25: 40, comp_p75: 60, gap: -30, flag: "weakness", n_comps: 10 },
    { metric: "xa", label: "Expected assists", target_pct: 90, comp_median_pct: 70, comp_p25: 60, comp_p75: 80, gap: 20, flag: "strength", n_comps: 10 },
  ],
};

export const forecast: ForecastResponse = {
  player: target,
  horizon: 3,
  as_of: 2025,
  retrospective: false,
  headline_source: "learned model",
  range_kind: "10-90% across bootstrap refits",
  calibrated: true,
  probabilities: [
    { outcome: "out", label: "Out", probability: 0.004, p10: 0.001, p90: 0.006, comps_alone: 0.12, base_rate: 0.13 },
    { outcome: "regular", label: "Regular", probability: 0.2, p10: 0.15, p90: 0.25, comps_alone: 0.48, base_rate: 0.5 },
    { outcome: "good", label: "Good", probability: 0.4, p10: 0.3, p90: 0.5, comps_alone: 0.3, base_rate: 0.25 },
    { outcome: "elite", label: "Elite", probability: 0.396, p10: 0.3, p90: 0.5, comps_alone: 0.1, base_rate: 0.07 },
  ],
  value: { now_eur: 30_000_000, p10_eur: 28_000_000, p50_eur: 45_000_000, p90_eur: 90_000_000, ceiling_eur: 200_000_000, conditional_on: "staying on a top-5-league squad" },
  evidence_comps: comps.comps,
  n_comps_used: 23,
  caveats: ["Outcomes are measured in the five covered leagues only."],
};

export const value: PlayerValue = {
  player_id: 7,
  name: "Test Winger",
  position_group: "WING_AM",
  covered: true,
  seasons: [
    { season: 2023, team: "Alpha FC", market_value_eur: 12_000_000, price_vs_output_pct: -35, standing: "underpriced" },
    { season: 2024, team: "Alpha FC", market_value_eur: 30_000_000, price_vs_output_pct: 5, standing: "fairly priced" },
  ],
  reading: "Negative = priced below peers with the same output and age.",
};

export const defenderOutlook: OutlookResponse = {
  player: { ...target, position_group: "DEF", name: "Test Defender" },
  covered: false,
  level_now: null,
  history: [],
  horizons: [],
  model: "gradient-boosted quantile regression",
  notes: ["No outlook: it covers forwards, wingers and midfielders with 900+ minutes in the season (defenders and goalkeepers have no composite level).", "x", "y", "z"],
};
