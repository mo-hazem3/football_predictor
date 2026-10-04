"""CLI: python -m ml.evaluate_similarity

Label-free test of the distance metric. Ground truth we do have: a player is the
same person across seasons, so, within the same position group and age window, a
player-season's other seasons should rank near the top of its neighbours. For each
target we find the best-ranked other season of the same player among all candidates
and report

  hit@k   share of targets whose best same-player row is in the top k
  MRR     mean reciprocal rank of that row
  chance  hit@k expected from a random ordering of the same candidate set

This measures whether the stats representation captures player identity/style, which
is a precondition for good comps; it does not prove that comps predict careers (that is
the backtest's job). Context features (league, league jump) are switched off here, since
they persist for a player across seasons and would inflate the score without saying
anything about the stats.
"""
from __future__ import annotations

import argparse
from math import comb

import numpy as np
import pandas as pd

from data_pipeline import db
from ml.similarity import ATTACK, DEFENCE, GOALKEEPING, SimilarityEngine

METRICS = ["euclidean", "cosine", "mahalanobis"]


def _chance_hit(n_candidates: int, n_same: int, k: int) -> float:
    if n_candidates - n_same < k:
        return 1.0
    return 1.0 - comb(n_candidates - n_same, k) / comb(n_candidates, k)


def evaluate(df: pd.DataFrame, metric: str, k: int = 10, age_window: float = 1.5) -> pd.DataFrame:
    eng = SimilarityEngine(df, metric=metric, use_context=False, age_window=age_window)
    rows = []
    for group, x in eng.d[eng.d._pool].groupby("position_group"):
        cols = GOALKEEPING if group == "GK" else ATTACK + DEFENCE
        x = x[x[[c + "__t" for c in cols]].notna().all(axis=1)].reset_index(drop=True)
        if len(x) < 50:
            continue
        v = eng.embed(x, group, cols)
        ages, pid = x.age.to_numpy(), x.player_id.to_numpy()
        ranks, chance = [], []
        for i in range(len(x)):
            in_window = np.abs(ages - ages[i]) <= age_window
            in_window[i] = False
            same = in_window & (pid == pid[i])
            if not same.any():
                continue
            d = ((v[in_window] - v[i]) ** 2).sum(axis=1)
            best_same = d[(pid[in_window] == pid[i])].min()
            ranks.append(1 + int((d < best_same).sum()))
            chance.append(_chance_hit(int(in_window.sum()), int(same.sum()), k))
        ranks = np.array(ranks)
        rows.append({
            "metric": metric, "group": group, "targets": len(ranks),
            f"hit@{k}": (ranks <= k).mean(), "MRR": (1.0 / ranks).mean(), f"chance_hit@{k}": float(np.mean(chance)),
        })
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    df = pd.read_sql("SELECT * FROM player_season_features", db.connect(args.db))
    res = pd.concat([evaluate(df, m, args.k) for m in METRICS], ignore_index=True)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    print("\nweighted by targets:")
    w = res.assign(h=res[f"hit@{args.k}"] * res.targets, m=res.MRR * res.targets, c=res[f"chance_hit@{args.k}"] * res.targets)
    g = w.groupby("metric")[["targets", "h", "m", "c"]].sum()
    print(pd.DataFrame({f"hit@{args.k}": g.h / g.targets, "MRR": g.m / g.targets, "chance": g.c / g.targets}).round(3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
