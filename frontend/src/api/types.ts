// Friendly names for the response types generated from the backend's OpenAPI schema (npm run gen:api).
import type { components } from "./schema";

type S = components["schemas"];

export type PlayerSearchResult = S["PlayerSearchResult"];
export type PlayerProfile = S["PlayerProfile"];
export type SeasonStats = S["SeasonStats"];
export type CompsResponse = S["CompsResponse"];
export type Comp = S["Comp"];
export type Gap = S["Gap"];
export type ForecastResponse = S["ForecastResponse"];
export type OutcomeProbability = S["OutcomeProbability"];
export type OutlookResponse = S["OutlookResponse"];
export type OutlookHorizon = S["OutlookHorizon"];
export type LevelPoint = S["LevelPoint"];
export type PlayerValue = S["PlayerValue"];
export type PricePoint = S["PricePoint"];
export type AgingResponse = S["AgingResponse"];
export type AgingGroup = S["AgingGroup"];
export type LeagueStrength = S["LeagueStrength"];
export type Meta = S["Meta"];
export type TeamSearchResult = S["TeamSearchResult"];
export type TeamProfile = S["TeamProfile"];
export type TeamDimension = S["TeamDimension"];
export type ShortlistResponse = S["ShortlistResponse"];
export type Candidate = S["Candidate"];
export type Target = S["Target"];
