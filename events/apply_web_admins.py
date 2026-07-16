#!/usr/bin/env python3
"""Re-apply the tsura.org web admin list to the running events server.

TSU loads in-game admins from game.json's remoteAdmins at boot and does
NOT persist runtime /admins changes back to it. The web admin panel
(webadmin.server_admins -> /srv/tsura/server_config/events.json) pushes
changes to the RUNNING server only — so a restart would silently drop
them. Cron runs this shortly after the daily restart (05:20) as user
`events`: it writes an autorun.src with /admins commands built from the
web config. Safe while players are on: only /admins commands, the
running event is untouched.
"""
import json
import os
import sys
from datetime import datetime

CONFIG = "/srv/tsura/server_config/events.json"
SCRIPTS_DIR = os.path.expanduser("~/server/config/Scripts")
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")


def main():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            admins = json.load(fh).get("ingame_admins") or []
    except (OSError, ValueError) as exc:
        log(f"cannot read {CONFIG}: {exc}")
        return 1
    if not admins:
        log("no ingame_admins in web config — nothing to do")
        return 0
    if os.path.exists(AUTORUN):
        log("autorun.src busy — skipping (next run re-applies)")
        return 0
    commands = ["/admins /clear"]
    commands += [f"/admins /add {sid}" for sid, _label in admins]
    tmp = AUTORUN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(commands) + "\n")
    os.replace(tmp, AUTORUN)
    log(f"applied {len(admins)} admin(s) from web config")
    return 0


if __name__ == "__main__":
    sys.exit(main())
