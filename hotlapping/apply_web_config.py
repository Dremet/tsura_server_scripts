"""Apply the tsura.org web-managed hotlapping config to the running server.

Runs from cron every minute as user `hotlapping`. The tsura.org admin panel
writes /srv/tsura/server_config/hotlapping.json; when it differs from the
last applied state (hotlapping.applied.json), this script writes an
autorun.src that sets vehicle, N identical events of the configured track,
and the start-behind distance, then skips to the next event.

restart_server.sh removes the applied marker at boot so the web config is
re-applied shortly after every server restart.

In-game combo changes
---------------------
Admins may change the track/vehicle live in-game (/level, /vehicle). The level
list and the hotlapping settings do survive a restart -- TSU rewrites game.json
at every session end and reloads it at boot; `-setup plain` does NOT clear them.
What used to destroy an in-game change was this script: restart_server.sh wiped
the applied marker, so every morning the (possibly stale) web config was pushed
over whatever an admin had set, which looked to players like "someone changed
the combo without permission".

Two things prevent that now:

* restart_server.sh no longer wipes the marker, it only invalidates
  `ingame_admins` (the one thing TSU really forgets at boot). So nothing is
  re-applied unless the panel was actually saved.
* This script *captures* the live combo back into hotlapping.json, so the panel
  keeps showing what is really being played. The live combo is read from the
  server's own log (config/Logs/log.*.txt), which records every list change
  immediately -- `No levels`, `4 levels: <name>, ...`, `Hotlapping ... with
  <vehicle>` -- even when nobody is connected. The event JSONs under
  /home/data/hotlapping remain a fallback; they are exact but only appear once
  somebody finishes an event.

A web-panel save still wins (deliberate override) and is the only thing that
announces a "New setup" in chat. If the server ends up with no levels at all
(e.g. a level file disappeared), the web config is restored once per boot as a
safety net, silently.

LIVE_RESTORE gates the capture:
  False -> shadow: behave exactly as before, only LOG what would change.
  True  -> armed: capture in-game changes.
Run with --dry-run to print the decision with no side effects at all.
"""

import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

import webconfig

CONFIG = "/srv/tsura/server_config/hotlapping.json"
APPLIED = "/srv/tsura/server_config/hotlapping.applied.json"
LIVE = "/srv/tsura/server_config/hotlapping.live.json"
FORCED = "/srv/tsura/server_config/hotlapping.forced.json"
SERVER_DIR = "/home/hotlapping/server"
SCRIPTS_DIR = os.path.join(SERVER_DIR, "config/Scripts")
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")
VEHICLES_JSON = os.path.join(SCRIPTS_DIR, "vehicles.json")
LEVELS_DIR = os.path.join(SERVER_DIR, "config/Levels")
LOGS_DIR = os.path.join(SERVER_DIR, "config/Logs")
RESTART_LOCK = "/home/hotlapping/.restarting"
EVENT_ROOT = "/home/data/hotlapping"
BADGE = "<color=#20c997>[Hotlapping]</color>"

# A restart lock older than this is stale (restart_server.sh died).
LOCK_MAX_AGE = 900
# Don't push into a server that just booted -- it is still loading content and
# restart_server.sh may still be clearing autorun files.
MIN_UPTIME = 90
# How long to wait for the server to consume our autorun.src before giving up.
AUTORUN_WAIT = 40

# False = shadow (log only, behaviour unchanged). True = armed (capture in-game
# combo changes and restore them after the nightly restart).
LIVE_RESTORE = True

SETUP_KEYS = ("track", "vehicle", "hotlap_behind_distance", "events_per_session")


def collision_changed(cfg, applied):
    return cfg.get("collision") != applied.get("collision")


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def server_pid():
    out = subprocess.run(
        ["pgrep", "-u", "hotlapping", "-x", "TSUs.x86_64"],
        capture_output=True,
        text=True,
    )
    pids = out.stdout.split()
    return pids[0] if out.returncode == 0 and pids else None


def server_uptime():
    """Seconds since the running server started, or None if it is down.
    /proc/<pid> carries the process start time."""
    pid = server_pid()
    if not pid:
        return None
    try:
        return time.time() - os.path.getmtime(f"/proc/{pid}")
    except OSError:
        return None


def restart_in_progress():
    """True while restart_server.sh is stopping/starting the server.

    Without this the per-minute cron races the 05:00 restart: it wrote its
    autorun.src in the very second restart_server.sh deleted stale autorun
    files, so the commands vanished unexecuted while the marker claimed
    success (observed 2026-07-24 and 2026-07-25)."""
    if not os.path.exists(RESTART_LOCK):
        return False
    return (time.time() - mtime(RESTART_LOCK)) < LOCK_MAX_AGE


