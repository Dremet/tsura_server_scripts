#!/usr/bin/env python3
"""Topdown heat controller.

Runs as user `topdown` alongside the game server and drives the matchmaking:
players join an empty server, a countdown runs, and a heat of four tracks --
each a one-lap qualifying followed by a race -- plays out automatically.

It talks to the game over the TSU script port (127.0.0.1:7766), which the server
only opens when started with `-scriptPort`. The port is bidirectional: log lines
and command replies arrive on the same stream. Verified live on 2026-07-31.

Per-event settings (qualifying versus race, lap count, points) are NOT sent from
here. They are applied by run_event_init.py through the server's own event-init
hook, which is the only moment TSU guarantees the settings land before the event
starts. This process writes the heat plan to disk; that script reads it.

Usage:  topdown_controller.py [--once] [--dry-run]
"""

import argparse
import json
import os
import random
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from td import heat as heat_mod
from td import protocol
from td import session as session_mod
from td.machine import HeatMachine

HOME = os.path.expanduser("~")
SCRIPTS = os.path.join(HOME, "server", "config", "Scripts")
AI_DIR = os.path.join(HOME, "server", "config", "AI")
PLAN_PATH = os.path.join(SCRIPTS, "heat_plan.json")
# The heat's session archive. The server reads a session container once, at
# session start, so per-track cameras only work if the archive is complete
# before the session begins.
PARTS_DIR = os.path.join(HOME, "session_parts")
SESSION_NAME = "topdown_heat"
SESSION_DIR = os.path.join(HOME, "server", "config", "Sessions")
SESSION_PATH = os.path.join(SESSION_DIR, SESSION_NAME + ".zip")
PROGRESS_PATH = os.path.join(SCRIPTS, "heat_progress.json")
STATE_PATH = os.path.join(HOME, "topdown_state.json")
LOG_PATH = os.path.join(HOME, "controller.log")
# Every line the server sends, so an unrecognised message can be diagnosed after
# the fact instead of by guessing. Only the controller may hold the script port,
# so there is no second client that could watch along.
RAW_LOG_PATH = os.path.join(HOME, "controller.raw.log")
RAW_LOG_MAX_BYTES = 5 * 1024 * 1024

HOST, PORT = "127.0.0.1", 7766
RECONNECT_SECONDS = 5
# How long to wait for the roster before assuming the reply gotlost.
WHO_TIMEOUT = 5.0
# Re-ask for the roster this often even when nothing happened, so a missed
# join/leave line cannot leave the controller with a stale idea of the lobby.
WHO_INTERVAL = 30.0

