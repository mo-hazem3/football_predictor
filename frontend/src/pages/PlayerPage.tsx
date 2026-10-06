import { Link, useParams, useSearchParams } from "react-router-dom";

import { useComps, useForecast, useOutlook, usePlayer, usePlayerValue } from "../api/hooks";
import type { PlayerProfile } from "../api/types";
import { Avatar } from "../components/Avatar";
import { CompsTable } from "../components/CompsTable";
import { DivergingBars } from "../components/charts/DivergingBars";
import { FanChart } from "../components/charts/FanChart";
import { TierBars } from "../components/charts/TierBars";
import { Notice, Section } from "../components/Section";
import { Async, ErrorBox } from "../components/States";
import { eur, leagueLabel, positionLabel, seasonLabel, teamLabel } from "../lib/format";

function Header({ p, season }: { p: PlayerProfile; season: number | undefined }) {
  const rows = p.seasons.filter((s) => s.percentiles && Object.keys(s.percentiles).length);
  const shown = rows.find((s) => s.season === season) ?? rows.at(-1) ?? p.seasons.at(-1);
  return (
    <header className="player-head">
      <Avatar name={p.name} large />
      <div>
        <h1>{p.name}</h1>
        <div className="row">
          <span className="chip accent">{positionLabel(p.position_group)}</span>
          {shown && (
            <span className="chip">
              {teamLabel(shown.team)} · {leagueLabel(shown.league)} {seasonLabel(shown.season)}
            </span>
          )}
          {shown?.age !== null && shown?.age !== undefined && <span className="chip">Age {shown.age.toFixed(1)}</span>}
          {p.nationalities.map((n) => (
            <span className="chip" key={n}>
              {n}
            </span>
          ))}
          {p.height_cm ? <span className="chip">{p.height_cm} cm</span> : null}
          {p.foot ? <span className="chip">{p.foot}-footed</span> : null}
          {p.birth_date ? <span className="chip">Born {p.birth_date}</span> : null}
          {shown?.market_value_eur ? <span className="chip">Value {eur(shown.market_value_eur)}</span> : null}
        </div>
      </div>
    </header>
  );
}

function SeasonPicker({ p, season, onChange }: { p: PlayerProfile; season: number | undefined; onChange: (s: number | undefined) => void }) {
  const ranked = [...new Set(p.seasons.filter((s) => s.percentiles && Object.keys(s.percentiles).length).map((s) => s.season))].sort((a, b) => b - a);
  if (ranked.length < 2) return null;
  return (
    <div className="field" style={{ marginBottom: "1rem" }}>
      <label htmlFor="season">Season to analyse</label>
      <select id="season" value={season ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}>
        <option value="">Latest</option>
        {ranked.map((s) => (
          <option key={s} value={s}>
            {seasonLabel(s)}
          </option>
        ))}
      </select>
    </div>
  );
}

function OutlookSection({ id, season }: { id: number; season?: number }) {
  const q = useOutlook(id, season);
  return (
    <Section id="outlook" title="Outlook" lede="Where his level is likely to be over the next three seasons.">
      <Async query={q} label="Fitting the outlook">
        {(o) =>
          o.covered ? (
            <>
              {o.notes.length > 3 && <Notice kind="info">{o.notes[0]}</Notice>}
              <FanChart outlook={o} />
            </>
          ) : (
            <Notice>{o.notes[0]}</Notice>
          )
        }
      </Async>
    </Section>
  );
}

