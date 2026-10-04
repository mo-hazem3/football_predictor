"""CLI: python -m data_pipeline.link_fbref_tm [--leagues EPL ...]

Link FBref player-seasons to Transfermarkt players with the same two passes as
link_understat_tm (name pass, then a club pass with a learned club map), but
FBref publishes a birth year, so the year acts as a hard cross-check.

FBref has no player id: an entity is (player_name, born) within a league-season.

Precision check without labelled data: Understat and FBref are linked to
Transfermarkt independently (different evidence), so where both link the same
Transfermarkt player-season their minutes played should agree; a wrong link in
either source shows up as a large gap (see minutes_agreement).
"""
from __future__ import annotations

import argparse
import sqlite3

from data_pipeline import db
from data_pipeline.entity_resolution import PlayerRecord, learn_club_map, resolve, resolve_within_clubs
from data_pipeline.link_understat_tm import tm_records


def fbref_records(conn: sqlite3.Connection, league: str, season: int) -> tuple[list[PlayerRecord], dict[str, int]]:
    by_key: dict[tuple[str, int], dict] = {}
    for table in ("fbref_player_seasons", "fbref_keeper_seasons"):
        for name, born, team, minutes in conn.execute(
            f"SELECT player_name, born, team, minutes FROM {table} WHERE league=? AND season=?", (league, season)
        ):
            rec = by_key.setdefault((name, born or 0), {"clubs": set(), "minutes": 0})
            rec["clubs"].add(team)
            rec["minutes"] += minutes or 0
    records = [
        PlayerRecord("fbref", f"{name}|{born}", name, birth_year=born or None, clubs=frozenset(r["clubs"]))
        for (name, born), r in by_key.items()
    ]
    return records, {f"{n}|{b}": r["minutes"] for (n, b), r in by_key.items()}


def link_league_season(conn: sqlite3.Connection, league: str, season: int) -> dict:
    left, minutes = fbref_records(conn, league, season)
    right = tm_records(conn, league, season)
    if not left or not right:
        return {}

    stage1 = resolve(left, right)
    club_map = learn_club_map(stage1)
    used_l = {m.left.source_id for m in stage1}
    used_r = {m.right.source_id for m in stage1}
    stage2 = resolve_within_clubs(
        [l for l in left if l.source_id not in used_l],
        [r for r in right if r.source_id not in used_r],
        club_map,
    )

    rows = []
    for stage, ms in (("name", stage1), ("club", stage2)):
        for m in ms:
            name, born = m.left.source_id.rsplit("|", 1)
            rows.append((league, season, name, int(born), int(m.right.source_id), m.score, stage))
    conn.execute("DELETE FROM fbref_tm_links WHERE league=? AND season=?", (league, season))
    conn.executemany("INSERT INTO fbref_tm_links VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()

    total = sum(minutes.values()) or 1
    linked = lambda ms: sum(minutes[m.left.source_id] for m in ms)
    return {
        "players": len(left), "linked": len(stage1) + len(stage2), "club_pass": len(stage2),
        "minutes_cov_name": linked(stage1) / total, "minutes_cov": (linked(stage1) + linked(stage2)) / total,
    }


def drop_conflicts(conn: sqlite3.Connection) -> int:
    """An FBref entity (name, born) must map to a single Transfermarkt player across seasons."""
    cur = conn.execute(
        """DELETE FROM fbref_tm_links
           WHERE (player_name, born) IN (SELECT player_name, born FROM fbref_tm_links
                                         GROUP BY 1, 2 HAVING COUNT(DISTINCT tm_player_id) > 1)"""
    )
    conn.commit()
    return cur.rowcount


def minutes_agreement(conn: sqlite3.Connection, tolerance: float = 0.10) -> tuple[int, int]:
    """(agree, compared): independent precision check.

    Where both Understat and FBref are linked to the same Transfermarkt player in
    a league-season, their minutes played should nearly match (same matches, small
    differences in how stoppage/extra time is counted). A wrong link in either
    source shows up as a large gap. Within `tolerance` or 90 minutes counts as agreeing.
    """
    import pandas as pd

    us = pd.read_sql(
        """SELECT l.tm_player_id, l.league, l.season, SUM(u.minutes) AS us_minutes
           FROM understat_tm_links l JOIN understat_player_seasons u
             ON u.understat_player_id = l.understat_player_id AND u.league = l.league AND u.season = l.season
           GROUP BY 1, 2, 3""", conn)
    fb_rows = pd.read_sql(
        """SELECT l.tm_player_id, l.league, l.season, p.minutes FROM fbref_tm_links l
           JOIN (SELECT league, season, player_name, born, minutes FROM fbref_player_seasons
                 UNION ALL SELECT league, season, player_name, born, minutes FROM fbref_keeper_seasons) p
             ON p.league = l.league AND p.season = l.season AND p.player_name = l.player_name AND COALESCE(p.born, 0) = l.born""",
        conn)
    fb = fb_rows.groupby(["tm_player_id", "league", "season"], as_index=False).minutes.sum().rename(columns={"minutes": "fb_minutes"})
    both = us.merge(fb, on=["tm_player_id", "league", "season"])
    gap = (both.us_minutes - both.fb_minutes).abs()
    ok = (gap <= 90) | (gap <= tolerance * both[["us_minutes", "fb_minutes"]].max(axis=1))
    return int(ok.sum()), len(both)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    pairs = conn.execute(
        """SELECT DISTINCT f.league, f.season FROM fbref_player_seasons f
           JOIN transfermarkt_squads t ON t.league = f.league AND t.season = f.season ORDER BY 1, 2"""
    ).fetchall()
    for league, season in pairs:
        if args.leagues and league not in args.leagues:
            continue
        s = link_league_season(conn, league, season)
        if s:
            print(f"{league} {season}: {s['linked']}/{s['players']} players ({s['club_pass']} via club pass); "
                  f"minutes coverage {s['minutes_cov_name']:.1%} -> {s['minutes_cov']:.1%}", flush=True)
    print(f"Dropped {drop_conflicts(conn)} link rows where one FBref player mapped to several Transfermarkt players.")
    agree, n = minutes_agreement(conn)
    if n:
        print(f"Cross-source check: of {n} player-seasons linked by both Understat and FBref, "
              f"{agree} ({agree / n:.1%}) have minutes within 10% / 90 min.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
