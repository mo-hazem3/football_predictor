/** Display helpers. Kept pure so they are trivially testable. */

export const POSITION_LABELS: Record<string, string> = {
  GK: "Goalkeeper",
  DEF: "Defender",
  MID: "Midfielder",
  WING_AM: "Winger / attacking mid",
  FWD: "Forward",
};

export const LEAGUE_LABELS: Record<string, string> = {
  EPL: "Premier League",
  La_liga: "La Liga",
  Bundesliga: "Bundesliga",
  Serie_A: "Serie A",
  Ligue_1: "Ligue 1",
};

export const positionLabel = (g: string | null | undefined) => (g ? (POSITION_LABELS[g] ?? g) : "Unknown position");
export const leagueLabel = (l: string) => LEAGUE_LABELS[l] ?? l.replace(/_/g, " ");

/** 2024 -> "2024/25" */
export const seasonLabel = (start: number) => `${start}/${String((start + 1) % 100).padStart(2, "0")}`;

/** 0.973 -> "97%", 0.004 -> "<1%", 0.1234 with digits=1 -> "12.3%" */
export function pct(p: number | null | undefined, digits = 0): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "–";
  if (p > 0 && p < 0.01 && digits === 0) return "<1%";
  return `${(p * 100).toFixed(digits)}%`;
}

/** 45_000_000 -> "€45m", 1_460_000_000 -> "€1.5bn", 800_000 -> "€800k" */
export function eur(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `€${(value / 1e9).toFixed(1)}bn`;
  if (abs >= 1e7) return `€${Math.round(value / 1e6)}m`;
  if (abs >= 1e6) return `€${(value / 1e6).toFixed(1)}m`;
  if (abs >= 1e3) return `€${Math.round(value / 1e3)}k`;
  return `€${Math.round(value)}`;
}

/** Understat joins a mid-season mover's clubs with a bare comma: 'Brentford,Manchester United' -> 'Brentford / Manchester United'. */
export const teamLabel = (t: string | null | undefined) => (t ? t.split(",").map((x) => x.trim()).join(" / ") : "–");

export const level = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? "–" : String(Math.round(x)));

export function signed(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const s = x.toFixed(digits);
  return x > 0 ? `+${s}` : s;
}

/** Percentile column names carry their scope: *_pct_global = across leagues on adjusted rates, *_pct_league = within league. */
export function metricLabel(key: string): string {
  const base = key.replace(/_pct_(global|league)$/, "").replace(/_p90(_adj)?$/, "");
  const names: Record<string, string> = {
    npxg: "Non-penalty xG",
    xa: "Expected assists",
    shots: "Shots",
    key_passes: "Key passes",
    xg_chain: "xG chain",
    xg_buildup: "xG build-up",
    tackles_won: "Tackles won",
    interceptions: "Interceptions",
    crosses: "Crosses",
    fouls: "Fouls committed",
    fouled: "Fouls drawn",
    goals: "Goals",
    assists: "Assists",
    gk_sota: "Shots on target faced",
    save_pct: "Save %",
  };
  return names[base] ?? base.replace(/_/g, " ");
}

/** Outcome tiers in display order with plain-language labels. */
export const OUTCOME_LABELS: Record<string, string> = {
  elite: "Elite (top 10%)",
  good: "Good (top 25%)",
  regular: "Regular starter",
  retained: "Still a regular",
  out: "Out of the top 5",
};
export const outcomeLabel = (o: string | null | undefined) => (o ? (OUTCOME_LABELS[o] ?? o) : "Not yet known");
