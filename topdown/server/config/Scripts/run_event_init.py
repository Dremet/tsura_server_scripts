#!/usr/bin/env python3
"""Configure the event the server is about to start.

TSU calls this from eventinit.src, which is the only moment the game guarantees
settings land before the event begins -- which is why the controller does not
send them over the script port itself.

The heat plan is written by topdown_controller.py; this script walks through it,
one event at a time: for each track a one-lap qualifying, then the race whose
grid comes from that qualifying.

The cursor only advances when an event actually finished (run_event_end.py drops
a marker). A server restart re-fires the event init WITHOUT an event end, so the
phase is kept instead of flipping -- the TripleHeat scripts get this wrong and
swap qualifying and race for the rest of the evening after a restart.
"""

import json
import os

import webconfig

PLAN_FILE = "heat_plan.json"
PROGRESS_FILE = "heat_progress.json"
DONE_FILE = "topdown_event_done"     # present iff an event ended since last init
OUTPUT_FILE = "event_init_generated.src"

BADGE = "<color=#fd7e14>[TopDown]</color>"
GREY = "<color=#aaaaaa>"

# Used when the plan is missing entirely -- better a sane race than a broken one.
FALLBACK_LAPS = 8
QUALI_MAX_MINUTES = 5


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


def advance(progress, round_count):
    """Move the cursor on by one event: quali -> race -> next track's quali."""
    if progress.get("phase") == "quali":
        progress["phase"] = "race"
    else:
        progress["phase"] = "quali"
        progress["round"] = int(progress.get("round", 0)) + 1
    if round_count and progress["round"] >= round_count:
        progress["finished"] = True
    return progress


def point_commands(points):
    """Point table for positions 1..20; everything past the table scores zero."""
    points = list(points or [])[:20]
    cmds = [f"/points.position{i} = {p}" for i, p in enumerate(points, 1)]
    cmds += [f"/points.position{i} = 0" for i in range(len(points) + 1, 21)]
    return cmds


# camera.json lives one level above the Scripts directory.
CAMERA_FILE = os.path.join("..", "camera.json")
# Which camera to force. McVizn overrode one of the built-in cameras rather
# than adding a custom preset, and his session files are named "camera5.cam",
# so 5 it is. Override per heat via the plan's "camera_preset".
# Enum (verified live 2026-07-31): 0=None, 1=VeryClose, 2=DashCam, 3=Normal,
# 4=TopView, 5=Close, 6=Trackside, 7=TracksideFixed, 8..12=Preset4..Preset8.
# The server accepts this only during event init.
CAMERA_PRESET_KEY = "preset4"
DEFAULT_CAMERA_PRESET = 9


def apply_camera(rnd, plan):
    """Force the overhead camera for this event, and tune it if configured.

    Forcing only works during event init -- from the lobby or mid-race the
    server answers "Cannot edit event settings after event init" (seen live
    2026-07-31), which is why this lives in the event-init hook.

    Optional per-track camera values are written into camera.json first; the
    server reads that file when it loads the track.
    """
    preset = plan.get("camera_preset", DEFAULT_CAMERA_PRESET)
    if preset in (None, "", 0):
        return []
    cam = rnd.get("camera_settings") or {}
    if not cam:
        return [f"/special.forcedCameraPreset = {preset}"]
    try:
        with open(CAMERA_FILE, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        target = data.setdefault(CAMERA_PRESET_KEY, {})
        target.update({k: v for k, v in cam.items() if v is not None})
        tmp = CAMERA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)
        os.replace(tmp, CAMERA_FILE)
    except Exception:                                  # noqa: BLE001
        # A camera we cannot write is not worth losing the race over.
        pass
    return [f"/special.forcedCameraPreset = {preset}"]


