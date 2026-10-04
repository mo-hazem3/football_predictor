"""CLI: python -m ml.plot_aging [--out docs/aging_curves.png] [--boot 200]

Small multiples, one panel per position: a player's output at each age as a multiple of what he
produces at 25 (same player, league-adjusted npxG + xA per 90, season-normalised), with a 95%
bootstrap band. Ages with fewer than 30 observations are not drawn. Single series per panel, so
one hue; the dotted line is "same as at 25". The note in each panel gives the plateau (ages within 3% of the
estimated maximum) because single-age peaks are not well determined.
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
from ml import aging

SURFACE, INK, INK2, MUTED, GRID, AXIS, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6"
TITLES = {"FWD": "Forwards", "WING_AM": "Wingers & attacking mids", "MID": "Midfielders", "DEF": "Defenders"}
MIN_OBS = 30


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/aging_curves.png")
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    df = pd.read_sql("SELECT * FROM player_season_features", db.connect(args.db))
    p = aging.panel(df, "attack")
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.9), facecolor=SURFACE, sharey=True)
    for ax, g in zip(axes, aging.GROUPS):
        c = aging.fit_curve(p[p.position_group == g], n_boot=args.boot)
        c = c[c.n_obs >= MIN_OBS]
        ax.axhline(1.0, color=AXIS, lw=1, ls=":", zorder=1)
        ax.fill_between(c.age, np.exp(c.lo), np.exp(c.hi), color=BLUE, alpha=0.16, lw=0, zorder=2)
        ax.plot(c.age, c.multiple_of_25, color=BLUE, lw=2, zorder=3)
        lo, hi = aging.plateau(c, min_obs=MIN_OBS)
        ax.annotate(f"within 3% of the top: ages {lo}-{hi}" if hi > lo else f"top at age {lo}", (0.03, 0.04), xycoords="axes fraction",
                    fontsize=8, color=INK2, ha="left")
        ax.set_title(TITLES[g], loc="left", fontsize=10.5, color=INK, pad=8)
        ax.set_xlabel("Age", fontsize=8.5, color=INK2)
        ax.set_facecolor(SURFACE)
        ax.grid(color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=8, length=0)
        ax.set_xticks([20, 25, 30, 35])
    axes[0].set_ylabel("Output as a multiple of age 25", fontsize=8.5, color=INK2)
    fig.suptitle("How a player's attacking output changes with age (same player, league-adjusted)", x=0.045, ha="left",
                 fontsize=12.5, color=INK, y=0.985)
    fig.text(0.045, 0.01, "Within-player estimate with 95% bootstrap band; ages with < 30 observations omitted. "
             "Survivorship: players who decline lose their 900+ minutes and drop out, so the older ages are optimistic.",
             fontsize=7.5, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
