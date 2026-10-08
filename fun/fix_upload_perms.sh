#!/bin/bash
# Keep the tsura.org upload dirs writable for the website (group tsu + setgid).
#
# TSU replaces the whole Vehicles/Levels folder whenever a player shares
# content in-game ("Imported new Levels and LevelLists folders, old ones moved
# to .old") -- the new folder comes with default permissions, which breaks
# panel uploads with "[Errno 13] Permission denied". Run this every minute so
# the window stays at most a minute; restart_server.sh does the same at boot.
cd ~/server 2>/dev/null || exit 0
for d in config/Vehicles config/Levels; do
    [ -d "$d" ] || continue
    [ "$(stat -c '%a %G' "$d")" = "2775 tsu" ] && continue
    chgrp tsu "$d" 2>/dev/null
    chmod 2775 "$d" 2>/dev/null
done
