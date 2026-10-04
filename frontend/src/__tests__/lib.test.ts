import { ApiError, buildUrl, errorMessage, getJson } from "../api/client";
import { retryPolicy } from "../api/hooks";
import { eur, leagueLabel, level, metricLabel, outcomeLabel, pct, positionLabel, seasonLabel, signed, teamLabel } from "../lib/format";

describe("format", () => {
  it("formats probabilities, with <1% for tiny non-zero values", () => {
    expect(pct(0.973)).toBe("97%");
    expect(pct(0.004)).toBe("<1%");
    expect(pct(0)).toBe("0%");
    expect(pct(0.1234, 1)).toBe("12.3%");
    expect(pct(null)).toBe("–");
    expect(pct(Number.NaN)).toBe("–");
  });

  it("formats money at the right scale", () => {
    expect(eur(45_000_000)).toBe("€45m");
    expect(eur(7_500_000)).toBe("€7.5m");
    expect(eur(1_460_000_000)).toBe("€1.5bn");
    expect(eur(800_000)).toBe("€800k");
    expect(eur(undefined)).toBe("–");
  });

  it("labels seasons, positions, leagues and outcomes", () => {
    expect(seasonLabel(2024)).toBe("2024/25");
    expect(seasonLabel(1999)).toBe("1999/00");
    expect(positionLabel("WING_AM")).toBe("Winger / attacking mid");
    expect(positionLabel(null)).toBe("Unknown position");
    expect(leagueLabel("La_liga")).toBe("La Liga");
    expect(leagueLabel("Eredivisie_B")).toBe("Eredivisie B");
    expect(outcomeLabel("elite")).toContain("Elite");
    expect(outcomeLabel(null)).toBe("Not yet known");
  });

  it("spaces out the clubs of a mid-season mover", () => {
    expect(teamLabel("Brentford,Manchester United")).toBe("Brentford / Manchester United");
    expect(teamLabel("Arsenal")).toBe("Arsenal");
    expect(teamLabel(null)).toBe("–");
  });

  it("formats numbers and metric names", () => {
    expect(level(87.6)).toBe("88");
    expect(signed(3)).toBe("+3");
    expect(signed(-3.5, 1)).toBe("-3.5");
    expect(metricLabel("npxg_pct_global")).toBe("Non-penalty xG");
    expect(metricLabel("tackles_won_pct_league")).toBe("Tackles won");
    expect(metricLabel("some_new_metric")).toBe("some new metric");
  });
});

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("builds query strings and skips empty values", () => {
    expect(buildUrl("/api/v1/x/", { q: "a b", season: 2024, gap: undefined, n: null, empty: "" })).toBe("/api/v1/x/?q=a+b&season=2024");
    expect(buildUrl("/api/v1/x/")).toBe("/api/v1/x/");
  });

  it("flattens DRF error shapes into one sentence", () => {
    expect(errorMessage({ detail: "No player with id 5." }, "x")).toBe("No player with id 5.");
    expect(errorMessage({ q: ["at least 2 characters"] }, "x")).toBe("q: at least 2 characters");
    expect(errorMessage({ k: "must be between 1 and 50" }, "x")).toBe("k: must be between 1 and 50");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })));
    await expect(getJson("/api/v1/health/")).resolves.toEqual({ ok: true });
  });

  it("turns an error response into an ApiError carrying the server's message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "No player with id 9." }), { status: 404 })));
    await expect(getJson("/api/v1/players/9/")).rejects.toMatchObject({ name: "ApiError", status: 404, message: "No player with id 9." });
  });

  it("explains a network failure instead of a bare TypeError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(getJson("/api/v1/health/")).rejects.toMatchObject({ status: 0, message: expect.stringContaining("backend") });
  });

  it("lets an aborted request propagate untouched (React Query cancels on unmount)", async () => {
    const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw abort; }));
    await expect(getJson("/api/v1/health/")).rejects.toBe(abort);
  });

  it("does not retry client errors but retries server errors a couple of times", () => {
    expect(retryPolicy(0, new ApiError(404, "nope"))).toBe(false);
    expect(retryPolicy(0, new ApiError(400, "bad"))).toBe(false);
    expect(retryPolicy(0, new ApiError(503, "down"))).toBe(true);
    expect(retryPolicy(2, new ApiError(503, "down"))).toBe(false);
    expect(retryPolicy(0, new ApiError(0, "network"))).toBe(true);
  });
});
