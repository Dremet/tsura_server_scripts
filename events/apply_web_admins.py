#!/usr/bin/env python3
"""Keep the events server's in-game admin list equal to the web admin list.

TSU loads in-game admins from game.json's remoteAdmins at boot and does NOT
persist runtime /admins changes back to it. The web admin panel
(webadmin.server_admins -> /srv/tsura/server_config/events.json) pushes
changes to the RUNNING server only.

Why it asks before it pushes
----------------------------
On 2026-09-05 the running server had silently dropped one admin (Juanen):
every config layer still listed all seven, the log recorded all seven being
added and never recorded a removal, yet `/admins` answered with six. So
game.json is NOT a picture of the runtime state -- only asking the server is.

This therefore queries `/admins` first and pushes only when the answer differs
from the web config, which makes it cheap enough to run every few minutes
instead of once a day. Before, a list that got lost at 06:00 stayed lost until
the next morning.

Both the query and the push go through Scripts/autorun.src, the only channel
into a running server; the answer comes back in the server's own log. Only
/admins commands are sent, so a running event is never disturbed.

Exit code is always 0 unless the config itself is unreadable -- a server that
is down or busy is a reason to try again later, not to alarm cron.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

CONFIG = "/srv/tsura/server_config/events.json"
SCRIPTS_DIR = os.path.expanduser("~/server/config/Scripts")
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")
LOGS_DIR = os.path.expanduser("~/server/config/Logs")

# How long to wait for the server to swallow an autorun file, and for its
# answer to reach the log afterwards.
CONSUME_TIMEOUT = 30
ANSWER_TIMEOUT = 10
POLL = 0.5

ADMIN_LINE = re.compile(r"^\s*-\s*(\d{17})\s*$")


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def wanted_admins():
    """Steam IDs from the web config, in config order."""
    with open(CONFIG, encoding="utf-8") as fh:
        entries = json.load(fh).get("ingame_admins") or []
    return [str(sid) for sid, _label in entries if str(sid).isdigit()]


def current_log():
    """The server's newest log file (one per boot), or None."""
    try:
        names = [n for n in os.listdir(LOGS_DIR)
                 if n.startswith("log.") and n.endswith(".txt")]
    except OSError:
        return None
    if not names:
        return None
    return os.path.join(LOGS_DIR, max(names))


def send(commands):
    """Run commands on the server; return the log text they produced.

    Returns None when the server never took the file -- it is down, still
    booting, or busy with somebody else's autorun.
    """
    if os.path.exists(AUTORUN):
        return None                      # another push is still in flight
    path = current_log()
    if not path:
        return None
    try:
        offset = os.path.getsize(path)
    except OSError:
        return None

    tmp = AUTORUN + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(commands) + "\n")
        os.replace(tmp, AUTORUN)
    except OSError as exc:
        log(f"cannot write autorun.src: {exc}")
        return None

    deadline = time.time() + CONSUME_TIMEOUT
    while time.time() < deadline:
        if not os.path.exists(AUTORUN):
            break
        time.sleep(POLL)
    else:
        # Never taken: clean up so we do not block the next run or the panel.
        try:
            os.remove(AUTORUN)
        except OSError:
            pass
        return None

    # The server writes its answer a moment after consuming the file.
    answer, quiet_until = "", time.time() + ANSWER_TIMEOUT
    while time.time() < quiet_until:
        time.sleep(POLL)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                answer = fh.read()
        except OSError:
            return None
        if answer.strip():
            break
    return answer


def parse_admins(answer):
    """Steam IDs from the last 'Remote admins:' block, or None if absent."""
    if answer is None:
        return None
    blocks = answer.split("Remote admins:")
    if len(blocks) < 2:
        # The server says this instead of printing an empty list.
        return [] if "No remote admins." in answer else None
    ids = []
    for line in blocks[-1].splitlines():
        m = ADMIN_LINE.match(line)
        if not m:
            if line.strip():
                break                    # block is over
            continue
        ids.append(m.group(1))
    return ids


def main():
    try:
        wanted = wanted_admins()
    except (OSError, ValueError) as exc:
        log(f"cannot read {CONFIG}: {exc}")
        return 1
    if not wanted:
        log("no ingame_admins in web config — nothing to do")
        return 0

    have = parse_admins(send(["/admins"]))
    if have is None:
        log("server did not answer /admins — retrying next run")
        return 0
    if set(have) == set(wanted):
        return 0                         # in sync: stay quiet in the log

    missing = [s for s in wanted if s not in have]
    extra = [s for s in have if s not in wanted]
    log(f"out of sync — server has {len(have)}, web config has {len(wanted)}"
        + (f"; missing {missing}" if missing else "")
        + (f"; unexpected {extra}" if extra else ""))

    commands = ["/admins /clear"] + [f"/admins /add {s}" for s in wanted]
    now = parse_admins(send(commands + ["/admins"]))
    if now is None:
        log("pushed, but the server did not confirm — checking again next run")
    elif set(now) == set(wanted):
        log(f"applied {len(wanted)} admin(s), server confirms")
    else:
        log(f"WARNING: server still disagrees after the push: {sorted(now)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
