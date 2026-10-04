"""CLI: python -m data_pipeline.ingest_understat_teams [--leagues EPL ...] [--seasons 2014 2025] [--no-style]

Per-match team stats come from the league payloads that the player ingest already cached (no
network). The tactical-style breakdown needs one request per team-season (about 1,200 for the
five leagues over 12 seasons, ~20 minutes at one request per second); everything is cached, so
interrupted runs resume where they stopped.
"""
from __future__ import annotations

import argparse
import sqlite3

from data_pipeline import db
from data_pipeline.sources import understat as us
from data_pipeline.sources import understat_teams as ut


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [[r[c] for c in cols] for r in rows],
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leagues", nargs="+", default=us.LEAGUES, choices=us.LEAGUES)
    ap.add_argument("--seasons", nargs=2, type=int, default=[2014, 2025], metavar=("FIRST", "LAST"),
                    help="inclusive range of season start years")
    ap.add_argument("--no-style", action="store_true", help="only the per-match rows (no network requests)")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    for league in args.leagues:
        for season in range(args.seasons[0], args.seasons[1] + 1):
            try:
                payload = us.fetch_league_payload(league, season)
            except Exception as exc:
                print(f"  skip {league} {season}: {exc}", flush=True)
                continue
            matches = ut.match_rows(payload, league, season)
            _insert(conn, "team_matches", matches)
            conn.commit()
            done = 0
            if not args.no_style:
                for team in ut.team_titles(payload):
                    try:
                        data = ut.fetch_team_data(team, season)
                    except Exception as exc:  # one bad team page should not end a 20-minute run
                        print(f"  skip {team} {season}: {type(exc).__name__}: {str(exc)[:100]}", flush=True)
                        continue
                    _insert(conn, "team_style", ut.style_rows(data["statistics"], league, season, team))
                    _insert(conn, "team_players", ut.player_rows(data, league, season, team))
                    conn.commit()  # never hold the write lock while waiting on the network
                    done += 1
            print(f"{league} {season}: {len(matches)} team-matches, style for {done} teams", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
