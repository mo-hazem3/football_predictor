import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { COLOR, TICK } from "./theme";

export interface PercentileRow {
  label: string;
  value: number;
  isGap: boolean;
}

/** Percentile (0 to 100) bars; gaps (at or below the threshold) are red and the threshold is marked, so the colour is never the only cue. */
export function PercentileBars({ rows, threshold, ariaLabel }: { rows: PercentileRow[]; threshold: number; ariaLabel: string }) {
  return (
    <figure style={{ margin: 0 }}>
      <div className="chart" role="img" aria-label={ariaLabel} style={{ height: rows.length * 30 + 40 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 36, bottom: 4, left: 8 }} barCategoryGap={6}>
            <CartesianGrid stroke={COLOR.grid} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={TICK} stroke={COLOR.axis} />
            <YAxis type="category" dataKey="label" width={210} tick={TICK} stroke={COLOR.axis} />
            <ReferenceLine x={threshold} stroke={COLOR.neg} strokeOpacity={0.6} />
            <Tooltip formatter={(v) => [`${Math.round(Number(v))}th percentile`, ""]} separator="" />
            <Bar dataKey="value" radius={2} isAnimationActive={false} label={{ position: "right", fill: "var(--ink-2)", fontSize: 11, formatter: (v: unknown) => String(Math.round(Number(v))) }}>
              {rows.map((r) => (
                <Cell key={r.label} fill={r.isGap ? COLOR.neg : COLOR.series} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
