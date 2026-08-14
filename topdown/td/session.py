"""Build a TSU session archive for one heat.

The server reads a session container once, when the session starts, and it
cannot be changed afterwards -- confirmed by the game's developer (2026-08-01)
and by a live test in which two tracks in one heat stubbornly shared the same
camera. Per-track cameras are therefore only possible by handing the server a
finished archive before the session begins, which is what this module builds.

The archive is assembled from McVizn's exported session, which serves as a parts
bin. A track he exported contributes its `camera5.cam` **byte for byte** unless
the config overrides camera values; a track he never exported is built from its
name and GUID alone, with a camera borrowed from another track or from the
configured default, so a new track can be added from the admin panel without
waiting for a fresh export.

Layout (per event NNN, 1-based):
    levels.json          the track list, one entry per event
    NNN-level.json       which track          (parts bin, or built from the GUID)
    NNN-camera5.cam      its camera           (verbatim, or encoded from config)
    NNN-event.json       race settings        (template + laps/mode/points)
    NNN-vehicles.json    the car              (one per race -- the car pool)
    NNN-ai.json          bot settings         (shared template)
"""

import copy
import json
import os
import zipfile

from . import camfile
from . import guid as guid_mod

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

# Last resort for a track that has neither an exported camera nor one borrowed
# from a sibling: McVizn's overhead settings with the heading left at zero,
# because where north is can only be known per track. It keeps a new track
# playable in top-down view until someone aims the camera properly; the panel's
# "default camera" overrides every value here.
DEFAULT_CAMERA = {
    "cameraPosition": 0,                 # FixedAngle
    "followHistory": 0.0,
    "distance": 115.0,
    "verticalAngle": 49.64517593383789,
    "horizontalAngle": 0.0,
    "behindVelocitySpeed": 20.0,
    "smoothingTime": 0.0,
    "lookMode": 0,
    "rankLockedTarget": False,
    "fov": 23.605838775634766,
    "targetYPosition": 0.5,
    "predictionTime": 0.8846836686134338,
    "predictionSmoothTime": 0.5,
    "blockReactionTime": 1.5,
    "followSecondaryTargetAmount": 50,
    "tracksideSwitchPhase": 50,
    "keepCloseInFreeCamera": False,
    "tracksideInterval": 600,
    "tracksideCameraFixed": False,
}


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

    def level(self, track_name):
        entry = self.tracks.get(track_name)
        return entry["level"] if entry else None

    def camera_bytes(self, track_name):
        """The exported camera file, unchanged, or None."""
        entry = self.tracks.get(track_name)
        if not entry:
            return None
        with open(entry["camera"], "rb") as fh:
            return fh.read()

    def camera_props(self, track_name):
        """The exported camera decoded into properties, or None."""
        entry = self.tracks.get(track_name)
        if not entry:
            return None
        try:
            return camfile.decode_file(entry["camera"])
        except (OSError, ValueError):
            return None


def build_level(track_name, track_guid):
    """A level entry for a track the parts bin does not have.

    The server matches a level by its GUID, so name plus GUID is enough --
    creation time, author and description are cosmetic. This is what lets an
    admin add a track in the panel without McVizn exporting a session first.
    """
    if not track_guid:
        raise ValueError(f"no session parts and no GUID for track {track_name!r}")
    return {
        "guid": guid_mod.to_doc(track_guid),
        "creationTime": 0,
        "name": track_name,
        "makerId": 0,
        "levelType": 0,
        "description": "",
    }


def build_vehicles(template, vehicle_guid):
    """The car for one race: the template with this race's GUID substituted.

    Every event in the archive carries its own vehicles.json, which is how one
    car per race works at all. Anything else in the template (`selectionType`,
    and whatever a future export adds) is kept.
    """
    doc = copy.deepcopy(template)
    if not vehicle_guid:
        return doc
    entries = doc.get("possibleVehicles") or [{}]
    entry = copy.deepcopy(entries[0])
    entry["m_guid"] = guid_mod.to_doc(vehicle_guid)
    doc["possibleVehicles"] = [entry]
    return doc


