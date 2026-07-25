#!/bin/bash

export PATH=/usr/games/:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/hotlapping/.local/share/Steam/server/linux64:/home/hotlapping/.local/share/Steam/steamcmd/linux64

# Change directory to where your game server executable is located
cd ~/server

# Tell the per-minute apply_web_config.py cron to hold off: without this it
# races us and writes its autorun.src into the very second we delete stale
# autorun files below, so its commands vanish unexecuted while its marker
# claims success. Released once the server is up again.
LOCK=~/.restarting
touch "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# Keep the tsura.org upload dirs writable for the website (group tsu +
# setgid). If those bits get lost, panel uploads die with "Permission
# denied" -- this makes every restart self-heal.
for d in config/Vehicles config/Levels; do
    [ -d "$d" ] || mkdir -p "$d"
    chgrp tsu "$d" 2>/dev/null
    chmod 2775 "$d" 2>/dev/null
done

# Stop the game server (only if it's running under the steam user)
pkill -u hotlapping TSUs.x86_64

# Wait for a few seconds to ensure the server has stopped properly
sleep 60

# Remove a stale autorun so the fresh server doesn't fire yesterday's commands
rm -f ~/server/config/Scripts/autorun.src

# Do NOT delete the applied marker. The level list, the vehicle and the
# hotlapping settings all survive the restart via game.json (TSU rewrites it at
# every session end and reloads it at boot; -setup plain does not clear them),
# so a forced re-apply would do nothing but overwrite whatever an admin set
# in-game -- exactly the "someone changed the combo without permission"
# complaint. Only the in-game admin list is really forgotten at boot, so
# invalidate just that part and let apply_web_config.py push it again.
python3 - <<'PY'
import json, os
p = "/srv/tsura/server_config/hotlapping.applied.json"
try:
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict):
        d["ingame_admins"] = None
        tmp = f"{p}.tmp.restart"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, 0o664)
        os.replace(tmp, p)
except Exception:
    pass
PY

# Start the game server
nohup ./TSUs.x86_64 -public -port 7759 -setup plain > error &

# Hold the lock until the server is really up, so the apply cron pushes into a
# server that has finished loading its content.
sleep 20



