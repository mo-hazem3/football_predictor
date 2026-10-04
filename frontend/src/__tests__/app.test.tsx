import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { PlayerSearch } from "../components/Searches";
import { InsightsPage } from "../pages/InsightsPage";
import { TeamsPage } from "../pages/TeamsPage";
import { PlayerPage } from "../pages/PlayerPage";
import { comps, defenderOutlook, forecast, outlook, profile, value } from "../test/fixtures";

type Handler = unknown | ((url: URL) => { status?: number; body: unknown });

/** Routes fetch() by pathname so each test states exactly which API responses it depends on. */
function mockApi(routes: Record<string, Handler>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      calls.push(url.pathname + url.search);
      const handler = routes[url.pathname];
      if (handler === undefined) return new Response(JSON.stringify({ detail: `unmocked ${url.pathname}` }), { status: 500 });
      const r = typeof handler === "function" ? (handler as (u: URL) => { status?: number; body: unknown })(url) : { body: handler };
      return new Response(JSON.stringify(r.body), { status: r.status ?? 200 });
    }),
  );
  return calls;
}

function renderAt(ui: React.ReactNode, path: string, routePath = "*") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function LocationProbe() {
  return <div data-testid="location">{useLocation().pathname}</div>;
}

afterEach(() => vi.unstubAllGlobals());

