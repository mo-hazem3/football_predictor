import { Link } from "react-router-dom";

import type { Comp } from "../api/types";
import { leagueLabel, outcomeLabel, seasonLabel, teamLabel } from "../lib/format";

/** The "visible proof": each comparable player, and what he went on to become (blank until his window has finished). */
export function CompsTable({ comps, caption }: { comps: Comp[]; caption?: string }) {
  if (!comps.length) return <p className="muted">No comparable players found.</p>;
  return (
    <div className="table-wrap">
      <table>
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            <th>Player</th>
            <th>Season</th>
            <th>Team</th>
            <th className="num">Age</th>
            <th className="num" title="Distance in the engine's stats space">Distance</th>
            <th>Went on to become</th>
            <th className="num">Peak value ×</th>
          </tr>
        </thead>
        <tbody>
          {comps.map((c) => (
            <tr key={`${c.player_id}-${c.season}`}>
              <td>
                <Link to={`/players/${c.player_id}`}>{c.name}</Link>
              </td>
              <td>
                {seasonLabel(c.season)} <span className="muted small">{leagueLabel(c.league)}</span>
              </td>
              <td>{teamLabel(c.team)}</td>
              <td className="num">{c.age.toFixed(1)}</td>
              <td className="num" title="Smaller is closer. Distances are only comparable within one player's list.">
                {c.distance.toFixed(2)}
              </td>
              <td>
                <span className={`chip ${c.outcome ?? ""}`}>{c.outcome ? outcomeLabel(c.outcome) : "Too recent to know"}</span>
              </td>
              <td className="num">{c.value_ratio !== null && c.value_ratio !== undefined ? `${c.value_ratio.toFixed(1)}×` : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
