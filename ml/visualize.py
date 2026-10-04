"""CLI: python -m ml.visualize [--out docs/comps_pca.png]

Sanity-check figure: project every player-season of a position group onto the first two
principal components of the engine's own stats embedding, then show where one target and its
closest comps fall. If the metric is meaningful the comps should sit in a tight neighbourhood
around the target instead of being scattered across the cloud. PCA is a 2-D shadow of a
~11-dimensional space, so comps can look slightly further apart than they are.

Style: emphasis form (everything else in recessive gray, the comps and the target in two
categorical hues validated with the dataviz palette script, all-pairs, light mode).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from adjustText import adjust_text

from data_pipeline import db
from ml.similarity import ATTACK, DEFENCE, SimilarityEngine

# light-mode tokens (see dataviz palette): surface, ink, grid, series slots 1-2
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
CONTEXT_GRAY, COMPS_BLUE, TARGET_ORANGE = "#c9c8c1", "#2a78d6", "#eb6834"
FONT = ["Segoe UI", "DejaVu Sans"]

PANELS = [("Erling Haaland", 2020, "Forwards"), ("Lamine Yamal", 2024, "Wingers & attacking mids")]


def _complete(eng: SimilarityEngine, group: str) -> tuple[pd.DataFrame, list[str]]:
    cols = ATTACK + DEFENCE
    x = eng.d[(eng.d.position_group == group) & eng.d._pool]
    return x[x[[c + "__t" for c in cols]].notna().all(axis=1)].reset_index(drop=True), cols


def pca_coords(eng_stats: SimilarityEngine, group: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Rows with complete features, their 2-D PCA coordinates, and (explained variance, loadings)."""
    x, cols = _complete(eng_stats, group)
    v = eng_stats.embed(x, group, cols)
    v = v - v.mean(axis=0)
    _, s, vt = np.linalg.svd(v, full_matrices=False)
    explained = s**2 / (s**2).sum()
    vt = vt[:2].copy()
    # The sign of a principal axis is arbitrary; orient for readability: more attacking output
    # to the right (attack block = first 6 columns), chance-creators (xA, column 1) upwards.
    if vt[0, :len(ATTACK)].sum() < 0:
        vt[0] *= -1
    if vt[1, 1] < 0:
        vt[1] *= -1
    return x, v @ vt.T, (explained[:2], vt)


def draw_panel(ax, eng, eng_stats, name: str, season: int, title: str, k: int = 10, n_labels: int = 4) -> dict:
    row = eng.find(name, season).iloc[0]
    comps = eng.comps(int(row.player_id), int(row.season), k=k)
    target = eng.target_row(int(row.player_id), int(row.season))
    x, xy, (explained, loadings) = pca_coords(eng_stats, target.position_group)
    key = list(zip(x.player_id, x.season))
    pos = {kv: xy[i] for i, kv in enumerate(key)}

    ax.scatter(xy[:, 0], xy[:, 1], s=7, color=CONTEXT_GRAY, linewidths=0, alpha=0.55, zorder=1)
    cxy = np.array([pos[(r.player_id, r.season)] for r in comps.itertuples() if (r.player_id, r.season) in pos])
    ax.scatter(cxy[:, 0], cxy[:, 1], s=34, color=COMPS_BLUE, edgecolors=SURFACE, linewidths=1.5, zorder=3)
    t = pos[(target.player_id, target.season)]
    ax.scatter([t[0]], [t[1]], s=70, color=TARGET_ORANGE, edgecolors=SURFACE, linewidths=1.5, zorder=4)

    # label the target and the closest few comps; adjustText keeps labels off each other and the points
    texts = [ax.text(t[0], t[1], f"{target.player_name} {target.season}/{str(target.season + 1)[-2:]}",
                     fontsize=9, color=INK, fontweight="bold", zorder=6)]
    pts = [t]
    for r in comps.head(n_labels).itertuples():
        p = pos.get((r.player_id, r.season))
        if p is not None:
            texts.append(ax.text(p[0], p[1], f"{r.player_name.split()[-1]} {r.season}", fontsize=8, color=INK2, zorder=6))
            pts.append(p)
    pts = np.vstack([pts, cxy])
    adjust_text(texts, x=pts[:, 0], y=pts[:, 1], ax=ax, expand=(1.3, 1.6),
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6, shrinkA=2, shrinkB=3))

    ax.set_title(title, loc="left", fontsize=10.5, color=INK, pad=8)
    ax.set_xlabel(f"More attacking output  →   (PC1, {explained[0]:.0%} of variance)", fontsize=8.5, color=INK2)
    ax.set_ylabel(f"Finisher  ←  →  creator   (PC2, {explained[1]:.0%})", fontsize=8.5, color=INK2)
    ax.set_facecolor(SURFACE)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)

    # how tight is the neighbourhood? median distance to target: comps vs same-position, same-age candidates
    window = x[(x.age - target.age).abs() <= eng.age_window]
    wxy = xy[window.index]
    pool_d = np.median(np.hypot(*(wxy - t).T))
    comp_d = np.median(np.hypot(*(cxy - t).T))
    return {"panel": title, "n_pool": len(x), "pc1+pc2": float(explained.sum()),
            "median_dist_comps": float(comp_d), "median_dist_age_peers": float(pool_d),
            }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/comps_pca.png")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    df = pd.read_sql("SELECT * FROM player_season_features", db.connect(args.db))
    eng = SimilarityEngine(df)                          # as used for comps (context on)
    eng_stats = SimilarityEngine(df, use_context=False)  # stats-only space for the projection

    plt.rcParams["font.family"] = FONT
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.9), facecolor=SURFACE)
    stats = [draw_panel(ax, eng, eng_stats, n, s, t) for ax, (n, s, t) in zip(axes, PANELS)]

    handles = [
        plt.Line2D([], [], marker="o", ls="", color=CONTEXT_GRAY, markersize=5, label="All players of that position, 900+ min"),
        plt.Line2D([], [], marker="o", ls="", color=COMPS_BLUE, markersize=7, label="10 closest comps"),
        plt.Line2D([], [], marker="o", ls="", color=TARGET_ORANGE, markersize=9, label="Target"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8.5, labelcolor=INK2, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("Comparable players sit together in the engine's stats space", x=0.065, ha="left", fontsize=12.5, color=INK, y=0.975)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    for s in stats:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
