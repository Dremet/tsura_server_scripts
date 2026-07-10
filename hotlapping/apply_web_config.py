"""Apply the tsura.org web-managed hotlapping config to the running server.

Runs from cron every minute as user `hotlapping`. The tsura.org admin panel
writes /srv/tsura/server_config/hotlapping.json; when it differs from the
last applied state (hotlapping.applied.json), this script writes an
autorun.src that sets vehicle, N identical events of the configured track,
and the start-behind distance, then skips to the next event.

restart_server.sh removes the applied marker at boot so the web config is
re-applied shortly after every server restart.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

CONFIG = "/srv/tsura/server_config/hotlapping.json"
APPLIED = "/srv/tsura/server_config/hotlapping.applied.json"
SCRIPTS_DIR = "/home/hotlapping/server/config/Scripts"
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")
BADGE = "<color=#20c997>[Hotlapping]</color>"


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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


def main():
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

    if cfg == read_json(APPLIED):
        return  # nothing to do

    if not server_running():
        return  # apply on a later run once the server is up
    if os.path.exists(AUTORUN):
        return  # server busy consuming another autorun; retry next minute

    try:
        commands = [
            "/refreshfiles",
            "/vehicles /clear",
            f"/vehicle /add {quoted(vehicle)}",
            "/levels /clear",
        ]
        commands += [f"/level /add {quoted(track)}"] * events
        commands += [
            "/respawning.startBehindWhenHotlapping = true",
            f"/respawning.hotlapBehindDistance = {distance}",
            f"/broadcast {BADGE} New setup: {track} — {vehicle}",
            f"/broadcast {BADGE} <color=#aaaaaa>Start-behind distance {distance}, "
            f"{events} events per session (set via tsura.org).</color>",
            "/continue",
        ]
    except ValueError as exc:
        log(f"cannot build commands: {exc}")
        return

    with open(AUTORUN, "w") as f:
        f.write("\n".join(commands) + "\n")

    with open(APPLIED, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(APPLIED, 0o664)
    except OSError:
        pass

    log(f"applied: track={track!r} vehicle={vehicle!r} "
        f"distance={distance} events={events}")


if __name__ == "__main__":
    main()
