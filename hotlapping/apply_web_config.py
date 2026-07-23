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
Admins may change the track/vehicle live in-game (/level, /vehicle). TSU never
persists runtime state, so without help such a change is lost at the nightly
restart and overwritten by the (possibly stale) web config -- which looked to
players like "someone changed the combo without permission".

To let in-game changes survive, this script also *captures* the live combo
from the server's own event output (the newest
/home/data/hotlapping/**/raw/*_event.json -> level.name + a player's
vehicle.name = the combo actually driven) and folds it back into
hotlapping.json. The existing post-restart re-apply then restores what was
really being driven. A web-panel save still wins (deliberate override) and is
the only thing that announces a "New setup" in chat.

LIVE_RESTORE gates the new behaviour:
  False -> shadow: behave exactly as before, only LOG what would change.
  True  -> armed: capture in-game changes; restore them (silently) after
           restart.
Run with --dry-run to print the decision with no side effects at all.
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

CONFIG = "/srv/tsura/server_config/hotlapping.json"
APPLIED = "/srv/tsura/server_config/hotlapping.applied.json"
LIVE = "/srv/tsura/server_config/hotlapping.live.json"
SCRIPTS_DIR = "/home/hotlapping/server/config/Scripts"
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")
EVENT_ROOT = "/home/data/hotlapping"
BADGE = "<color=#20c997>[Hotlapping]</color>"

# False = shadow (log only, behaviour unchanged). True = armed (capture in-game
# combo changes and restore them after the nightly restart).
LIVE_RESTORE = False

SETUP_KEYS = ("track", "vehicle", "hotlap_behind_distance", "events_per_session")


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


def server_running():
    return (
        subprocess.run(
            ["pgrep", "-u", "hotlapping", "-x", "TSUs.x86_64"],
            stdout=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def quoted(name):
    """Quote a track/vehicle name for a TSU console command."""
    if "'" not in name:
        return f"'{name}'"
    if '"' not in name:
        return f'"{name}"'
    raise ValueError(f"name contains both quote characters: {name!r}")


def read_live_combo():
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


def main(dry_run=False):
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
    if cfg == applied:
        return  # nothing to do

    setup_changed = any(cfg.get(k) != applied.get(k) for k in SETUP_KEYS)
    admins_changed = cfg.get("ingame_admins") != applied.get("ingame_admins")
    if not setup_changed and not admins_changed:
        if not dry_run:
            write_json(APPLIED, cfg)
        return

    # Announce a "New setup" only for a genuine change. When armed, a plain
    # post-restart restore of the combo that was already being driven stays
    # silent (that is exactly the misleading broadcast we want to kill).
    if (
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
            f"announce={announce} applied_missing={applied_missing} "
            f"target={track!r}/{vehicle!r} live={live}"
        )
        return

    if not server_running():
        return  # apply on a later run once the server is up
    if os.path.exists(AUTORUN):
        return  # server busy consuming another autorun; retry next minute

    try:
        commands = []
        admins = [str(a[0]) for a in cfg.get("ingame_admins", []) if str(a[0]).isdigit()]
        if admins_changed and admins:
            # admin-only sync never interrupts the running event
            commands += ["/admins /clear"] + [f"/admins /add {sid}" for sid in admins]
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

    with open(AUTORUN, "w") as f:
        f.write("\n".join(commands) + "\n")

    write_json(APPLIED, cfg)

    log(
        f"applied: setup_changed={setup_changed} admins_changed={admins_changed} "
        f"announce={announce} track={track!r} vehicle={vehicle!r} "
        f"distance={distance} events={events}"
    )


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv[1:])