def wait_consumed(path, timeout):
    """Wait for the server to pick up (delete) an autorun file."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not os.path.exists(path):
            return True
        time.sleep(1)
    return not os.path.exists(path)


def quoted(name):
    """Quote a track/vehicle name for a TSU console command."""
    if "'" not in name:
        return f"'{name}'"
    if '"' not in name:
        return f'"{name}"'
    raise ValueError(f"name contains both quote characters: {name!r}")


TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}): ")
LEVELS_RE = re.compile(r"^\d+ levels?: (.+)$")
NO_LEVELS_RE = re.compile(r"^No levels$")
EVENT_RE = re.compile(r"^Event \d+ / \d+ is about to start in (.+)\.$")
VEHICLE_RE = re.compile(r"^Hotlapping .* with (.+)$")


def _epoch(stamp):
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return 0.0


def _log_files():
    """Server logs, newest first (one file per boot: log.<date>.<time>.txt)."""
    try:
        names = sorted(
            (n for n in os.listdir(LOGS_DIR) if n.startswith("log.") and n.endswith(".txt")),
            reverse=True,
        )
    except OSError:
        return []
    return [os.path.join(LOGS_DIR, n) for n in names]


def _level_names():
    """Track names the server has files for."""
    try:
        return [n[:-4] for n in os.listdir(LEVELS_DIR) if n.endswith(".lvl")]
    except OSError:
        return []


def _current_vehicle():
    """The vehicle the server currently offers, from its own vehicles.json.

    Exact and untruncated, unlike the log line -- the server rewrites this file
    whenever the selection changes."""
    d = read_json(VEHICLES_JSON)
    if not isinstance(d, dict):
        return None
    possible = d.get("possibleVehicles") or []
    selected = (d.get("selectedVehicles") or {}).get("guids") or []
    for v in possible:
        if v.get("guid") in selected and v.get("name"):
            return str(v["name"]).strip()
    if len(possible) == 1 and possible[0].get("name"):
        return str(possible[0]["name"]).strip()
    return None


def _scan_log(path):
    """Last setup state a server log records.

    Returns (state, vehicle, vehicle_ts, exact_names) where state is
    {'track', 'empty', 'ts', 'cut'} or None if the file logs no setup at all.
    The server truncates the level list at ~64 characters ("a, a..."), so a
    name is only trustworthy when it is followed by a comma or the line is not
    truncated; `cut` flags the rest.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None

    state = vehicle = None
    vehicle_ts = ts = 0.0
    exact = []
    for line in lines:
        m = TS_RE.match(line)
        if m:
            ts = _epoch(m.group(1))
            line = line[m.end():]
        if NO_LEVELS_RE.match(line):
            state = {"track": None, "empty": True, "ts": ts, "cut": False}
            continue
        m = LEVELS_RE.match(line)
        if m:
            body = m.group(1)
            first, sep, _ = body.partition(", ")
            cut = not sep and body.endswith("...")
            state = {
                "track": first[:-3].strip() if cut else first.strip(),
                "empty": False,
                "ts": ts,
                "cut": cut,
            }
            continue
        m = EVENT_RE.match(line)
        if m:
            exact.append(m.group(1).strip())
            continue
        m = VEHICLE_RE.match(line)
        if m:
            vehicle, vehicle_ts = m.group(1).strip(), ts
    return state, vehicle, vehicle_ts, exact


def read_live_combo_from_log():
    """Live combo from the server's own log, or None if it logs nothing usable.

    Returns {'empty': True, 'observed_at': ...} when the server currently has
    no levels at all. Walks back through older logs because the level list
    survives a restart: if the current boot has not touched it, the last change
    logged before the restart is still what the server is running.
    """
    for path in _log_files()[:5]:
        scan = _scan_log(path)
        if not scan:
            continue
        state, log_vehicle, vehicle_ts, exact = scan
        if state is None:
            continue  # this boot never touched the setup -> look further back
        if state["empty"]:
            return {"empty": True, "observed_at": state["ts"]}
        track = state["track"]
        if state["cut"]:
            matches = {n for n in exact + _level_names() if n.startswith(track)}
            if len(matches) != 1:
                return None  # ambiguous truncation: better no answer than a wrong one
            track = matches.pop()
        vehicle = _current_vehicle() or log_vehicle
        if not track or not vehicle:
            return None
        return {
            "track": track,
            "vehicle": vehicle,
            "observed_at": max(state["ts"], vehicle_ts),
        }
    return None


