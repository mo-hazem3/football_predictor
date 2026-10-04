import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { AgingGroup } from "../../api/types";
import { COLOR, TICK } from "./theme";

interface Point {
  age: number;
  multiple: number;
  band: [number, number] | null;
}

export function agingData(group: AgingGroup): Point[] {
  return group.points.map((p) => ({ age: p.age, multiple: p.multiple_of_25, band: p.lo !== null && p.lo !== undefined && p.hi !== null && p.hi !== undefined ? [p.lo, p.hi] : null }));
}

/** One position's curve: output at each age as a multiple of the same player's output at 25, with the plateau shaded. */
export function AgingChart({ group }: { group: AgingGroup }) {
  const data = agingData(group);
  return (
    <figure style={{ margin: 0 }}>
      <h3>{group.label}</h3>
      <div className="chart" role="img" aria-label={`${group.label}: output stays within 3% of its maximum from age ${group.plateau_from} to ${group.plateau_to}.`} style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 2, left: 0 }}>
            <CartesianGrid stroke={COLOR.grid} vertical={false} />
            <XAxis dataKey="age" type="number" domain={["dataMin", "dataMax"]} ticks={[20, 25, 30, 35]} tick={TICK} stroke={COLOR.axis} />
            <YAxis domain={[0.5, 1.3]} ticks={[0.6, 0.8, 1, 1.2]} tick={TICK} stroke={COLOR.axis} width={34} tickFormatter={(v: number) => `${v}×`} />
            <ReferenceArea x1={group.plateau_from} x2={group.plateau_to} fill={COLOR.seriesSoft} strokeOpacity={0} />
            <ReferenceLine y={1} stroke={COLOR.axis} />
            <Tooltip formatter={(v) => (Array.isArray(v) ? `${Number(v[0]).toFixed(2)}× to ${Number(v[1]).toFixed(2)}×` : `${Number(v).toFixed(2)}×`)} labelFormatter={(a) => `Age ${a}`} />
            <Area dataKey="band" stroke="none" fill={COLOR.series} fillOpacity={0.16} isAnimationActive={false} connectNulls />
            <Line dataKey="multiple" stroke={COLOR.series} strokeWidth={2.2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-note">Shaded columns: ages within 3% of the top (ages {group.plateau_from} to {group.plateau_to}).</figcaption>
    </figure>
  );
}
