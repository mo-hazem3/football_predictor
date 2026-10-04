// Chart colours are CSS variables (see styles.css), so charts follow the light/dark theme without re-rendering logic.
export const COLOR = {
  series: "var(--series-1)",
  seriesSoft: "var(--series-1-soft)",
  accent: "var(--series-2)",
  pos: "var(--pos)",
  neg: "var(--neg)",
  grid: "var(--grid)",
  axis: "var(--axis)",
  muted: "var(--muted)",
  ink: "var(--ink)",
} as const;

export const TICK = { fill: "var(--muted)", fontSize: 12 } as const;