def read_live_combo():
    """Live combo: the server log first, its event files as a fallback."""
    combo = read_live_combo_from_log()
    if combo is not None:
        return combo
    return read_live_combo_from_events()


def read_live_combo_from_events():
    """Return {'track','vehicle','observed_at'} from the newest hotlapping
    event file the server wrote, or None. The event JSON records the exact
    level name and each player's vehicle, i.e. the combo actually driven.
    Only the newest few session dirs are inspected to stay cheap on a
    per-minute cron."""
    dirs = []
    for root in (EVENT_ROOT, os.path.join(EVENT_ROOT, "archive")):
        try:
            for name in os.listdir(root):
                if re.match(r"\d{8}_\d{6}$", name):
                    dirs.append(os.path.join(root, name, "raw"))
        except OSError:
            continue
    dirs.sort(reverse=True)
    files = []
    for d in dirs[:8]:
        files.extend(glob.glob(os.path.join(d, "*_event.json")))
    for f in sorted(files, key=mtime, reverse=True):
        d = read_json(f)
        if not isinstance(d, dict):
            continue
        track = (d.get("level") or {}).get("name")
        vehicle = None
        for p in d.get("players") or []:
            v = (p.get("vehicle") or {}).get("name")
            if v:
                vehicle = v
                break
        if track and vehicle:
            return {
                "track": track.strip(),
                "vehicle": vehicle.strip(),
                "observed_at": mtime(f),
            }
    return None


def write_json(path, obj):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o664)
    except OSError:
        pass


def boot_stamp():
    """Start time of the running server process, as an identity for this boot."""
    pid = server_pid()
    if not pid:
        return None
    try:
        return round(os.path.getmtime(f"/proc/{pid}"), 3)
    except OSError:
        return None


def forced_this_boot():
    d = read_json(FORCED)
    stamp = boot_stamp()
    return isinstance(d, dict) and stamp is not None and d.get("boot") == stamp


def mark_forced():
    stamp = boot_stamp()
    if stamp is not None:
        try:
            write_json(FORCED, {"boot": stamp})
        except OSError:
            pass


