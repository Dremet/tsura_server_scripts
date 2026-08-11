"""Build a TSU session archive for one heat.

The server reads a session container once, when the session starts, and it
cannot be changed afterwards -- confirmed by the game's developer (2026-08-01)
and by a live test in which two tracks in one heat stubbornly shared the same
camera. Per-track cameras are therefore only possible by handing the server a
finished archive before the session begins, which is what this module builds.

The archive is assembled from McVizn's exported session, which serves as a parts
bin: his `camera5.cam` files are copied in **byte for byte**, so the cameras are
exactly his -- no decoding, no rounding, no guessing at fields.

Layout (per event NNN, 1-based):
    levels.json          the track list, one entry per event
    NNN-level.json       which track          (per track, from the parts bin)
    NNN-camera5.cam      its camera           (per track, copied verbatim)
    NNN-event.json       race settings        (template + laps/mode/points)
    NNN-vehicles.json    the car              (shared template)
    NNN-ai.json          bot settings         (shared template)
"""

import copy
import json
import os
import zipfile

RACE_MODE_RACE = 0
RACE_MODE_HOTLAPPING = 1

# Enum values as stored in the JSON, which are NOT the console values -- read off
# the server with /savesettings (2026-08-04). Confusing 1 with 3 here put every
# race on a reversed grid: McVizn qualified fifth and started last.
STARTING_ORDER_STANDINGS = 0
STARTING_ORDER_REVERSE_STANDINGS = 1
STARTING_ORDER_RANDOM = 2
STARTING_ORDER_LAST_EVENT = 3      # grid from the previous event = the quali
CONTACT_RULES_NORMAL = 0
CONTACT_RULES_GHOSTS = 2
CONTACT_RULES_EQUAL_GHOSTS = 3     # no collisions -- what a qualifying wants
# "forcedCameraPreset" in the JSON encoding; 25 == console value 9 == Preset5,
# which is the slot McVizn's camera5.cam files occupy.
CAMERA_PRESET_JSON = 25


def _read_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def point_table(points):
    """Turn a points list into the position1..position20 block TSU expects."""
    points = list(points or [])[:20]
    table = {f"position{i}": int(p) for i, p in enumerate(points, 1)}
    for i in range(len(points) + 1, 21):
        table[f"position{i}"] = 0
    return table


def build_event(template, *, laps, quali, quali_points, race_points,
                camera_preset=CAMERA_PRESET_JSON, drafting=None):
    """One event's settings: the template with this round's values applied."""
    ev = copy.deepcopy(template)
    race = ev.setdefault("race", {})
    race["raceMode"] = RACE_MODE_HOTLAPPING if quali else RACE_MODE_RACE
    race["maxLaps"] = int(laps)
    race["alwaysHotlapWhenAlone"] = False
    if quali:
        race["maxMinutes"] = 5.0
        race["startingOrder"] = STARTING_ORDER_STANDINGS
        # Everyone drives their lap alone -- no collisions in qualifying.
        race["contactRules"] = CONTACT_RULES_EQUAL_GHOSTS
    else:
        race["maxMinutes"] = 1440.0
        # The grid comes from the qualifying that just ran, and is NOT reversed.
        race["startingOrder"] = STARTING_ORDER_LAST_EVENT
        race["contactRules"] = CONTACT_RULES_NORMAL
    points = race.setdefault("points", {})
    points.update(point_table(quali_points if quali else race_points))
    # McVizn's scheme has no fastest-lap bonus; the game defaults to one.
    points["pointsForFastestLap"] = 0
    # Drafting is per car -- the VoZzer gets a bigger tow than the McTopper --
    # so it comes from the config rather than from McVizn's exported template.
    # run_event_init.py cannot do this: with a session archive in play it sends
    # no per-event settings at all, and the archive wins over anything later.
    if drafting:
        ev.setdefault("drafting", {}).update(drafting)
    ev.setdefault("special", {})["forcedCameraPreset"] = camera_preset
    return ev


def build_levels_index(level_docs):
    """levels.json -- the track list, in the order the events are driven."""
    return {
        "levels": [{"m_guid": doc["guid"]} for doc in level_docs],
        "heats": 1,
        "repeatLoops": 1,
        "order": 0,
        "maxLevels": 1000,
        "standingsHistory": 100,
    }


class PartsBin:
    """McVizn's exported session, used as a source of per-track building blocks."""

    def __init__(self, root):
        self.root = root
        self.event_template = _read_json(os.path.join(root, "event.json"))
        self.vehicles = _read_json(os.path.join(root, "vehicles.json"))
        self.ai = _read_json(os.path.join(root, "ai.json"))
        self.tracks = {}
        tracks_dir = os.path.join(root, "tracks")
        for name in sorted(os.listdir(tracks_dir)):
            path = os.path.join(tracks_dir, name)
            level = _read_json(os.path.join(path, "level.json"))
            self.tracks[level["name"]] = {
                "level": level,
                "camera": os.path.join(path, "camera5.cam"),
            }

    def has(self, track_name):
        return track_name in self.tracks

    def missing(self, track_names):
        return [t for t in track_names if t not in self.tracks]


def build_session(plan, parts, out_path, ai_fill=None):
    """Write the session archive for `plan` and return the list of event names.

    Each round of the plan becomes two events: a qualifying and a race on the
    same track, so a four-track heat produces eight events.
    """
    rounds = plan.get("rounds") or []
    if not rounds:
        raise ValueError("cannot build a session with no rounds")
    missing = parts.missing([r["track"] for r in rounds])
    if missing:
        raise ValueError(f"no session parts for: {', '.join(missing)}")

    quali_points = plan.get("quali_points", [1])
    race_points = plan.get("race_points", [10, 6, 4, 3, 2, 1])
    quali_laps = int(plan.get("quali_laps", 1))
    # Already resolved for this heat's car by the controller; empty means "leave
    # the template's values alone".
    drafting = plan.get("drafting") or {}

    # McVizn's export is the baseline; the web config wins over it, so bot
    # strength and where humans start are configured in one place instead of
    # being frozen into the parts bin. Without this only aiFill ever came from
    # the config -- everything else in the archive stayed on the export's values.
    ai = copy.deepcopy(parts.ai)
    ai.update(plan.get("ai") or {})
    if ai_fill is not None:
        ai["aiFill"] = int(ai_fill)

    events = []          # (level_doc, camera_path, event_doc)
    for rnd in rounds:
        entry = parts.tracks[rnd["track"]]
        for quali in (True, False):
            events.append((
                entry["level"],
                entry["camera"],
                build_event(parts.event_template,
                            laps=quali_laps if quali else rnd.get("laps", 8),
                            quali=quali,
                            quali_points=quali_points,
                            race_points=race_points,
                            drafting=drafting),
            ))

    tmp = out_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("levels.json",
                    json.dumps(build_levels_index([e[0] for e in events]),
                               indent=1, ensure_ascii=False))
        for index, (level, camera_path, event) in enumerate(events, 1):
            prefix = f"{index:03d}"
            zf.writestr(f"{prefix}-level.json",
                        json.dumps(level, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-event.json",
                        json.dumps(event, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-vehicles.json",
                        json.dumps(parts.vehicles, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-ai.json",
                        json.dumps(ai, indent=1, ensure_ascii=False))
            # Copied verbatim: this is the whole point of going through a
            # session archive rather than writing camera.json ourselves.
            with open(camera_path, "rb") as fh:
                zf.writestr(f"{prefix}-camera5.cam", fh.read())
    os.replace(tmp, out_path)
    return [f"{i:03d}" for i in range(1, len(events) + 1)]
