"""CLI: python -m data_pipeline.link_understat_tm [--leagues EPL ...]

Link Understat player ids to Transfermarkt player ids, one league-season at a
time, in two passes (see entity_resolution): global name match, then a
club-aware pass for what is left. Prints minutes-weighted coverage, which is
the honest metric: missing a bench player matters far less than missing a starter.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date

from data_pipeline import db
from data_pipeline.entity_resolution import PlayerRecord, learn_club_map, resolve, resolve_within_clubs


def tm_records(conn: sqlite3.Connection, league: str, season: int) -> list[PlayerRecord]:
    """One record per Transfermarkt player: a mid-season mover appears in two squads."""
    by_id: dict[int, dict] = {}
    for pid, name, birth, nat, club in conn.execute(
        "SELECT tm_player_id, player_name, birth_date, nationality, club_name FROM transfermarkt_squads WHERE league=? AND season=?",
        (league, season),
    ):
        rec = by_id.setdefault(pid, {"name": name, "birth": birth, "nat": nat, "clubs": set()})
        rec["clubs"].add(club)
    return [
        PlayerRecord("transfermarkt", str(pid), r["name"], date.fromisoformat(r["birth"]) if r["birth"] else None, r["nat"], frozenset(r["clubs"]))
        for pid, r in by_id.items()
    ]


def understat_records(conn: sqlite3.Connection, league: str, season: int) -> tuple[list[PlayerRecord], dict[str, int]]:
    by_id: dict[int, dict] = {}
    for pid, name, team, minutes in conn.execute(
        "SELECT understat_player_id, player_name, team, minutes FROM understat_player_seasons WHERE league=? AND season=?",
        (league, season),
    ):
        rec = by_id.setdefault(pid, {"name": name, "clubs": set(), "minutes": 0})
        rec["clubs"].update(team.split(","))  # Understat joins a mover's clubs with commas
        rec["minutes"] += minutes
    records = [PlayerRecord("understat", str(pid), r["name"], clubs=frozenset(r["clubs"])) for pid, r in by_id.items()]
    return records, {str(pid): r["minutes"] for pid, r in by_id.items()}


def link_league_season(conn: sqlite3.Connection, league: str, season: int) -> dict:
    left, minutes = understat_records(conn, league, season)
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

    rows = [(int(m.left.source_id), int(m.right.source_id), league, season, m.score, stage)
            for stage, ms in (("name", stage1), ("club", stage2)) for m in ms]
    conn.execute("DELETE FROM understat_tm_links WHERE league=? AND season=?", (league, season))
    conn.executemany("INSERT INTO understat_tm_links VALUES (?,?,?,?,?,?)", rows)
    conn.commit()

    total = sum(minutes.values())
    linked = lambda ms: sum(minutes[m.left.source_id] for m in ms)
    return {
        "players": len(left), "linked": len(stage1) + len(stage2), "club_pass": len(stage2),
        "clubs_mapped": len(club_map),
        "minutes_cov_name": linked(stage1) / total, "minutes_cov": (linked(stage1) + linked(stage2)) / total,
    }


def drop_conflicts(conn: sqlite3.Connection) -> int:
    """Remove links where one player maps to several players on the other side.

    Understat ids and Transfermarkt ids are each stable across seasons, so a
    consistent link is one-to-one over the whole table. Conflicts are almost
    always mononyms ('Juanfran', 'Emerson') that name matching cannot separate
    and Understat gives no birth date to break the tie; we refuse to guess
    and leave those players unlinked.
    """
    cur = conn.execute(
        """DELETE FROM understat_tm_links
           WHERE understat_player_id IN (SELECT understat_player_id FROM understat_tm_links
                                         GROUP BY 1 HAVING COUNT(DISTINCT tm_player_id) > 1)
              OR tm_player_id IN (SELECT tm_player_id FROM understat_tm_links
                                  GROUP BY 1 HAVING COUNT(DISTINCT understat_player_id) > 1)"""
    )
    conn.commit()
    return cur.rowcount


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    pairs = conn.execute(
        """SELECT DISTINCT u.league, u.season FROM understat_player_seasons u
           JOIN transfermarkt_squads t ON t.league = u.league AND t.season = u.season ORDER BY 1, 2"""
    ).fetchall()
    for league, season in pairs:
        if args.leagues and league not in args.leagues:
            continue
        s = link_league_season(conn, league, season)
        if s:
            print(f"{league} {season}: {s['linked']}/{s['players']} players ({s['club_pass']} via club pass, "
                  f"{s['clubs_mapped']} clubs mapped); minutes coverage {s['minutes_cov_name']:.1%} -> {s['minutes_cov']:.1%}")
    print(f"Dropped {drop_conflicts(conn)} link rows involved in many-to-one conflicts (mononyms).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
