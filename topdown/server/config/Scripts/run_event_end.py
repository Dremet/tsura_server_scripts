#!/usr/bin/env python3
"""Close out one event: advance the cursor and stamp the results for the pipeline.

Two jobs:

1. Drop the marker that lets run_event_init.py know an event really finished, so
   the qualifying/race cursor may move on. A restart re-fires the event init
   without an event end, and must not flip the phase.

2. Write the heat stamp next to the result files. Nothing in the TSU output says
   which heat a race belonged to, so the pipeline would otherwise have to guess
   from timestamps.

Qualifying runs in hotlapping mode and produces no usable race stats -- those get
discarded, exactly as the TripleHeat scripts do. The qualifying still scores: the
pole point is derived from `start_position == 1` in the race that follows, since
the qualifying is what sets that grid.
"""

import json
import os

PLAN_FILE = "heat_plan.json"
PROGRESS_FILE = "heat_progress.json"
DONE_FILE = "topdown_event_done"
STAMP_FILE = "topdown_heat.json"
EVENT_STATS = "eventstats.json"


def read_json(path, fallback):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:                                  # noqa: BLE001
        return fallback


def main():
    plan = read_json(PLAN_FILE, {})
    progress = read_json(PROGRESS_FILE, {"round": 0, "phase": "quali"})
    rounds = plan.get("rounds") or []
    index = int(progress.get("round", 0))
    rnd = rounds[index] if 0 <= index < len(rounds) else {}

    stamp = {
        "heat_id": plan.get("heat_id"),
        "round": index + 1,
        "rounds_total": len(rounds),
        "phase": progress.get("phase", "quali"),
        "track": rnd.get("track", ""),
        "track_guid": rnd.get("track_guid", ""),
        "vehicle": plan.get("vehicle", ""),
        "laps": rnd.get("laps"),
        "ai_lines": rnd.get("ai_lines", False),
    }
    with open(STAMP_FILE, "w", encoding="utf-8") as fh:
        json.dump(stamp, fh, indent=2, ensure_ascii=False)

    # Tell the next event init that this event genuinely completed.
    with open(DONE_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(stamp["heat_id"] or ""))


if __name__ == "__main__":
    main()
