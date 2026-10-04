import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { OutlookResponse } from "../../api/types";
import { level, pct, seasonLabel } from "../../lib/format";
import { COLOR, TICK } from "./theme";

export interface FanPoint {
  season: number;
  /** observed level (history) */
  level?: number;
  /** forecast median, starting from the current level so the fan grows out of the line */
  median?: number;
  /** [p10, p90] */
  band?: [number, number];
  pObserved?: number;
}

/** History points, then a fan that starts at today's level (zero width) and opens up over the horizons. */
export function fanData(o: Pick<OutlookResponse, "history" | "horizons" | "level_now" | "player">): FanPoint[] {
  const points = new Map<number, FanPoint>();
  for (const h of o.history) points.set(h.season, { season: h.season, level: h.level });
  const now = o.player.season;
  if (o.level_now !== null && o.level_now !== undefined) {
    points.set(now, { ...(points.get(now) ?? { season: now }), median: o.level_now, band: [o.level_now, o.level_now] });
  }
  for (const h of o.horizons) {
    points.set(h.season, { season: h.season, median: h.p50, band: [h.p10, h.p90], pObserved: h.p_observed });
  }
  return [...points.values()].sort((a, b) => a.season - b.season);
}

function FanTooltip({ active, payload }: { active?: boolean; payload?: ReadonlyArray<{ payload: FanPoint }> }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="card" style={{ padding: "0.5rem 0.75rem", margin: 0 }}>
      <strong>{seasonLabel(p.season)}</strong>
      <div className="small">
        {p.level !== undefined && <div>Level {level(p.level)}</div>}
        {p.band && p.pObserved !== undefined && (
          <>
            <div>
              Likely range {level(p.band[0])} to {level(p.band[1])} (median {level(p.median)})
            </div>
            <div className="muted">Chance still a top-5 regular: {pct(p.pObserved)}</div>
          </>
        )}
      </div>
    </div>
  );
}

export function FanChart({ outlook }: { outlook: OutlookResponse }) {
  const data = fanData(outlook);
  const seasons = data.map((d) => d.season);
  const last = outlook.horizons.at(-1);
  const summary = last
    ? `Level over time for ${outlook.player.name}: ${level(outlook.level_now)} now; in ${last.horizon} seasons likely between ${level(last.p10)} and ${level(last.p90)}.`
    : `Level over time for ${outlook.player.name}.`;

  return (
    <figure style={{ margin: 0 }}>
      <div className="chart" role="img" aria-label={summary} style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={COLOR.grid} vertical={false} />
            <XAxis dataKey="season" type="number" domain={[Math.min(...seasons), Math.max(...seasons)]} ticks={seasons} tickFormatter={(s: number) => `'${String(s % 100).padStart(2, "0")}`} tick={TICK} stroke={COLOR.axis} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={TICK} stroke={COLOR.axis} width={34} />
            <Tooltip content={<FanTooltip />} />
            <ReferenceLine x={outlook.player.season} stroke={COLOR.axis} />
            <Area dataKey="band" stroke="none" fill={COLOR.series} fillOpacity={0.16} isAnimationActive={false} connectNulls />
            <Line dataKey="median" stroke={COLOR.series} strokeWidth={1.6} strokeOpacity={0.75} dot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="level" stroke={COLOR.series} strokeWidth={2.4} dot={{ r: 3.5, fill: COLOR.series, stroke: "var(--surface)", strokeWidth: 1.5 }} isAnimationActive={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-note">
        Line: level so far (position-specific percentile). Shaded: likely 10 to 90% range for the next three seasons, if he is still getting 900+ minutes in the five
        leagues.
      </figcaption>
      <ul className="horizons" aria-label="Forecast by season">
        {outlook.horizons.map((h) => (
          <li key={h.horizon}>
            <span className="label">{seasonLabel(h.season)} (+{h.horizon})</span>
            <strong>
              {level(h.p10)} to {level(h.p90)}
            </strong>
            <span className="muted small"> median {level(h.p50)} · {pct(h.p_observed)} still a regular</span>
          </li>
        ))}
      </ul>
      <details>
        <summary>Show data table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Season</th>
                <th className="num">Level</th>
                <th className="num">Low (10%)</th>
                <th className="num">Median</th>
                <th className="num">High (90%)</th>
                <th className="num">Still a regular</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.season}>
                  <td>{seasonLabel(d.season)}</td>
                  <td className="num">{level(d.level)}</td>
                  <td className="num">{d.band && d.pObserved !== undefined ? level(d.band[0]) : "–"}</td>
                  <td className="num">{d.pObserved !== undefined ? level(d.median) : "–"}</td>
                  <td className="num">{d.band && d.pObserved !== undefined ? level(d.band[1]) : "–"}</td>
                  <td className="num">{pct(d.pObserved)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
