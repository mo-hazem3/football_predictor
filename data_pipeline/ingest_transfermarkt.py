"""CLI: python -m data_pipeline.ingest_transfermarkt --leagues EPL Bundesliga --seasons 2014 2025 [--history]

Squads (bio + market value) are loaded first. With --history, per-player market
value and transfer history are fetched for linked players (understat_tm_links)
with at least --min-minutes Understat minutes, most-played first. Everything is cached, so re-runs and
interrupted runs resume without re-downloading.
"""
from __future__ import annotations

import argparse
import sqlite3

from data_pipeline import db
from data_pipeline.sources import transfermarkt as tm


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [[r[c] for c in cols] for r in rows],
    )


def ingest_squads(conn: sqlite3.Connection, leagues: list[str], first: int, last: int) -> int:
    total = 0
    for league in leagues:
        for season in range(first, last + 1):
            try:
                clubs = tm.fetch_clubs(league, season)
            except Exception as exc:
                print(f"  skip {league} {season}: {exc}")
                continue
            n = 0
            for club in clubs:
                try:
                    rows = tm.fetch_squad(club, season, league)
                except Exception as exc:
                    print(f"  skip {club['name']} {season}: {exc}")
                    continue
                _insert(conn, "transfermarkt_squads", rows)
                conn.commit()  # don't hold the write lock while sleeping on the next request
                n += len(rows)
            conn.commit()
            total += n
            print(f"{league} {season}: {len(clubs)} clubs, {n} players")
    return total


def pending_history_players(conn: sqlite3.Connection, min_minutes: int) -> list[int]:
    """Players without history yet, most-played first.

    Needs `understat_tm_links` (run link_understat_tm first): history is only
    worth ~6 s/player for players with enough Understat minutes to be comps.
    """
    return [r[0] for r in conn.execute(
        """SELECT l.tm_player_id
           FROM understat_tm_links l
           JOIN understat_player_seasons u
             ON u.understat_player_id = l.understat_player_id AND u.league = l.league AND u.season = l.season
           WHERE l.tm_player_id NOT IN (SELECT tm_player_id FROM transfermarkt_market_values)
             AND l.tm_player_id NOT IN (SELECT tm_player_id FROM transfermarkt_transfers)
           GROUP BY l.tm_player_id
           HAVING SUM(u.minutes) >= ?
           ORDER BY SUM(u.minutes) DESC""",
        (min_minutes,),
    )]


def ingest_history(conn: sqlite3.Connection, limit: int | None, min_minutes: int) -> int:
    pending = pending_history_players(conn, min_minutes)
    if limit:
        pending = pending[:limit]
    done = 0
    for pid in pending:
        try:
            values, transfers = tm.fetch_market_values(pid), tm.fetch_transfers(pid)
        except Exception as exc:
            print(f"  skip player {pid}: {exc}")
            continue
        _insert(conn, "transfermarkt_market_values", values)
        _insert(conn, "transfermarkt_transfers", transfers)
        conn.commit()
        done += 1
        if done % 50 == 0:
            print(f"history: {done}/{len(pending)} players")
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+", default=list(tm.COMPETITIONS), choices=list(tm.COMPETITIONS))
    ap.add_argument("--seasons", nargs=2, type=int, default=[2014, 2025], metavar=("FIRST", "LAST"),
                    help="inclusive range of season start years")
    ap.add_argument("--history", action="store_true", help="also fetch per-player market-value and transfer history")
    ap.add_argument("--history-limit", type=int, help="cap the number of players fetched in this run")
    ap.add_argument("--min-minutes", type=int, default=900,
                    help="history only for players with at least this many Understat minutes (default 900 ~ 10 full games)")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    print(f"Stored {ingest_squads(conn, args.leagues, *args.seasons)} squad rows.")
    if args.history:
        print(f"Loaded history for {ingest_history(conn, args.history_limit, args.min_minutes)} players.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
