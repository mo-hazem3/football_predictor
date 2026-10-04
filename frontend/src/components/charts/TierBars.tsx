import type { OutcomeProbability } from "../../api/types";
import { outcomeLabel, pct } from "../../lib/format";

/** Outcome probabilities best-first (the API returns worst-first). */
export function orderTiers(rows: OutcomeProbability[]): OutcomeProbability[] {
  return [...rows].reverse();
}

export function TierBars({ rows, modelUncertainty }: { rows: OutcomeProbability[]; modelUncertainty: boolean }) {
  return (
    <figure style={{ margin: 0 }}>
      <div role="list" aria-label="Outcome probabilities">
        {orderTiers(rows).map((r) => {
          const lo = r.p10 ?? r.probability;   // the range is null when the model gives none
          const hi = r.p90 ?? r.probability;
          return (
          <div className="tier" role="listitem" key={r.outcome}>
            <span className="name">{outcomeLabel(r.outcome)}</span>
            <div className="track" aria-hidden="true">
              <div className="fill" style={{ width: `${r.probability * 100}%` }} />
              <div className="range" style={{ left: `${lo * 100}%`, width: `${Math.max(hi - lo, 0) * 100}%` }} />
              <div className="comps-mark" style={{ left: `calc(${r.comps_alone * 100}% - 1px)` }} />
            </div>
            <span className="value">
              <strong>{pct(r.probability)}</strong> <span className="muted small">({pct(lo)} to {pct(hi)})</span>
            </span>
          </div>
          );
        })}
      </div>
      <div className="legend" aria-hidden="true">
        <span>
          <span className="swatch" style={{ background: "var(--series-1)" }} />
          Probability
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--ink)", opacity: 0.6 }} />
          {modelUncertainty ? "10-90% across refits of the model (model uncertainty only)" : "10-90% credible interval"}
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--series-2)" }} />
          Comps alone (the weaker estimate)
        </span>
      </div>
    </figure>
  );
}
