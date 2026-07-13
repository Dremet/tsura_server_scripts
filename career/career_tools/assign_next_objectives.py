#!/usr/bin/env python3
"""Assign next Monday's race-day challenges (cron: Tuesdays 00:00).

Runs right after a race night, once the pipeline has scored all of the
evening's races, so the following race day's challenges are visible on
tsura.org/career for the whole week. Idempotent: drivers that already
have an objective for that date keep it — the Monday-20:55 prep
(career_prepare_session.py) also keeps existing rows and only fills in
drivers who enrolled later in the week.
"""
import datetime
import os
import sys

import psycopg

from career_prepare_session import assign_objectives


def next_monday(today: datetime.date) -> datetime.date:
    """The next Monday strictly after `today` (a Monday maps to +7)."""
    return today + datetime.timedelta(days=(0 - today.weekday()) % 7 or 7)


def main() -> None:
    db_url = os.environ.get("CAREER_DB_URL") or os.environ.get("TSU_PROD_POSTGRES_URL")
    if not db_url:
        print("ERROR: CAREER_DB_URL / TSU_PROD_POSTGRES_URL not set",
              file=sys.stderr)
        sys.exit(1)
    race_date = next_monday(datetime.date.today())
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM career.seasons "
                    "WHERE status='active' LIMIT 1")
        season = cur.fetchone()
        if not season:
            print("[career-objectives] no active season - nothing to do")
            return
        assigned = assign_objectives(conn, season["id"], race_date)
    print(f"[career-objectives] season '{season['name']}', "
          f"race day {race_date}: {len(assigned)} challenges assigned")
    for sid, desc in sorted(assigned.items()):
        print(f"  {sid} -> {desc}")


if __name__ == "__main__":
    main()
