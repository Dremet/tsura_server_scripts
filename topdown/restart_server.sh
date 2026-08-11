#!/bin/bash

export PATH=/usr/games/:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/topdown/.local/share/Steam/server/linux64:/home/topdown/.local/share/Steam/steamcmd/linux64

cd ~/server

# Keep the tsura.org upload dirs writable for the website (group tsu + setgid).
# TSU replaces these folders wholesale when a player shares content in-game,
# which drops the bits and breaks panel uploads until someone notices.
for d in config/Vehicles config/Levels config/AI; do
    [ -d "$d" ] || mkdir -p "$d"
    chgrp tsu "$d" 2>/dev/null
    chmod 2775 "$d" 2>/dev/null
done

pkill -u topdown TSUs.x86_64

# Wait for the server to stop properly
sleep 30

# Drop a stale autorun so the fresh server does not fire yesterday's commands
rm -f ~/server/config/Scripts/autorun.src

# -scriptPort is what the heat controller talks to. Without it the controller
# has nothing to connect to and no heats will ever start.
nohup ./TSUs.x86_64 -public -port 7761 -setup plain -scriptPort 7766 > error &
