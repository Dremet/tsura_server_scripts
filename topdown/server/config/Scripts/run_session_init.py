#!/usr/bin/env python3
"""Set up the session for one heat.

TSU only accepts level, vehicle and AI changes during session init -- everything
else is refused with "Cannot change levels after session init". That window is
exactly when the server runs this hook, which is why the heat's track list is
built here rather than pushed over the script port at an arbitrary moment.

The controller writes heat_plan.json and then asks the server for a new session;
this script turns that plan into commands. Each track is queued twice: once for
its one-lap qualifying, once for the race.
"""

import json
import os

PLAN_FILE = "heat_plan.json"
PROGRESS_FILE = "heat_progress.json"
OUTPUT_FILE = "session_init_generated.src"
DONE_FILE = "topdown_event_done"

BADGE = "<color=#fd7e14>[TopDown]</color>"
GREY = "<color=#aaaaaa>"


def read_json(path, fallback):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:                                  # noqa: BLE001
        return fallback


def write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def quoted(name):
    """Quote a name for the console; TSU offers no escaping."""
    if "'" not in name:
        return f"'{name}'"
    if '"' not in name:
        return f'"{name}"'
    raise ValueError(f"name contains both quote characters: {name!r}")


def build_commands(plan):
    rounds = plan.get("rounds") or []
    if not rounds:
        return [f"/broadcast {BADGE} {GREY}No heat planned.</color>"]

    cmds = []
    # Without the timer the lobby waits for every player to press ready, and a
    # single idle player stalls the heat indefinitely. Switchable so a test
    # session can be driven by hand.
    if plan.get("timer_on", True):
        cmds.append("/timerOn = true")
    else:
        cmds.append("/timerOn = false")
    cmds.append("/admins /clear")
    cmds += [f"/admins /add {a[0]}" for a in plan.get("admins", []) if a]

    session_name = plan.get("session_name")
    if session_name:
        # The archive carries tracks, cars, AI settings, per-event race settings
        # AND each track's own camera. A camera cannot be applied any other way:
        # the server reads the container once here and ignores later changes.
        cmds.append(f"/loadsession {quoted(session_name)}")
    else:
        # Fallback if the archive could not be built -- the heat still runs,
        # just with the default camera. The console has one vehicle list for
        # the whole session, so a car pool cannot be honoured here: every car
        # of the heat is offered and players pick.
        cars = []
        for rnd in rounds:
            car = rnd.get("vehicle") or plan.get("vehicle", "")
            if car and car not in cars:
                cars.append(car)
        cmds.append("/vehicles /clear")
        cmds += [f"/vehicle /add {quoted(car)}" for car in cars]
        cmds.append("/levels /clear")
        for rnd in rounds:
            cmds += [f"/level /add {quoted(rnd['track'])}"] * 2

        ai = plan.get("ai", {})
        cmds.append(f"/set ai.aiFill {int(plan.get('ai_fill', 0))}")
        for key in ("aiSkill", "aiSkillLevel1", "aiSkillLevel2",
                    "aiSkillLevel2Percentage", "humanStartPosition"):
            if key in ai:
                cmds.append(f"/set ai.{key} {ai[key]}")
        if ai.get("aiClanTag"):
            cmds.append("/set ai.forceAIClanTag true")
            cmds.append(f"/set ai.aiClanTag {ai['aiClanTag']}")
        cmds.append("/points.pointsForFastestLap = 0")

    # The car is named per track: it can differ from race to race.
    names = ", ".join(f"{r['track']} ({r['vehicle']})" if r.get("vehicle")
                      else r["track"] for r in rounds)
    cmds.append(f"/broadcast {BADGE} Heat #{plan.get('heat_id', '?')} -- "
                f"{len(rounds)} tracks, one lap of qualifying then a race on each.")
    cmds.append(f"/broadcast {BADGE} {GREY}{names}</color>")
    missing = [r["track"] for r in rounds if not r.get("ai_lines", True)]
    if missing:
        cmds.append(f"/broadcast {BADGE} {GREY}No AI lines for "
                    f"{', '.join(missing)} -- those races run without bots.</color>")
    return cmds


def main():
    plan = read_json(PLAN_FILE, {})
    commands = build_commands(plan)

    # A fresh session means a fresh heat: rewind the quali/race cursor so the
    # first event is round 1's qualifying.
    write_json(PROGRESS_FILE, {"heat_id": plan.get("heat_id"),
                               "round": 0, "phase": "quali"})
    if os.path.exists(DONE_FILE):
        os.remove(DONE_FILE)

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(commands) + "\n")


if __name__ == "__main__":
    main()
