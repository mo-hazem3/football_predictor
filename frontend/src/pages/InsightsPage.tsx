import { useAging, useLeagues } from "../api/hooks";
import { AgingChart } from "../components/charts/AgingChart";
import { Notice, Section } from "../components/Section";
import { Async } from "../components/States";
import { leagueLabel } from "../lib/format";

export function InsightsPage() {
  const aging = useAging();
  const leagues = useLeagues();
  return (
    <>
      <h1>Insights</h1>
      <Section
        id="aging"
        title="How output changes with age"
        lede="A player's attacking output at each age as a multiple of his own output at 25: the same players followed as they age, league-adjusted, with a 95% bootstrap band."
      >
        <Async query={aging} label="Loading aging curves">
          {(a) => (
            <>
              <div className="grid">
                {a.groups.map((g) => (
                  <AgingChart key={g.position_group} group={g} />
                ))}
              </div>
              <Notice kind="info">
                <strong>Describes aging well, forecasts it poorly.</strong> In the backtest, shrinking last season's output toward the position mean cut next-season error by about 9% against assuming
                persistence; adding the aging curve on top changed it by under 3%, because a year of aging moves output by 5 to 10% while season-to-season noise is far larger.
              </Notice>
              <ul className="small muted">
                {a.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </>
          )}
        </Async>
      </Section>

      <Section
        id="leagues"
        title="How hard is each league?"
        lede="Estimated from players who changed league: a factor of 0.85 means the same player typically produces about 15% less attacking output per 90 there than the five-league average (difficulty mixed with playing style)."
      >
        <Async query={leagues} label="Loading league factors">
          {(rows) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>League</th>
                    <th className="num">Factor</th>
                    <th className="num">95% interval</th>
                    <th className="num" title="Player-seasons from players who changed league that fed the estimate">Observations</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((l) => (
                    <tr key={l.league}>
                      <td>{leagueLabel(l.league)}</td>
                      <td className="num">{l.factor.toFixed(2)}</td>
                      <td className="num">
                        {l.ci_low !== null && l.ci_low !== undefined && l.ci_high !== null && l.ci_high !== undefined ? `${l.ci_low.toFixed(2)} to ${l.ci_high.toFixed(2)}` : "–"}
                      </td>
                      <td className="num">{l.n_obs.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
        <p className="chart-note">The Premier League is clearly the hardest. The order of the middle three leagues is uncertain: their intervals overlap.</p>
      </Section>
    </>
  );
}