def main(dry_run=False):
    if restart_in_progress() and not dry_run:
        return  # come back once the server is up again

    cfg = read_json(CONFIG)
    if not isinstance(cfg, dict):
        return  # unreadable/invalid config: do nothing

    try:
        track = str(cfg["track"]).strip()
        vehicle = str(cfg["vehicle"]).strip()
        distance = int(cfg.get("hotlap_behind_distance", 840))
        events = max(1, min(20, int(cfg.get("events_per_session", 5))))
        if not track or not vehicle:
            raise ValueError("track/vehicle empty")
    except Exception as exc:
        log(f"invalid config, not applying: {exc}")
        return

    applied = read_json(APPLIED)
    applied_missing = not isinstance(applied, dict)
    applied_mtime = mtime(APPLIED)

    prev_live = read_json(LIVE)
    live = read_live_combo()
    # The server sits there with no levels at all (a level file went missing, a
    # fresh install, an admin cleared the list): restore the web config once per
    # boot as a safety net, silently.
    live_empty = bool(live) and bool(live.get("empty"))
    if live_empty:
        live = None
    live_is_new = bool(live) and (
        not isinstance(prev_live, dict)
        or (prev_live.get("track"), prev_live.get("vehicle"))
        != (live["track"], live["vehicle"])
    )
    if live and not dry_run:
        try:
            write_json(LIVE, live)
        except OSError:
            pass

    # --- Capture an in-game combo change into the web config -------------
    # Fire only when the live combo differs from what we last applied, was
    # observed AFTER our last apply (a genuine in-game change, not a stale lap
    # from before the last push), and no panel save is pending (cfg still
    # equals applied). Then hotlapping.json becomes the real current combo, so
    # the next post-restart re-apply restores it instead of a stale value.
    if (
        not applied_missing
        and live
        and (live["track"], live["vehicle"])
        != (applied.get("track"), applied.get("vehicle"))
        and (cfg.get("track"), cfg.get("vehicle"))
        == (applied.get("track"), applied.get("vehicle"))
        and live["observed_at"] > applied_mtime
    ):
        if LIVE_RESTORE and not dry_run:
            new = dict(cfg)
            new["track"] = live["track"]
            new["vehicle"] = live["vehicle"]
            write_json(CONFIG, new)
            write_json(APPLIED, new)  # already live on the server; do not re-push
            log(
                f"captured in-game combo into web config: "
                f"{live['track']!r} / {live['vehicle']!r} "
                f"(was {applied.get('track')!r} / {applied.get('vehicle')!r})"
            )
            return
        elif live_is_new or dry_run:
            log(
                f"shadow: would capture in-game combo "
                f"{live['track']!r} / {live['vehicle']!r} "
                f"(applied={applied.get('track')!r} / {applied.get('vehicle')!r}); "
                f"LIVE_RESTORE off"
            )

    applied = applied if isinstance(applied, dict) else {}
    # Restore an empty server at most once per boot, so a track the server
    # cannot load can never turn into a per-minute /continue loop.
    restore_empty = live_empty and not forced_this_boot()
    if cfg == applied and not restore_empty:
        return  # nothing to do

    setup_changed = restore_empty or any(cfg.get(k) != applied.get(k) for k in SETUP_KEYS)
    admins_changed = cfg.get("ingame_admins") != applied.get("ingame_admins")
    physics_changed = collision_changed(cfg, applied)
    if not setup_changed and not admins_changed and not physics_changed:
        if not dry_run:
            write_json(APPLIED, cfg)
        return

    # Announce a "New setup" only for a genuine change. When armed, a plain
    # post-restart restore of the combo that was already being driven stays
    # silent (that is exactly the misleading broadcast we want to kill).
    if restore_empty or (
        LIVE_RESTORE
        and setup_changed
        and live
        and (track, vehicle) == (live["track"], live["vehicle"])
    ):
        announce = False
    else:
        announce = setup_changed

    if dry_run:
        log(
            f"DRY-RUN: setup_changed={setup_changed} admins_changed={admins_changed} "
            f"physics_changed={physics_changed} "
            f"announce={announce} applied_missing={applied_missing} "
            f"restore_empty={restore_empty} target={track!r}/{vehicle!r} live={live}"
        )
        return

    uptime = server_uptime()
    if uptime is None:
        return  # server down: apply on a later run once it is up
    if uptime < MIN_UPTIME:
        return  # still booting: let it finish loading before pushing commands
    if os.path.exists(AUTORUN):
        return  # server busy consuming another autorun; retry next minute

    try:
        commands = []
        admins = [str(a[0]) for a in cfg.get("ingame_admins", []) if str(a[0]).isdigit()]
        if admins_changed and admins:
            # admin-only sync never interrupts the running event
            commands += ["/admins /clear"] + [f"/admins /add {sid}" for sid in admins]
        if physics_changed:
            # physics-only: no /continue, the running event is not disturbed
            commands += webconfig.get_collision_commands(cfg)
        if setup_changed:
            commands += [
                "/refreshfiles",
                "/vehicles /clear",
                f"/vehicle /add {quoted(vehicle)}",
                "/levels /clear",
            ]
            commands += [f"/level /add {quoted(track)}"] * events
            commands += [
                "/respawning.startBehindWhenHotlapping = true",
                f"/respawning.hotlapBehindDistance = {distance}",
            ]
            if announce:
                commands += [
                    f"/broadcast {BADGE} New setup: {track} — {vehicle}",
                    f"/broadcast {BADGE} <color=#aaaaaa>Start-behind distance {distance}, "
                    f"{events} events per session (set via tsura.org).</color>",
                ]
            commands += ["/continue"]
    except ValueError as exc:
        log(f"cannot build commands: {exc}")
        return

    if not commands:
        # e.g. the collision block was removed from the config: there is
        # nothing to send, but the state is now in sync. An empty autorun.src
        # would just sit there and block the next real push.
        write_json(APPLIED, cfg)
        return

    with open(AUTORUN, "w") as f:
        f.write("\n".join(commands) + "\n")

    # Only claim success once the server has actually taken the file. Writing
    # the marker blindly is how a swallowed apply used to stay invisible.
    if not wait_consumed(AUTORUN, AUTORUN_WAIT):
        try:
            os.remove(AUTORUN)
        except OSError:
            pass
        log(
            f"server did not consume autorun.src within {AUTORUN_WAIT}s "
            f"(uptime {uptime:.0f}s) — nothing applied, retrying next minute"
        )
        return

    if restore_empty:
        mark_forced()
    write_json(APPLIED, cfg)

    log(
        f"applied: setup_changed={setup_changed} admins_changed={admins_changed} "
        f"physics_changed={physics_changed} "
        f"announce={announce} restore_empty={restore_empty} track={track!r} "
        f"vehicle={vehicle!r} distance={distance} events={events}"
    )


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv[1:])
