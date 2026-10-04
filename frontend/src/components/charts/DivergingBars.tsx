import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { signed } from "../../lib/format";
import { COLOR, TICK } from "./theme";

export interface DivergingRow {
  label: string;
  value: number;
}

/** Symmetric axis limit rounded up to a multiple of 10, so the zero line sits in the middle and bars are comparable. */
export function symmetricLimit(values: number[], step = 10, min = 20): number {
  const m = Math.max(min, ...values.map((v) => Math.abs(v)));
  return Math.ceil(m / step) * step;
}

/** Horizontal bars left (below) or right (above) of zero. Blue = above the reference, red = below; the sign is also in the label. */
export function DivergingBars({ rows, unit, ariaLabel, legend }: { rows: DivergingRow[]; unit: string; ariaLabel: string; legend: { above: string; below: string } }) {
  const lim = symmetricLimit(rows.map((r) => r.value));
  return (
    <figure style={{ margin: 0 }}>
      <div className="chart" role="img" aria-label={ariaLabel} style={{ height: Math.max(160, rows.length * 30 + 40) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 36, bottom: 4, left: 8 }} barCategoryGap={6}>
            <CartesianGrid stroke={COLOR.grid} horizontal={false} />
            <XAxis type="number" domain={[-lim, lim]} tick={TICK} stroke={COLOR.axis} tickFormatter={(v: number) => signed(v)} />
            <YAxis type="category" dataKey="label" width={150} tick={TICK} stroke={COLOR.axis} />
            <ReferenceLine x={0} stroke={COLOR.axis} />
            <Tooltip formatter={(v) => [`${signed(Number(v))} ${unit}`, ""]} separator="" />
            <Bar dataKey="value" radius={2} isAnimationActive={false} label={{ position: "right", fill: "var(--ink-2)", fontSize: 11, formatter: (v: unknown) => signed(Number(v)) }}>
              {rows.map((r) => (
                <Cell key={r.label} fill={r.value >= 0 ? COLOR.pos : COLOR.neg} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="legend" aria-hidden="true">
        <span>
          <span className="swatch" style={{ background: "var(--pos)" }} />
          {legend.above}
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--neg)" }} />
          {legend.below}
        </span>
      </div>
    </figure>
  );
}