DEFAULT_CONFIG = {
    # The car pool: one of these is drawn per race (André, 2026-08-11). Both
    # have AI driving lines for every track the server knows.
    "vehicles": [
        {"name": "VoZzer", "guid": "17xxzrmve5gb-3868ch8", "weight": 1.0},
        {"name": "McTopper v1", "guid": "128pn7m9fecb-32z2vmh", "weight": 1.0},
    ],
    "tracks_per_heat": 4,
    "lap_bonus_max_pct": 20,
    "countdown_seconds": 90,
    "cooldown_seconds": 60,
    "vote_seconds": 60,
    "bot_fill": 14,
    "max_drivers": 20,
    "bots_off_from_humans": 6,
    "quali": {"laps": 1, "points": [1]},
    "race": {"points": [10, 6, 4, 3, 2, 1]},
    # Applies to every car; `drafting_by_vehicle` bends it per car afterwards.
    # 35/18 are McVizn's numbers for the VoZzer (2026-08-11); the McTopper is
    # quicker in a tow and keeps the original 14%.
    "drafting": {"maxDraftingDistance": 35, "draftingSpeedEffect": 18},
    "drafting_by_vehicle": {"McTopper v1": {"draftingSpeedEffect": 14}},
    # Bots wear a [BOT] tag, from McVizn's exported session (2026-07-31).
    # His skill 10 (= Custom1, an AI group the server does not even have a file
    # for) was too strong, so the bots run on 3 = Medium since 2026-08-11.
    # aiSkillLevel1/2 only matter for 100 = Mixed.
    # humanStartPosition is HumanStartPositionType: 0 = Default (the grid is not
    # rigged), 1 = ForceAtFirstEvent, 2 = ForceAlways. It sat on 2 with
    # forcedStartPosition 20, which pushed every human to the back of the grid.
    "ai": {
        "aiSkill": 3,
        "aiSkillLevel1": 3,
        "aiSkillLevel2": 1,
        "aiSkillLevel2Percentage": 50,
        "humanStartPosition": 0,
        "aiClanTag": "BOT",
    },
    # Names and GUIDs resolved against the live server; lap counts from McVizn.
    # No camera values here on purpose: every one of these tracks has an
    # exported camera5.cam in the parts bin, and that file is the truth. A
    # track only needs `camera_settings` once someone edits the camera in the
    # panel, or `camera_from` to borrow another track's.
    "tracks": [
        {"name": "Buffalo Hill - Rallycross v1.0", "guid": "z1s768q5723-2z9rhj7",
         "laps": 12, "type": "Rallycross", "pit": True, "weight": 1.0},
        {"name": "CSup - Lost Lagoons v1", "guid": "xvf09b5nq83-2xw55w3",
         "laps": 6, "type": "Circuit", "pit": True, "weight": 1.0},
        {"name": "CSup Sugar Hill V1.0", "guid": "z316kaggp23-2zcdqea",
         "laps": 14, "type": "Circuit", "pit": True, "weight": 1.0},
        {"name": "Maple Ridge v1.1", "guid": "13ng23pntnl3-3472zvj",
         "laps": 14, "type": "Circuit", "pit": False, "weight": 1.0},
        {"name": "Jonno Island v1.0", "guid": "139k2kmmzws3-33vswqr",
         "laps": 8, "type": "Circuit", "pit": True, "weight": 1.0},
        {"name": "E.V.M.C. V1", "guid": "11kcwn867t23-329n370",
         "laps": 10, "type": "Circuit", "pit": True, "weight": 1.0},
        # Added 2026-08-11 from McVizn's export.
        {"name": "Distant Island", "guid": "1d4pxkexwfv3-3dd3b8l",
         "laps": 11, "type": "Circuit", "pit": True, "weight": 1.0},
        {"name": "Kemora 1983 v1.0", "guid": "kmhb9dgbac3-2m6dead",
         "laps": 11, "type": "Circuit", "pit": True, "weight": 1.0},
    ],
    "ingame_admins": [],
}


