import { render, screen, within } from "@testing-library/react";

import { agingData } from "../components/charts/AgingChart";
import { symmetricLimit } from "../components/charts/DivergingBars";
import { FanChart, fanData } from "../components/charts/FanChart";
import { TierBars, orderTiers } from "../components/charts/TierBars";
import { forecast, outlook } from "../test/fixtures";

describe("fanData", () => {
  it("joins history to a fan that opens from today's level", () => {
    const d = fanData(outlook);
    expect(d.map((p) => p.season)).toEqual([2023, 2024, 2025, 2026, 2027]);
    expect(d[0]).toMatchObject({ season: 2023, level: 71 });
    expect(d[1]).toMatchObject({ season: 2024, level: 88, median: 88, band: [88, 88] });   // zero-width at "now"
    expect(d[2]).toMatchObject({ season: 2025, median: 86, band: [70, 95], pObserved: 0.96 });
    expect(d[2].level).toBeUndefined();                                                      // no observed level in the future
  });

  it("copes with an uncovered player (no history, no horizons)", () => {
    expect(fanData({ ...outlook, history: [], horizons: [], level_now: null })).toEqual([]);
  });
});

describe("FanChart", () => {
  it("has a text equivalent: a summary label and a full data table", () => {
    render(<FanChart outlook={outlook} />);
    expect(screen.getByRole("img", { name: /Test Winger.*88 now.*between 55 and 94/ })).toBeInTheDocument();
    const table = screen.getByRole("table", { hidden: true });
    const rows = within(table).getAllByRole("row", { hidden: true });
    expect(rows).toHaveLength(1 + 5);                                                        // header + 5 seasons
    expect(within(table).getByText("2027/28")).toBeInTheDocument();
    expect(within(table).getByText("90%")).toBeInTheDocument();                              // chance still a regular, three seasons out
  });
});

describe("TierBars", () => {
  it("lists the best outcome first and shows ranges", () => {
    expect(orderTiers(forecast.probabilities).map((r) => r.outcome)).toEqual(["elite", "good", "regular", "out"]);
    render(<TierBars rows={forecast.probabilities} modelUncertainty />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent("Elite");
    expect(items[0]).toHaveTextContent("40%");
    expect(items[0]).toHaveTextContent("30% to 50%");
    expect(items[3]).toHaveTextContent("<1%");                                               // 0.4% is shown as <1%, not "0%"
  });

  it("does not break when the API gives no range", () => {
    const rows = forecast.probabilities.map((r) => ({ ...r, p10: null, p90: null }));
    render(<TierBars rows={rows} modelUncertainty={false} />);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("40% (40% to 40%)");
  });
});

describe("helpers", () => {
  it("symmetricLimit makes the zero line central and bars comparable", () => {
    expect(symmetricLimit([-5, 12])).toBe(20);        // never tighter than the minimum
    expect(symmetricLimit([-41, 12])).toBe(50);
    expect(symmetricLimit([])).toBe(20);
  });

  it("agingData drops a missing band rather than inventing one", () => {
    const points = agingData({
      position_group: "MID", label: "Midfielders", plateau_from: 24, plateau_to: 27,
      points: [{ age: 24, multiple_of_25: 1, lo: 0.9, hi: 1.1, n_obs: 100 }, { age: 25, multiple_of_25: 1, lo: null, hi: null, n_obs: 100 }],
    });
    expect(points[0].band).toEqual([0.9, 1.1]);
    expect(points[1].band).toBeNull();
  });
});
