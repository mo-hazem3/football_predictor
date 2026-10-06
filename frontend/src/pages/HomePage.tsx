import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useMeta } from "../api/hooks";
import { Avatar } from "../components/Avatar";
import { PlayerSearch } from "../components/Searches";

const EXAMPLES: { id: number; name: string; why: string }[] = [
  { id: 11527, name: "Lamine Yamal", why: "an 18-year-old at the top of his position" },
  { id: 7322, name: "Bukayo Saka", why: "in his prime, how long does the level last?" },
  { id: 8260, name: "Erling Haaland", why: "an elite striker: strengths and gaps against comps" },
];

const icon = (children: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

const FEATURES: { title: string; icon: ReactNode; body: string }[] = [
  {
    title: "Outlook, not a prediction",
    icon: icon(<polyline points="3 17 9 11 13 15 21 6" />),
    body: "A fan chart of where a player's level is likely to be over the next three seasons, with the chance he is still a top-five-league regular. It beats simple baselines in a rolling backtest, by a modest margin, and its bands cover 78% of outcomes against a nominal 80%.",
  },
  {
    title: "Price versus output",
    icon: icon(
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1.1 0-2-.4-2.5-1.2M12 6.5V8m0 8v1.5" />
      </>,
    ),
    body: "Players priced furthest below what they produce gained about 19% more value over the next season than those priced furthest above, after counting players who left the five leagues. A screen to look at, not a buy signal.",
  },
  {
    title: "What a team is missing",
    icon: icon(
      <>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="4.5" />
        <circle cx="12" cy="12" r="1" />
      </>,
    ),
    body: "Ten tactical dimensions ranked against the league, the gaps, and a labelled heuristic shortlist of players who could address them. Signings explain only a few points of next season's style change, so it ranks; it does not promise.",
  },
];

export function HomePage() {
  const meta = useMeta();
  return (
    <>
      <section className="hero">
        <span className="eyebrow">Open data · five leagues · 2014 to 2025</span>
        <h1>
          Scouting intelligence from <span className="accent">open football data</span>
        </h1>
        <p>
          Search a player to see where his level is likely to go, who played like him and what they became, whether he is priced fairly for what he produces, and what his team
          is missing. Every number comes with the backtest that says how much to trust it.
        </p>
        <PlayerSearch autoFocus />
        <div className="examples">
          <span className="label">Try</span>
          {EXAMPLES.map((e) => (
            <Link key={e.id} to={`/players/${e.id}`} title={e.why} className="pill">
              <Avatar name={e.name} />
              {e.name}
            </Link>
          ))}
          <span className="small muted">
            or look at a <Link to="/teams">team</Link>
          </span>
        </div>
      </section>

      {meta.data && (
        <div className="stats">
          <div className="tile">
            <span className="big">{meta.data.players.toLocaleString()}</span>
            <span className="label">players</span>
          </div>
          <div className="tile">
            <span className="big">{meta.data.player_seasons.toLocaleString()}</span>
            <span className="label">player-seasons</span>
          </div>
          <div className="tile">
            <span className="big">
              {meta.data.seasons[0]}–{meta.data.as_of}
            </span>
            <span className="label">seasons covered</span>
          </div>
        </div>
      )}

      <div className="grid">
        {FEATURES.map((f) => (
          <section className="card feature" key={f.title}>
            <div className="icon-badge">{f.icon}</div>
            <h2>{f.title}</h2>
            <p>{f.body}</p>
          </section>
        ))}
      </div>

      <p className="small muted" style={{ marginTop: "1.5rem" }}>
        <Link to="/method">How far to trust it</Link> lists what was validated and what failed.
      </p>
    </>
  );
}