def log(message):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def raw_log(line):
    """Append one received line, rotating once the file gets large."""
    try:
        if os.path.exists(RAW_LOG_PATH) and \
                os.path.getsize(RAW_LOG_PATH) > RAW_LOG_MAX_BYTES:
            os.replace(RAW_LOG_PATH, RAW_LOG_PATH + ".1")
        with open(RAW_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    except OSError:
        pass


def load_config():
    """Web config merged over the built-in defaults.

    A missing or broken config must never stop heats from running, so anything
    unreadable falls back to the defaults key by key.
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        sys.path.insert(0, SCRIPTS)
        import webconfig
        web = webconfig.load("topdown")
    except Exception as exc:                       # noqa: BLE001 - never fatal
        log(f"config: using built-in defaults ({exc})")
        return cfg
    if not isinstance(web, dict):
        return cfg
    for key, value in web.items():
        if key == "tracks" and not value:
            continue                               # never end up with no tracks
        cfg[key] = value
    return cfg


def _per_vehicle(config, shared_key, by_vehicle_key, vehicle):
    """The shared block for `vehicle`, with that car's own overrides applied.

    Names are matched exactly as the config spells them, case-insensitively.
    """
    values = dict(config.get(shared_key) or {})
    for name, overrides in (config.get(by_vehicle_key) or {}).items():
        if str(name).lower() == str(vehicle or "").lower():
            values.update(overrides or {})
    return values


def resolve_drafting(config, vehicle):
    """Drafting settings for `vehicle`.

    The tow is a property of the car, not of the track: the VoZzer and the
    McTopper each get their own number (McVizn, 2026-08-11).
    """
    return _per_vehicle(config, "drafting", "drafting_by_vehicle", vehicle)


def resolve_ai(config, vehicle):
    """Bot settings for `vehicle`.

    Bots are quicker in one car than in another, so the strength belongs to the
    car as well: André asked for Medium High in the VoZzer only (2026-08-14).
    """
    return _per_vehicle(config, "ai", "ai_by_vehicle", vehicle)


def _read_json(path, fallback):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:                              # noqa: BLE001
        return fallback


def _write_json(path, data):
    """Write atomically -- run_event_init.py may read this at any moment."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def next_heat_id():
    """Heat IDs are global and never reused, including across restarts (F4)."""
    state = _read_json(STATE_PATH, {})
    heat_id = int(state.get("last_heat_id", 0)) + 1
    state["last_heat_id"] = heat_id
    _write_json(STATE_PATH, state)
    return heat_id


class Controller:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.config = load_config()
        self.sock = None
        self.buffer = b""
        self.machine = HeatMachine(
            self.config, random.Random(), self.build_plan, log=log
        )
        self.who_expect = None
        self.who_buffer = {}
        self.who_asked_at = 0.0
        self.last_who = 0.0

    # --- plan ------------------------------------------------------------

    def build_plan(self):
        """Compose a heat and publish it for the event-init hook."""
        self.config = load_config()
        self.machine.config = self.config
        ai_pairs = heat_mod.available_ai_lines(AI_DIR)
        plan = heat_mod.build_heat_plan(self.config, random.Random(), ai_pairs)
        plan["heat_id"] = next_heat_id()
        plan["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        plan["quali_points"] = self.config.get("quali", {}).get("points", [1])
        plan["race_points"] = self.config.get("race", {}).get("points",
                                                              [10, 6, 4, 3, 2, 1])
        # Per round, because the car changes between races and both the tow and
        # the bots' pace belong to the car. The heat-wide values stay for the
        # fallback path that runs without a session archive.
        for rnd in plan.get("rounds") or []:
            rnd["drafting"] = resolve_drafting(self.config, rnd.get("vehicle"))
            rnd["ai"] = resolve_ai(self.config, rnd.get("vehicle"))
        plan["drafting"] = resolve_drafting(self.config, plan.get("vehicle"))
        plan["default_camera_settings"] = self.config.get(
            "default_camera_settings", {})
        plan["admins"] = self.config.get("ingame_admins", [])
        plan["ai"] = self.config.get("ai", {})
        # 9 == "Preset5" on the console, which is what McVizn's session files
        # use (they store 25, the JSON encoding of the same camera).
        plan["camera_preset"] = self.config.get("camera_preset", 9)
        # Off only for hand-driven tests; a live heat needs it or one idle
        # player stalls the lobby forever.
        plan["timer_on"] = self.config.get("timer_on", True)
        # Decided here, not in the session-init hook: only the controller knows
        # how many humans are on right now (bots stand down from six).
        plan["ai_fill"] = self.machine.effective_bot_fill()
        # Build the session archive before anything else: without it the heat
        # cannot run, so a failure here must abort the heat rather than start a
        # session with stale tracks.
        plan["session_name"] = None
        if not self.dry_run:
            try:
                parts = session_mod.PartsBin(PARTS_DIR)
                session_mod.build_session(plan, parts, SESSION_PATH,
                                          ai_fill=plan["ai_fill"])
                plan["session_name"] = SESSION_NAME
                log(f"session archive built: {SESSION_PATH}")
                for line in session_mod.describe_session(plan, parts):
                    log(f"  {line}")
            except Exception as exc:                   # noqa: BLE001
                log(f"could not build session archive ({exc}) -- "
                    f"falling back to individual commands")

        if not self.dry_run:
            _write_json(PLAN_PATH, plan)
            # Reset the hook's cursor so the new heat starts at round 1 quali.
            _write_json(PROGRESS_PATH, {"heat_id": plan["heat_id"],
                                        "round": 0, "phase": "quali", "done": False})
        return plan

    # --- transport -------------------------------------------------------

    def connect(self):
        self.sock = socket.create_connection((HOST, PORT), timeout=5)
        self.sock.settimeout(1.0)
        self.buffer = b""
        log(f"connected to script port {HOST}:{PORT}")

    def send(self, commands):
        if not commands:
            return
        for cmd in commands:
            log(f"-> {cmd}")
            if self.dry_run or not self.sock:
                continue
            try:
                self.sock.sendall((cmd + "\n").encode("utf-8"))
            except OSError as exc:
                log(f"send failed ({exc}) -- dropping connection")
                self.close()
                return
            # The server processes one command per line; a short gap keeps long
            # bursts (a heat setup is ~20 lines) from being coalesced.
            time.sleep(0.05)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def read_lines(self):
        try:
            chunk = self.sock.recv(8192)
        except socket.timeout:
            return []
        except OSError as exc:
            log(f"read failed ({exc})")
            self.close()
            return []
        if not chunk:
            log("script port closed the connection")
            self.close()
            return []
        self.buffer += chunk
        lines = []
        while b"\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n", 1)
            lines.append(raw.decode("utf-8", "replace"))
        return lines

    # --- roster ----------------------------------------------------------

    def ask_who(self, now):
        """Ask the server who is on. Names alone never establish identity."""
        self.who_asked_at = now
        self.last_who = now
        self.send(["/who /id"])

    def handle_who_entry(self, event, now):
        self.who_buffer[event["steam_id"]] = event["name"]
        if self.who_expect is not None and len(self.who_buffer) >= self.who_expect:
            self.finish_who(now)

    def finish_who(self, now):
        roster, self.who_buffer = dict(self.who_buffer), {}
        self.who_expect = None
        self.who_asked_at = 0.0
        self.send(self.machine.set_players(roster, now))

    # --- main loop -------------------------------------------------------

    def handle(self, line, now):
        raw_log(line)
        event = protocol.parse_line(line)
        if not event:
            return
        kind = event["kind"]

        if kind == protocol.WHO_HEADER:
            self.who_expect = event["count"]
            self.who_buffer = {}
            if event["count"] == 0:
                self.finish_who(now)
        elif kind == protocol.WHO_ENTRY:
            self.handle_who_entry(event, now)
        elif kind in (protocol.JOIN, protocol.LEAVE):
            log(f"<- {line.strip()}")
            self.ask_who(now)
        elif kind == protocol.CHAT:
            steam_id = self.steam_id_for(event["name"])
            self.send(self.machine.on_chat(steam_id, event["name"],
                                           event["text"], now))
        elif kind == protocol.EVENT_ENDED:
            log("<- event ended")
            self.send(self.machine.on_event_ended(now))
            self.ask_who(now)
        elif kind == protocol.SESSION_STARTED:
            log("<- session init")
            self.send(self.machine.on_session_started(now))
            self.ask_who(now)
        elif kind == protocol.SESSION_ENDED:
            log("<- session end")
            self.send(self.machine.on_session_ended(now))
        elif kind == protocol.EVENT_UPCOMING and event.get("track"):
            log(f"<- event {event['index']}/{event['total']} at {event['track']}")

    def steam_id_for(self, name):
        for steam_id, known in self.machine.humans.items():
            if known == name:
                return steam_id
        return None

    def run(self, once=False):
        log("controller starting")
        while True:
            if not self.sock:
                try:
                    self.connect()
                    self.ask_who(time.time())
                except OSError as exc:
                    log(f"cannot reach script port ({exc}); retry in "
                        f"{RECONNECT_SECONDS}s")
                    if once:
                        return 1
                    time.sleep(RECONNECT_SECONDS)
                    continue

            for line in self.read_lines():
                self.handle(line, time.time())

            now = time.time()
            self.send(self.machine.tick(now))

            # A "/who /id" reply that never arrived must not wedge the roster.
            if self.who_asked_at and now - self.who_asked_at > WHO_TIMEOUT:
                if self.who_buffer or self.who_expect == 0:
                    self.finish_who(now)
                else:
                    self.who_expect = None
                    self.who_asked_at = 0.0
            elif now - self.last_who > WHO_INTERVAL:
                self.ask_who(now)

            if once:
                return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true",
                    help="single pass, for smoke tests")
    ap.add_argument("--dry-run", action="store_true",
                    help="log commands instead of sending them")
    args = ap.parse_args()
    try:
        return Controller(dry_run=args.dry_run).run(once=args.once) or 0
    except KeyboardInterrupt:
        log("controller stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
