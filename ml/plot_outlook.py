"""CLI: python -m ml.plot_outlook [--players "Lamine Yamal" ...] [--out docs/outlook_fan_charts.png]

Fan charts from the live outlook model (fitted on every outcome known by the latest season): each panel shows a
player's level (position-specific composite percentile) over his seasons so far, then the 10-90% band and
median for the next three seasons. The band is conditional on his still getting 900+ minutes in the five
leagues; the note under each panel gives the chance of that three seasons out.

Style: one hue (history line and forecast share it; the band is the same hue at low opacity), recessive grid,
no dashed rules. Level is bounded at 100, so bands near the top are clipped by construction.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data_pipeline import db
from ml.learned import add_trend
from ml.outcomes import add_composite, build_outcomes, value_series
from ml.outlook import Outlook, build_pairs

SURFACE, INK, INK2, MUTED, GRID, AXIS, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6"
DEFAULT_PLAYERS = ["Lamine Yamal", "Bukayo Saka", "Erling Haaland", "Kevin De Bruyne"]


def fit_live(conn) -> tuple[Outlook, pd.DataFrame]:
    features = pd.read_sql("SELECT * FROM player_season_features", conn)
    squads = pd.read_sql("SELECT tm_player_id, season, market_value_eur FROM transfermarkt_squads", conn)
    last = int(features.season.max())
    out = add_trend(build_outcomes(add_composite(features), value_series(squads), 3, last))
    pairs = build_pairs(out, last)
    return Outlook().fit(pairs), pairs


def draw(ax, name: str, model: Outlook, pairs: pd.DataFrame) -> None:
    mine = pairs[pairs.player_name == name].sort_values("season")
    if mine.empty:
        raise SystemExit(f"No player with a usable level named '{name}'.")
    row = mine.iloc[[-1]]
    q, p = model.predict(row)[0], model.predict_observed(row)[0]
    s0, level0 = int(row.season.iloc[0]), float(row.composite.iloc[0])
    xs = [s0, s0 + 1, s0 + 2, s0 + 3]
    lo, mid, hi = [level0, *q[:, 0]], [level0, *q[:, 1]], [level0, *q[:, 2]]

    ax.axvline(s0, color=AXIS, lw=1, zorder=1)                       # "now": solid hairline, not a dashed rule
    ax.fill_between(xs, lo, hi, color=BLUE, alpha=0.16, lw=0, zorder=2)
    ax.plot(xs, mid, color=BLUE, lw=1.6, alpha=0.75, zorder=3)
    ax.plot(mine.season, mine.composite, color=BLUE, lw=2.2, marker="o", ms=4.5, mec=SURFACE, mew=1.2, zorder=4)
    ax.set_ylim(0, 102)
    ax.set_xlim(mine.season.min() - 0.4, s0 + 3.4)
    ax.set_xticks(sorted(set(mine.season) | set(xs)))
    ax.set_xticklabels([f"'{s % 100:02d}" for s in sorted(set(mine.season) | set(xs))])
    ax.set_title(f"{name}, age {float(row.age.iloc[0]):.0f}", loc="left", fontsize=10.5, color=INK, pad=8)
    ax.annotate(f"+3 seasons: {q[2, 0]:.0f}-{q[2, 2]:.0f} (median {q[2, 1]:.0f})\nstill a top-5 regular: {p[2]:.0%}", (0.03, 0.04),
                xycoords="axes fraction", fontsize=8, color=INK2, ha="left", va="bottom", linespacing=1.4)
    ax.set_facecolor(SURFACE)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--players", nargs="+", default=DEFAULT_PLAYERS)
    ap.add_argument("--out", default="docs/outlook_fan_charts.png")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    model, pairs = fit_live(db.connect(args.db))
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    n = len(args.players)
    fig, axes = plt.subplots(1, n, figsize=(3.4 * n, 3.9), facecolor=SURFACE, sharey=True)
    axes = np.atleast_1d(axes)
    for ax, name in zip(axes, args.players):
        draw(ax, name, model, pairs)
    axes[0].set_ylabel("Level (percentile among his position)", fontsize=8.5, color=INK2)
    for ax in axes:
        ax.set_xlabel("Season (start year)", fontsize=8.5, color=INK2)
    fig.suptitle("Where a player's level is likely to be over the next three seasons", x=0.04, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.04, 0.012, "Line: level so far. Band: 10-90% range for the next three seasons and median, conditional on still getting 900+ minutes "
             "in the five leagues. Level is capped at 100.", fontsize=7.5, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
