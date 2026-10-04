import { useMeta } from "../api/hooks";
import { Section } from "../components/Section";

interface Row {
  claim: string;
  result: string;
  verdict: "held" | "mixed" | "failed";
}

// Numbers come from the backtests in the repository README (docs/backtest_h3.txt, docs/outlook_backtest.txt).
const ROWS: Row[] = [
  { claim: "Players with similar statistics have similar careers (comps as the forecast)", result: "No better than matching on current level and age (Brier 0.598 vs 0.582). Kept as evidence, not as the probability.", verdict: "failed" },
  { claim: "A learned model on a few summary features predicts the outcome tier", result: "Holdout Brier 0.516 vs 0.589 for same-level matching; intervals exclude zero. Overstates P(elite) in the 20 to 70% range; recalibrated on out-of-time predictions.", verdict: "held" },
  { claim: "A fan chart of the next three seasons' level", result: "Beats persistence and shrinkage at every horizon (pinball 3.94 / 4.20 / 4.42 vs 4.16 / 4.49 / 4.57), a modest gain. Bands cover 78% for a nominal 80%.", verdict: "held" },
  { claim: "Aging curves improve forecasts", result: "They describe aging well but add under 3% over regression to the mean; worse for players 30 and over three seasons out.", verdict: "failed" },
  { claim: "Underpriced players gain more value later", result: "+19% over one season and +33% over two, after counting players who left the five leagues (the raw figure was +24% and +51%: part survivorship). Weaker since 2020.", verdict: "held" },
  { claim: "Signings fix a team's gaps", result: "Squad changes explain only about 3 points of R-squared of next season's style change, once an accounting-identity leak is removed. The shortlist is a labelled heuristic.", verdict: "mixed" },
  { claim: "Players can be matched across sources", result: "97.6 to 100% of minutes linked per league-season; Understat and FBref agree on minutes for 99.95% of doubly linked player-seasons.", verdict: "held" },
];

const CHIP: Record<Row["verdict"], { cls: string; text: string }> = {
  held: { cls: "chip good", text: "Held up" },
  mixed: { cls: "chip", text: "Weak" },
  failed: { cls: "chip out", text: "Did not hold" },
};

export function MethodPage() {
  const meta = useMeta();
  return (
    <>
      <h1>How far to trust it</h1>
      <p className="lede" style={{ maxWidth: 720 }}>
        Every claim in this app was tested out of sample, against simple baselines, with features rebuilt as of each backtest date so nothing from the future leaks in. These are the
        results, including the ones that failed.
      </p>
      <Section id="results" title="What held up and what did not">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Claim</th>
                <th>Result</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.claim}>
                  <td>{r.claim}</td>
                  <td>{r.result}</td>
                  <td>
                    <span className={CHIP[r.verdict].cls}>{CHIP[r.verdict].text}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Section id="limits" title="What it cannot see">
        <ul>
          <li>Only the five biggest leagues, 2014 to 2025. Players from lower leagues or other continents are invisible until they reach one.</li>
          <li>Performance means attacking output (league-adjusted non-penalty xG, expected assists, chain involvement). It says little about defenders and nothing about goalkeepers' quality beyond save percentage, so those positions get no outlook.</li>
          <li>"Elite" is a fixed cut (top 10% of a position's composite). "Out" mixes injury, retirement and a move to a league outside the data.</li>
          <li>Market value is Transfermarkt's estimate, revised a few times a year. It is not a transfer fee and not a valuation by a club.</li>
          <li>Ranges show model uncertainty, not the randomness of football. Treat a 5% chance as unlikely, not impossible.</li>
        </ul>
      </Section>
      {meta.data && (
        <p className="small muted">
          Model information: horizon {meta.data.horizon} seasons, information up to {meta.data.as_of}, {meta.data.forecast_bootstrap_fits} bootstrap refits behind forecast ranges, probabilities {meta.data.calibrated ? "" : "not "}
          calibrated. Full report: <code>{meta.data.backtest_report}</code> and the repository README.
        </p>
      )}
    </>
  );
}