def quali_commands(rnd, plan):
    laps = int(plan.get("quali_laps", 1))
    return point_commands(plan.get("quali_points", [1])) + apply_camera(rnd, plan) + [
        "/refreshfiles",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {laps}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        "/race.startStyle = Countdown",
        "/race.contactRules = EqualGhosts",
        "/race.alwaysHotlapWhenAlone = False",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        f"/broadcast {BADGE} Qualifying at {rnd['track']} -- {laps} lap"
        f"{'s' if laps != 1 else ''} for grid position.",
    ]


def race_commands(rnd, plan, draft):
    laps = int(rnd.get("laps", FALLBACK_LAPS))
    cmds = point_commands(plan.get("race_points", [10, 6, 4, 3, 2, 1])) + apply_camera(rnd, plan) + [
        "/refreshfiles",
        "/race.raceMode = Race",
        f"/race.maxLaps = {laps}",
        "/race.maxMinutes = 1440",
        # The qualifying decides the grid, and there is no reverse grid (F2).
        "/race.startingOrder = LastEvent",
        "/race.startStyle = Countdown",
        "/race.contactRules = Normal",
        "/race.alwaysHotlapWhenAlone = False",
    ]
    for key, value in sorted((draft or {}).items()):
        cmds.append(f"/drafting.{key} = {value}")
    cmds.append(f"/broadcast {BADGE} Race at {rnd['track']} -- {laps} laps. "
                f"{GREY}Grid from qualifying.</color>")
    if not rnd.get("ai_lines", True):
        cmds.append(f"/broadcast {BADGE} {GREY}No AI lines for this track "
                    f"-- running without bots.</color>")
    return cmds


def main():
    plan = read_json(PLAN_FILE, {})
    rounds = plan.get("rounds") or []
    progress = read_json(PROGRESS_FILE, {"round": 0, "phase": "quali"})

    if os.path.exists(DONE_FILE):
        os.remove(DONE_FILE)
        advance(progress, len(rounds))
        write_json(PROGRESS_FILE, progress)

    # When the heat runs from a session archive, every per-event setting --
    # mode, laps, points and the camera -- already comes from that archive.
    # Re-sending them here would fight the session for no gain, so only the
    # announcement is emitted and the quali/race cursor is advanced (the
    # results pipeline needs it to stamp which round a race belonged to).
    if plan.get("session_name"):
        index = int(progress.get("round", 0))
        if 0 <= index < len(rounds):
            rnd = rounds[index]
            quali = progress.get("phase") != "race"
            # The car is named with the track: the pool draws one per race, so
            # players cannot assume it is the same as in the last round.
            car = rnd.get("vehicle") or plan.get("vehicle", "")
            where = f"{rnd['track']} ({car})" if car else rnd["track"]
            if quali:
                line = (f"/broadcast {BADGE} Qualifying at {where} -- "
                        f"{plan.get('quali_laps', 1)} lap for grid position.")
            else:
                line = (f"/broadcast {BADGE} Race at {where} -- "
                        f"{rnd.get('laps', FALLBACK_LAPS)} laps. "
                        f"{GREY}Grid from qualifying.</color>")
            commands = [line]
            if not quali and not rnd.get("ai_lines", True):
                commands.append(f"/broadcast {BADGE} {GREY}No AI lines for this "
                                f"track -- running without bots.</color>")
        else:
            commands = []
        with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as fh:
            fh.write("\n".join(commands) + "\n" if commands else "\n")
        return

    index = int(progress.get("round", 0))
    if not rounds or index >= len(rounds):
        # Nothing planned (or the heat is over and the server queued another
        # event anyway): leave the server on sane settings rather than crashing.
        commands = [f"/broadcast {BADGE} {GREY}No heat plan for this event.</color>"]
    else:
        rnd = rounds[index]
        if progress.get("phase") == "race":
            commands = race_commands(rnd, plan, plan.get("drafting"))
        else:
            commands = quali_commands(rnd, plan)

    # Global vehicle collision settings from the admin panel. Last, so they
    # win over anything the heat plan set for this event.
    commands += webconfig.get_collision_commands(webconfig.load("topdown"))

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(commands) + "\n")


if __name__ == "__main__":
    main()
