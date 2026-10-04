import { Link, useSearchParams } from "react-router-dom";

import { useMeta, useShortlist, useTeamProfile } from "../api/hooks";
import type { Candidate, TeamProfile } from "../api/types";
import { PercentileBars } from "../components/charts/PercentileBars";
import { Notice, Section } from "../components/Section";
import { TeamSearch } from "../components/Searches";
import { Async } from "../components/States";
import { eur, leagueLabel, positionLabel, seasonLabel, teamLabel } from "../lib/format";

const EXAMPLE_TEAMS = [
  { team: "Burnley", season: 2023 },
  { team: "Bayer Leverkusen", season: 2023 },
  { team: "Leicester", season: 2015 },
];

function CandidatesTable({ rows }: { rows: Candidate[] }) {
  if (!rows.length) return <p className="muted">No candidate meets the strength bar within these filters.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Position</th>
            <th>Plays for</th>
            <th className="num">Age</th>
            <th className="num" title="Mean percentile within position on the metrics that bear on this gap">Fit</th>
            <th className="num">Value</th>
            <th className="num" title="% below (−) or above (+) the value of peers with the same output and age">Price vs output</th>
            <th>Age curve</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.player_id}>
              <td>
                <Link to={`/players/${c.player_id}`}>{c.name}</Link>
              </td>
              <td>{positionLabel(c.position_group)}</td>
              <td>
                {teamLabel(c.team)} <span className="muted small">{leagueLabel(c.league)}</span>
              </td>
              <td className="num">{c.age.toFixed(1)}</td>
              <td className="num">{Math.round(c.fit)}</td>
              <td className="num">{eur(c.market_value_eur)}</td>
              <td className="num">{c.price_vs_output_pct !== null && c.price_vs_output_pct !== undefined ? `${c.price_vs_output_pct > 0 ? "+" : ""}${Math.round(c.price_vs_output_pct)}%` : "–"}</td>
              <td className="small">{c.age_note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Shortlist({ p, search, setSearch }: { p: TeamProfile; search: URLSearchParams; setSearch: (n: URLSearchParams) => void }) {
  // default to the weakest gap that is reliable: counter-attack and set-piece threat persist weakly year to year
  const byWeakness = [...p.dimensions].sort((a, b) => a.percentile - b.percentile);
  const gaps = byWeakness.filter((d) => d.is_gap);
  const gap = search.get("gap") ?? (gaps.find((d) => !d.noisy) ?? gaps[0] ?? byWeakness[0]).dimension;
  const maxAge = search.get("maxAge") ? Number(search.get("maxAge")) : 29;
  const maxValueM = search.get("maxValueM") ? Number(search.get("maxValueM")) : undefined;
  const q = useShortlist({ team: p.team, season: p.season, gap, maxAge, maxValueM, n: 10 });

  function set(key: string, value: string) {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearch(next);
  }

  return (
    <Section id="shortlist" title="Candidates for a gap" lede="A ranking heuristic: players strong, for their position, on the metrics that plausibly bear on the gap, within the club's own price scale. It does not predict that a signing closes the gap.">
      <div className="row" style={{ marginBottom: "1rem", alignItems: "flex-end" }}>
        <div className="field">
          <label htmlFor="gap">Gap to address</label>
          <select id="gap" value={gap} onChange={(e) => set("gap", e.target.value)}>
            {[...p.dimensions]
              .sort((a, b) => a.percentile - b.percentile)
              .map((d) => (
                <option key={d.dimension} value={d.dimension}>
                  {d.label} ({Math.round(d.percentile)}th{d.is_gap ? ", gap" : ""})
                </option>
              ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="maxage">Max age</label>
          <input id="maxage" type="text" inputMode="numeric" defaultValue={maxAge} onBlur={(e) => set("maxAge", e.target.value)} style={{ width: 90 }} />
        </div>
        <div className="field">
          <label htmlFor="budget">Max value (€m)</label>
          <input id="budget" type="text" inputMode="decimal" placeholder="club scale" defaultValue={maxValueM ?? ""} onBlur={(e) => set("maxValueM", e.target.value)} style={{ width: 110 }} />
        </div>
      </div>
      <Async query={q} label="Finding candidates">
        {(s) => (
          <>
            {!s.mapped && <Notice kind="info">{s.note}</Notice>}
            {s.mapped && (
              <>
                <p className="small muted">
                  Value ceiling {eur(s.ceiling_eur)}
                  {!maxValueM ? " (the highest value in this squad)" : ""}. {s.gap.noisy ? "This dimension is noisy: a team's value on it persists weakly from year to year." : ""}
                </p>
                <CandidatesTable rows={s.candidates} />
              </>
            )}
          </>
        )}
      </Async>
    </Section>
  );
}

function Profile({ team, season, search, setSearch }: { team: string; season?: number; search: URLSearchParams; setSearch: (n: URLSearchParams) => void }) {
  const q = useTeamProfile(team, season);
  return (
    <Async query={q} label="Loading team">
      {(p) => (
        <>
          <header style={{ marginBottom: "1.25rem" }}>
            <h1>{p.team}</h1>
            <div className="row">
              <span className="chip">
                {leagueLabel(p.league)} {seasonLabel(p.season)}
              </span>
              <span className="chip">{p.points_per_match.toFixed(2)} points per match</span>
              <span className="chip">xG {p.xg_per_match.toFixed(2)} for / {p.xga_per_match.toFixed(2)} against</span>
            </div>
          </header>
          <Section id="style" title="Style and gaps" lede="Each dimension ranked against the other teams in the league that season. Higher is better; red is the bottom quartile.">
            <PercentileBars
              rows={p.dimensions.map((d) => ({ label: d.noisy ? `${d.label} (noisy)` : d.label, value: d.percentile, isGap: d.is_gap }))}
              threshold={25}
              ariaLabel={`Style profile of ${p.team}: gaps in ${p.dimensions.filter((d) => d.is_gap).map((d) => d.label).join(", ") || "no dimension"}.`}
            />
            <p className="chart-note">"Noisy" dimensions (counter-attack and set-piece threat) persist weakly season to season, so a gap there may be partly chance.</p>
          </Section>
          <Shortlist p={p} search={search} setSearch={setSearch} />
        </>
      )}
    </Async>
  );
}

export function TeamsPage() {
  const [search, setSearch] = useSearchParams();
  const team = search.get("team") ?? "";
  const season = search.get("season") ? Number(search.get("season")) : undefined;
  const meta = useMeta();

  function setSeason(value: string) {
    const next = new URLSearchParams(search);
    if (value) next.set("season", value);
    else next.delete("season");
    next.delete("gap");
    setSearch(next);
  }

  return (
    <>
      <div className="row spread" style={{ marginBottom: "1rem" }}>
        <TeamSearch />
        {team && meta.data && (
          <div className="field">
            <label htmlFor="team-season">Season</label>
            <select id="team-season" value={season ?? ""} onChange={(e) => setSeason(e.target.value)}>
              <option value="">Latest</option>
              {[...meta.data.seasons].reverse().map((s) => (
                <option key={s} value={s}>
                  {seasonLabel(s)}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      {team ? (
        <Profile team={team} season={season} search={search} setSearch={setSearch} />
      ) : (
        <section className="hero">
          <h1>What is a team missing?</h1>
          <p>Search a team to see its tactical profile against the league, where it is weakest, and a shortlist of players who could address a gap.</p>
          <p className="small muted">
            Try:{" "}
            {EXAMPLE_TEAMS.map((e, i) => (
              <span key={e.team}>
                {i > 0 && ", "}
                <Link to={`/teams?team=${encodeURIComponent(e.team)}&season=${e.season}`}>
                  {e.team} {seasonLabel(e.season)}
                </Link>
              </span>
            ))}
          </p>
        </section>
      )}
    </>
  );
}

