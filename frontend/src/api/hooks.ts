import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError, getJson } from "./client";
import type {
  AgingResponse,
  CompsResponse,
  ForecastResponse,
  LeagueStrength,
  Meta,
  OutlookResponse,
  PlayerProfile,
  PlayerSearchResult,
  PlayerValue,
  ShortlistResponse,
  TeamProfile,
  TeamSearchResult,
} from "./types";

/** Client errors (404 unknown player, 400 bad input) will not get better by retrying; server/network errors might. */
export const retryPolicy = (failureCount: number, error: Error) =>
  !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2;

const STABLE = 5 * 60_000; // model output only changes when the backend cache is rebuilt

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: ({ signal }) => getJson<PlayerSearchResult[]>("/api/v1/players/search/", { q, limit: 8 }, signal),
    enabled: q.trim().length >= 2,
    placeholderData: keepPreviousData,
    staleTime: STABLE,
    retry: retryPolicy,
  });

export const usePlayer = (id: number) =>
  useQuery({
    queryKey: ["player", id],
    queryFn: ({ signal }) => getJson<PlayerProfile>(`/api/v1/players/${id}/`, undefined, signal),
    enabled: Number.isInteger(id) && id > 0, // a malformed route id (NaN) must not hit /players/NaN/
    staleTime: STABLE,
    retry: retryPolicy,
  });

export const useOutlook = (id: number, season?: number) =>
  useQuery({ queryKey: ["outlook", id, season], queryFn: ({ signal }) => getJson<OutlookResponse>(`/api/v1/players/${id}/outlook/`, { season }, signal), staleTime: STABLE, retry: retryPolicy });

export const useForecast = (id: number, season?: number) =>
  useQuery({ queryKey: ["forecast", id, season], queryFn: ({ signal }) => getJson<ForecastResponse>(`/api/v1/players/${id}/forecast/`, { season }, signal), staleTime: STABLE, retry: retryPolicy });

export const useComps = (id: number, season?: number, k = 10) =>
  useQuery({ queryKey: ["comps", id, season, k], queryFn: ({ signal }) => getJson<CompsResponse>(`/api/v1/players/${id}/comps/`, { season, k }, signal), staleTime: STABLE, retry: retryPolicy });

export const usePlayerValue = (id: number) =>
  useQuery({ queryKey: ["value", id], queryFn: ({ signal }) => getJson<PlayerValue>(`/api/v1/players/${id}/value/`, undefined, signal), staleTime: STABLE, retry: retryPolicy });

export const useAging = () =>
  useQuery({ queryKey: ["aging"], queryFn: ({ signal }) => getJson<AgingResponse>("/api/v1/aging/", undefined, signal), staleTime: STABLE, retry: retryPolicy });

export const useLeagues = () =>
  useQuery({ queryKey: ["leagues"], queryFn: ({ signal }) => getJson<LeagueStrength[]>("/api/v1/leagues/", undefined, signal), staleTime: STABLE, retry: retryPolicy });

export const useMeta = () =>
  useQuery({ queryKey: ["meta"], queryFn: ({ signal }) => getJson<Meta>("/api/v1/meta/", undefined, signal), staleTime: STABLE, retry: retryPolicy });

export const useTeamSearch = (q: string) =>
  useQuery({
    queryKey: ["team-search", q],
    queryFn: ({ signal }) => getJson<TeamSearchResult[]>("/api/v1/teams/search/", { q, limit: 8 }, signal),
    enabled: q.trim().length >= 2,
    placeholderData: keepPreviousData,
    staleTime: STABLE,
    retry: retryPolicy,
  });

export const useTeamProfile = (team: string, season?: number) =>
  useQuery({
    queryKey: ["team-profile", team, season],
    queryFn: ({ signal }) => getJson<TeamProfile>("/api/v1/teams/profile/", { team, season }, signal),
    enabled: team.length > 0,
    staleTime: STABLE,
    retry: retryPolicy,
  });

export interface ShortlistParams {
  team: string;
  season?: number;
  gap?: string;
  maxValueM?: number;
  maxAge?: number;
  n?: number;
}

export const useShortlist = (p: ShortlistParams) =>
  useQuery({
    queryKey: ["shortlist", p],
    queryFn: ({ signal }) =>
      getJson<ShortlistResponse>("/api/v1/teams/shortlist/", { team: p.team, season: p.season, gap: p.gap, max_value_m: p.maxValueM, max_age: p.maxAge, n: p.n }, signal),
    enabled: p.team.length > 0 && !!p.gap,
    placeholderData: keepPreviousData,
    staleTime: STABLE,
    retry: retryPolicy,
  });