def resolve_camera(rnd, parts, default_camera=None):
    """This round's camera file, plus a word on where it came from.

    Priority: the config's own values (that is what the panel edits) over the
    exported camera, then a camera borrowed from another track, then the
    configured default. An exported camera with nothing overriding it is passed
    through byte for byte, so the common case stays exactly as McVizn made it.
    """
    track = rnd.get("track", "")
    overrides = {k: v for k, v in (rnd.get("camera_settings") or {}).items()
                 if v is not None}
    exported = parts.camera_props(track)

    if exported is not None and not overrides:
        return parts.camera_bytes(track), "exported"

    base, source = exported, "exported"
    if base is None:
        borrowed = rnd.get("camera_from") or ""
        base = parts.camera_props(borrowed) if borrowed else None
        source = f"copied from {borrowed}"
    if base is None:
        base = dict(DEFAULT_CAMERA)
        base.update(default_camera or {})
        source = "default"

    props = dict(base)
    props.update(overrides)
    if overrides:
        source += " + config"
    return camfile.encode(props), source


def build_session(plan, parts, out_path, ai_fill=None):
    """Write the session archive for `plan` and return the list of event names.

    Each round of the plan becomes two events: a qualifying and a race on the
    same track, so a four-track heat produces eight events.
    """
    rounds = plan.get("rounds") or []
    if not rounds:
        raise ValueError("cannot build a session with no rounds")

    quali_points = plan.get("quali_points", [1])
    race_points = plan.get("race_points", [10, 6, 4, 3, 2, 1])
    quali_laps = int(plan.get("quali_laps", 1))
    # Resolved per round for that round's car by the controller; the heat-wide
    # value is the fallback. Empty means "leave the template's values alone".
    heat_drafting = plan.get("drafting") or {}
    default_camera = plan.get("default_camera_settings") or {}

    # McVizn's export is the baseline; the web config wins over it, so bot
    # strength and where humans start are configured in one place instead of
    # being frozen into the parts bin. Without this only aiFill ever came from
    # the config -- everything else in the archive stayed on the export's values.
    def bots_for(round_ai):
        ai = copy.deepcopy(parts.ai)
        ai.update(plan.get("ai") or {})
        ai.update(round_ai or {})
        if ai_fill is not None:
            ai["aiFill"] = int(ai_fill)
        return ai

    events = []          # (level_doc, camera_bytes, event_doc, vehicles_doc, ai)
    for rnd in rounds:
        level = parts.level(rnd["track"]) or build_level(rnd["track"],
                                                         rnd.get("track_guid"))
        camera, _source = resolve_camera(rnd, parts, default_camera)
        vehicles = build_vehicles(parts.vehicles, rnd.get("vehicle_guid"))
        drafting = rnd.get("drafting") or heat_drafting
        # Bot strength can differ per car, so it is resolved per round too.
        bots = bots_for(rnd.get("ai"))
        for quali in (True, False):
            events.append((
                level,
                camera,
                build_event(parts.event_template,
                            laps=quali_laps if quali else rnd.get("laps", 8),
                            quali=quali,
                            quali_points=quali_points,
                            race_points=race_points,
                            drafting=drafting),
                vehicles,
                bots,
            ))

    tmp = out_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("levels.json",
                    json.dumps(build_levels_index([e[0] for e in events]),
                               indent=1, ensure_ascii=False))
        for index, (level, camera, event, vehicles, ai) in enumerate(events, 1):
            prefix = f"{index:03d}"
            zf.writestr(f"{prefix}-level.json",
                        json.dumps(level, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-event.json",
                        json.dumps(event, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-vehicles.json",
                        json.dumps(vehicles, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-ai.json",
                        json.dumps(ai, indent=1, ensure_ascii=False))
            zf.writestr(f"{prefix}-camera5.cam", camera)
    os.replace(tmp, out_path)
    return [f"{i:03d}" for i in range(1, len(events) + 1)]


def describe_session(plan, parts):
    """One line per round: what the archive will contain and where it came from.

    Worth logging -- a borrowed or defaulted camera is otherwise invisible until
    someone notices the track sitting sideways on screen.
    """
    lines = []
    default_camera = plan.get("default_camera_settings") or {}
    for i, rnd in enumerate(plan.get("rounds") or [], 1):
        _camera, source = resolve_camera(rnd, parts, default_camera)
        level = "parts" if parts.has(rnd["track"]) else "built from GUID"
        lines.append(f"round {i}: {rnd['track']} ({level}) / "
                     f"{rnd.get('vehicle') or '?'} / {rnd.get('laps')} laps / "
                     f"camera {source}")
    return lines
