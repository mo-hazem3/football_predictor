import { Link } from "react-router-dom";

import { useMeta } from "../api/hooks";
import { PlayerSearch } from "../components/Searches";

const EXAMPLES: { id: number; name: string; why: string }[] = [
  { id: 11527, name: "Lamine Yamal", why: "an 18-year-old at the top of his position" },
  { id: 7322, name: "Bukayo Saka", why: "in his prime, how long does the level last?" },
  { id: 8260, name: "Erling Haaland", why: "an elite striker: strengths and gaps against comps" },
];

export function HomePage() {
  const meta = useMeta();
  return (
    <>
      <section className="hero">
        <h1>Scouting intelligence from open football data</h1>
        <p>
          Search a player to see where his level is likely to go, who played like him and what they became, whether he is priced fairly for what he produces, and what his team
          is missing. Every number comes with the backtest that says how much to trust it.
        </p>
        <PlayerSearch autoFocus />
        <p className="small muted" style={{ marginTop: "0.75rem" }}>
          Try:{" "}
          {EXAMPLES.map((e, i) => (
            <span key={e.id}>
              {i > 0 && ", "}
              <Link to={`/players/${e.id}`} title={e.why}>
                {e.name}
              </Link>
            </span>
          ))}
          . Or look at a <Link to="/teams">team</Link>.
        </p>
      </section>

      <div className="grid">
        <section className="card">
          <h2>Outlook, not a prediction</h2>
          <p>A fan chart of where a player's level is likely to be over the next three seasons, with the chance he is still a top-five-league regular. It beats simple baselines in a rolling backtest, by a modest margin, and its bands cover 78% of outcomes against a nominal 80%.</p>
        </section>
        <section className="card">
          <h2>Price versus output</h2>
          <p>Players priced furthest below what they produce gained about 19% more value over the next season than those priced furthest above, after counting players who left the five leagues. A screen to look at, not a buy signal.</p>
        </section>
        <section className="card">
          <h2>What a team is missing</h2>
          <p>Ten tactical dimensions ranked against the league, the gaps, and a labelled heuristic shortlist of players who could address them. Signings explain only a few points of next season's style change, so it ranks; it does not promise.</p>
        </section>
      </div>

      <p className="small muted">
        <Link to="/method">How far to trust it</Link> lists what was validated and what failed.
        {meta.data && ` Data: ${meta.data.players.toLocaleString()} players, ${meta.data.player_seasons.toLocaleString()} player-seasons, ${meta.data.seasons[0]} to ${meta.data.as_of}.`}
      </p>
    </>
  );
}