describe("player search", () => {
  const results = [
    { player_id: 7, name: "Test Winger", latest_season: 2024, team: "Alpha FC", league: "EPL", position_group: "WING_AM", age: 22.4, minutes: 2400 },
    { player_id: 8, name: "Test Winger Jr", latest_season: 2023, team: "Beta FC", league: "La_liga", position_group: "FWD", age: 19, minutes: 900 },
  ];

  it("searches after a pause, lists matches, and keyboard selection navigates to the player", async () => {
    const calls = mockApi({ "/api/v1/players/search/": results });
    const user = userEvent.setup();
    renderAt(
      <>
        <PlayerSearch />
        <LocationProbe />
      </>,
      "/",
    );
    const box = screen.getByRole("combobox", { name: /search players/i });
    await user.type(box, "te");
    expect(await screen.findByRole("option", { name: /Test Winger.*Alpha FC/i })).toBeInTheDocument();
    expect(calls.filter((c) => c.includes("search"))).toHaveLength(1);              // debounced: one request for "te", not one per keystroke
    expect(calls[0]).toContain("q=te");

    await user.keyboard("{ArrowDown}{Enter}");                                      // second option
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/players/8"));
  });

  it("makes no request for a single character and says when nothing matches", async () => {
    const calls = mockApi({ "/api/v1/players/search/": [] });
    const user = userEvent.setup();
    renderAt(<PlayerSearch />, "/");
    const box = screen.getByRole("combobox");
    await user.type(box, "x");
    await new Promise((r) => setTimeout(r, 350));
    expect(calls).toHaveLength(0);
    await user.type(box, "yz");
    expect(await screen.findByText("No players found")).toBeInTheDocument();
  });

  it("closes the list with Escape", async () => {
    mockApi({ "/api/v1/players/search/": results });
    const user = userEvent.setup();
    renderAt(<PlayerSearch />, "/");
    await user.type(screen.getByRole("combobox"), "test");
    await screen.findByRole("listbox");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

describe("player page", () => {
  const full = {
    "/api/v1/players/7/": profile,
    "/api/v1/players/7/outlook/": outlook,
    "/api/v1/players/7/forecast/": forecast,
    "/api/v1/players/7/comps/": comps,
    "/api/v1/players/7/value/": value,
  };

  it("shows the profile, the outlook, the forecast with its evidence, the gaps and the price", async () => {
    mockApi(full);
    renderAt(<PlayerPage />, "/players/7", "players/:id");

    expect(await screen.findByRole("heading", { level: 1, name: "Test Winger" })).toBeInTheDocument();
    expect(screen.getByText("Egypt")).toBeInTheDocument();
    expect(screen.getByText("181 cm")).toBeInTheDocument();
    expect(screen.getByText("Value €30m")).toBeInTheDocument();

    const outlookSection = (await screen.findByRole("heading", { name: "Outlook" })).closest("section")!;
    expect(await within(outlookSection).findByRole("img", { name: /88 now/ })).toBeInTheDocument();

    const forecastSection = (await screen.findByRole("heading", { name: "What players like him became" })).closest("section")!;
    const bars = await within(forecastSection).findByRole("list", { name: "Outcome probabilities" });
    expect(within(bars).getAllByRole("listitem")[0]).toHaveTextContent("Elite (top 10%)");
    expect(within(forecastSection).getByRole("link", { name: "Past Star" })).toHaveAttribute("href", "/players/20");
    expect(within(forecastSection).getByText("Too recent to know")).toBeInTheDocument();     // a comp whose window has not finished
    expect(within(forecastSection).getByText(/capped|peak over the next three seasons/i)).toBeInTheDocument();

    expect(await screen.findByRole("img", { name: /Gap analysis for Test Winger: Tackles won/ })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /Price versus output for Test Winger/ })).toBeInTheDocument();
  });

  it("explains instead of charting when a player has no outlook", async () => {
    mockApi({ ...full, "/api/v1/players/7/outlook/": defenderOutlook, "/api/v1/players/7/value/": { ...value, covered: false, seasons: [], reading: "The value lens covers forwards, wingers and midfielders." } });
    renderAt(<PlayerPage />, "/players/7", "players/:id");
    expect(await screen.findByText(/No outlook: it covers forwards/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /88 now/ })).not.toBeInTheDocument();
    expect(await screen.findByText(/value lens covers forwards, wingers and midfielders/)).toBeInTheDocument();
  });

  it("shows the server's message when the player does not exist", async () => {
    mockApi({ "/api/v1/players/99/": () => ({ status: 404, body: { detail: "No player with id 99." } }) });
    renderAt(<PlayerPage />, "/players/99", "players/:id");
    expect(await screen.findByRole("alert")).toHaveTextContent("No player with id 99.");
  });

  it("rejects a malformed id without calling the API", async () => {
    const calls = mockApi({});
    renderAt(<PlayerPage />, "/players/abc", "players/:id");
    expect(await screen.findByRole("alert")).toHaveTextContent("not a valid player id");
    expect(calls).toHaveLength(0);
  });

  it("passes the chosen season to every analysis", async () => {
    const calls = mockApi(full);
    renderAt(<PlayerPage />, "/players/7?season=2023", "players/:id");
    await screen.findByRole("heading", { name: "Outlook" });
    await waitFor(() => expect(calls.filter((c) => c.includes("season=2023")).length).toBeGreaterThanOrEqual(3));   // outlook, forecast, comps
  });
});

describe("insights page", () => {
  it("renders the league table with intervals and tolerates a missing interval", async () => {
    mockApi({
      "/api/v1/aging/": { groups: [], notes: ["Survivorship: ..."] },
      "/api/v1/leagues/": [
        { league: "EPL", factor: 0.85, ci_low: 0.82, ci_high: 0.89, n_obs: 600, n_movers: 903 },
        { league: "Serie_A", factor: 1.04, ci_low: null, ci_high: null, n_obs: 500, n_movers: 903 },
      ],
    });
    renderAt(<InsightsPage />, "/insights");
    expect(await screen.findByText("Premier League")).toBeInTheDocument();
    expect(screen.getByText("0.82 to 0.89")).toBeInTheDocument();
    expect(screen.getByText("Serie A").closest("tr")).toHaveTextContent("–");
  });
});


describe("teams page", () => {
  const dim = (dimension: string, label: string, percentile: number, noisy = false) => ({ dimension, label, percentile, value: 1, is_gap: percentile <= 25, noisy });
  const teamProfile = {
    team: "Test FC", league: "EPL", season: 2023, points_per_match: 1.2, xpts_per_match: 1.3, xg_per_match: 1.1, xga_per_match: 1.6,
    dimensions: [dim("set_piece_xg", "Set-piece threat", 5, true), dim("open_play_xg", "Open-play chance creation", 15), dim("pressing", "Pressing intensity", 60)],
  };

  it("defaults the shortlist to the weakest *reliable* gap, not the weakest noisy one", async () => {
    const calls = mockApi({
      "/api/v1/meta/": { players: 1, player_seasons: 1, seasons: [2022, 2023], leagues: ["EPL"], horizon: 3, as_of: 2025, calibrated: true, forecast_bootstrap_fits: 30, backtest_report: "docs/backtest_h3.txt" },
      "/api/v1/teams/profile/": teamProfile,
      "/api/v1/teams/shortlist/": { team: "Test FC", season: 2023, gap: teamProfile.dimensions[1], mapped: true, note: "", ceiling_eur: 20_000_000, candidates: [], method: "heuristic" },
    });
    renderAt(<TeamsPage />, "/teams?team=Test%20FC&season=2023");
    expect(await screen.findByRole("heading", { level: 1, name: "Test FC" })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.includes("/teams/shortlist/"))).toBe(true));
    expect(calls.find((c) => c.includes("/teams/shortlist/"))).toContain("gap=open_play_xg");
    expect(await screen.findByText(/No candidate meets the strength bar/)).toBeInTheDocument();
  });

  it("says plainly when a gap cannot be mapped to players", async () => {
    mockApi({
      "/api/v1/meta/": { players: 1, player_seasons: 1, seasons: [2023], leagues: ["EPL"], horizon: 3, as_of: 2025, calibrated: true, forecast_bootstrap_fits: 30, backtest_report: "x" },
      "/api/v1/teams/profile/": { ...teamProfile, dimensions: [dim("set_piece_xga", "Set-piece defending", 3)] },
      "/api/v1/teams/shortlist/": { team: "Test FC", season: 2023, gap: dim("set_piece_xga", "Set-piece defending", 3), mapped: false, note: "No mapping: the free data has no aerial duels or marking.", ceiling_eur: null, candidates: [], method: "heuristic" },
    });
    renderAt(<TeamsPage />, "/teams?team=Test%20FC&season=2023");
    expect(await screen.findByText(/No mapping: the free data has no aerial duels/)).toBeInTheDocument();
  });
});
