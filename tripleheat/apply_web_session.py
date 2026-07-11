"""Apply the saved tsura.org config as a fresh session, on demand.

The admin panel's "Apply now" button writes a request file; this script
(cron, every minute, as the game user) consumes it:

1. If vehicles/levels were uploaded AFTER the server booted (or the server
   is down), it restarts the server first — startup is the only fully
   reliable file re-scan.
2. Then it runs the normal session-start flow (create_autorun.py
   start_session), exactly like the weekly session cron: /refreshfiles,
   web admin list, cars and random tracks from the saved config.
   sessioninit.src additionally runs /refreshfiles at every session init.
"""

import os
import subprocess
import time
from datetime import datetime

HOME = os.path.expanduser("~")
USER = os.path.basename(HOME)
KEY = {"tripleheat": "tripleheat", "heat": "casual_heat"}[USER]
REQUEST = f"/srv/tsura/server_config/{KEY}.apply_session"
SCRIPTS = f"{HOME}/server/config/Scripts"


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def server_pid():
    r = subprocess.run(["pgrep", "-u", USER, "-x", "TSUs.x86_64"],
                       capture_output=True, text=True)
    out = r.stdout.strip().split()
    return int(out[0]) if r.returncode == 0 and out else None


def newest_content_mtime():
    newest = 0.0
    for sub in ("Vehicles", "Levels"):
        try:
            for entry in os.scandir(f"{HOME}/server/config/{sub}"):
                if entry.is_file():
                    newest = max(newest, entry.stat().st_mtime)
        except OSError:
            pass
    return newest


def main():
    if not os.path.exists(REQUEST):
        return
    try:
        os.unlink(REQUEST)
    except OSError as exc:
        log(f"cannot consume request: {exc}")
        return
    log("apply-session request received")

    pid = server_pid()
    booted = os.stat(f"/proc/{pid}").st_mtime if pid else 0.0
    if pid is None or newest_content_mtime() > booted:
        log("restarting server first (new content files, or server down)")
        subprocess.run([f"{HOME}/restart_server.sh"])  # blocks ~70s
        for _ in range(60):
            if server_pid():
                break
            time.sleep(2)
        else:
            log("server did not come back — aborting")
            return
        time.sleep(10)  # grace period while the server loads its config

    autorun = os.path.join(SCRIPTS, "autorun.src")
    for _ in range(30):
        if not os.path.exists(autorun):
            break
        time.sleep(1)
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "create_autorun.py", "start_session"],
            cwd=SCRIPTS, capture_output=True, text=True, timeout=120)
        log(f"start_session rc={r.returncode}")
        if r.returncode != 0:
            log(r.stderr[-300:])
    except subprocess.TimeoutExpired:
        log("start_session timed out (autorun never freed?)")


if __name__ == "__main__":
    main()