function ForecastSection({ id, season }: { id: number; season?: number }) {
  const q = useForecast(id, season);
  return (
    <Section id="forecast" title="What players like him became" lede="Probabilities for the next three seasons, with the comparable players as evidence.">
      <Async query={q} label="Computing the forecast">
        {(f) => (
          <>
            {f.retrospective && <Notice>This season's outcome is already known, so this is a look back, not a true forecast.</Notice>}
            <TierBars rows={f.probabilities} modelUncertainty={f.headline_source === "learned model"} />
            <p className="small muted" style={{ marginTop: "0.75rem" }}>
              Headline from the {f.headline_source}
              {f.headline_source === "learned model" && f.calibrated ? ", calibrated on out-of-time backtests" : ""}. Read straight off the comps alone it would be weaker (orange tick): in the
              backtest, similar-statistics players predicted careers no better than "how good is he now, and how old".
            </p>
            {f.value && (
              <p>
                <strong>Market value</strong> now {eur(f.value.now_eur)}: peak over the next three seasons likely {eur(f.value.p10_eur)} to {eur(f.value.p90_eur)} (median {eur(f.value.p50_eur)})
                {f.value.ceiling_eur && f.value.p90_eur >= f.value.ceiling_eur ? `, capped at ${eur(f.value.ceiling_eur)}, the highest value in the data` : ""} — if he stays on a top-5-league squad.
              </p>
            )}
            <h3>The closest comparable players</h3>
            <CompsTable comps={f.evidence_comps} caption={`${f.n_comps_used} comps with a finished three-season window were used for the "comps alone" marker.`} />
            <details>
              <summary>Caveats</summary>
              <ul>
                {f.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </details>
          </>
        )}
      </Async>
    </Section>
  );
}

function CompsSection({ id, season }: { id: number; season?: number }) {
  const q = useComps(id, season, 10);
  return (
    <Section id="gaps" title="Strengths and gaps against comparable players" lede="Percentile points above (blue) or below (red) the median of his closest comps. Weaknesses are flagged beyond 15 points.">
      <Async query={q} label="Comparing with similar players">
        {(c) => (
          <>
            <DivergingBars
              rows={c.gap_analysis.map((g) => ({ label: g.label, value: g.gap }))}
              unit="percentile points vs comps"
              legend={{ above: "Above his comps' median", below: "Below his comps' median" }}
              ariaLabel={`Gap analysis for ${c.target.name}: ${c.gap_analysis.filter((g) => g.flag === "weakness").map((g) => g.label).join(", ") || "no flagged weaknesses"}.`}
            />
            <p className="chart-note">
              Compared on {c.features_used.length} statistics. {c.target.season < 2016 ? "Seasons before 2016 lack the defensive statistics, so they are compared on attacking output only." : ""}
            </p>
          </>
        )}
      </Async>
    </Section>
  );
}

function ValueSection({ id }: { id: number }) {
  const q = usePlayerValue(id);
  return (
    <Section id="price" title="Price versus output" lede="How far his market value sat below (negative) or above (positive) that of players with the same output and age.">
      <Async query={q} label="Pricing the player">
        {(v) =>
          !v.covered ? (
            <Notice kind="info">{v.reading}</Notice>
          ) : (
            <>
              <DivergingBars
                rows={v.seasons.filter((s) => s.price_vs_output_pct !== null && s.price_vs_output_pct !== undefined).map((s) => ({ label: seasonLabel(s.season), value: s.price_vs_output_pct as number }))}
                unit="% vs peers"
                legend={{ above: "Priced above peers with the same output and age", below: "Priced below them" }}
                ariaLabel={`Price versus output for ${v.name} by season.`}
              />
              <p className="chart-note">{v.reading}</p>
            </>
          )
        }
      </Async>
    </Section>
  );
}

const rate = (v: number | null | undefined, minutes: number) => (v === null || v === undefined || minutes < 450 ? "–" : v.toFixed(2)); // per-90 rates from a handful of minutes are noise

function SeasonsSection({ p }: { p: PlayerProfile }) {
  const rows = [...p.seasons].reverse();
  return (
    <Section id="seasons" title="Season by season">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Season</th>
              <th>Team</th>
              <th className="num">Age</th>
              <th className="num">Minutes</th>
              <th className="num" title="Non-penalty xG per 90, league-adjusted">npxG/90</th>
              <th className="num" title="Expected assists per 90, league-adjusted">xA/90</th>
              <th className="num" title="Tackles won per 90">Tkl/90</th>
              <th className="num">Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={`${s.season}-${s.league}`}>
                <td>
                  {seasonLabel(s.season)} <span className="muted small">{leagueLabel(s.league)}</span>
                </td>
                <td>{teamLabel(s.team)}</td>
                <td className="num">{s.age !== null && s.age !== undefined ? s.age.toFixed(1) : "–"}</td>
                <td className="num">{Math.round(s.minutes).toLocaleString()}</td>
                <td className="num">{rate(s.per90.npxg_p90_adj, s.minutes)}</td>
                <td className="num">{rate(s.per90.xa_p90_adj, s.minutes)}</td>
                <td className="num">{rate(s.per90.tackles_won_p90, s.minutes)}</td>
                <td className="num">{eur(s.market_value_eur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-note">Attacking rates are league-adjusted, so they are comparable across leagues. Rates are hidden below 450 minutes, where they are noise.</p>
    </Section>
  );
}

export function PlayerPage() {
  const params = useParams();
  const id = Number(params.id);
  const [search, setSearch] = useSearchParams();
  const season = search.get("season") ? Number(search.get("season")) : undefined;
  const profile = usePlayer(id);

  if (!Number.isInteger(id) || id <= 0) {
    return (
      <>
        <ErrorBox error={new Error("That is not a valid player id.")} />
        <p>
          <Link to="/">Search for a player</Link>
        </p>
      </>
    );
  }

  return (
    <Async query={profile} label="Loading player">
      {(p) => (
        <>
          <Header p={p} season={season} />
          <SeasonPicker
            p={p}
            season={season}
            onChange={(s) => {
              const next = new URLSearchParams(search);
              if (s) next.set("season", String(s));
              else next.delete("season");
              setSearch(next, { replace: true });
            }}
          />
          <OutlookSection id={id} season={season} />
          <ForecastSection id={id} season={season} />
          <CompsSection id={id} season={season} />
          <ValueSection id={id} />
          <SeasonsSection p={p} />
        </>
      )}
    </Async>
  );
}
