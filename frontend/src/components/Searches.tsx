import { useNavigate } from "react-router-dom";

import { useSearch, useTeamSearch } from "../api/hooks";
import type { PlayerSearchResult, TeamSearchResult } from "../api/types";
import { leagueLabel, positionLabel, seasonLabel } from "../lib/format";
import { Autocomplete } from "./Autocomplete";

export function PlayerSearch({ compact, autoFocus }: { compact?: boolean; autoFocus?: boolean }) {
  const navigate = useNavigate();
  return (
    <Autocomplete<PlayerSearchResult>
      label="Search players"
      placeholder="Search a player, e.g. Yamal"
      compact={compact}
      autoFocus={autoFocus}
      useResults={useSearch}
      getKey={(p) => p.player_id}
      renderItem={(p) => (
        <>
          <span>{p.name}</span>
          <span className="sub">
            {positionLabel(p.position_group)} · {p.team ?? "–"} · {leagueLabel(p.league)} {seasonLabel(p.latest_season)}
          </span>
        </>
      )}
      onSelect={(p) => navigate(`/players/${p.player_id}`)}
      emptyText="No players found"
    />
  );
}

export function TeamSearch({ compact }: { compact?: boolean }) {
  const navigate = useNavigate();
  return (
    <Autocomplete<TeamSearchResult>
      label="Search teams"
      placeholder="Search a team, e.g. Burnley"
      compact={compact}
      useResults={useTeamSearch}
      getKey={(t) => t.team}
      renderItem={(t) => (
        <>
          <span>{t.team}</span>
          <span className="sub">
            {leagueLabel(t.league)} · latest {seasonLabel(t.latest_season)}
          </span>
        </>
      )}
      onSelect={(t) => navigate(`/teams?team=${encodeURIComponent(t.team)}&season=${t.latest_season}`)}
      emptyText="No teams found"
    />
  );
}
