#!/bin/bash
# TSU replaces Vehicles/Levels wholesale on in-game content import, which resets
# the group and setgid bits and breaks tsura.org uploads with EACCES. Re-apply
# them every minute so a mid-day import cannot block uploads until tomorrow.

for d in /home/topdown/server/config/Vehicles \
         /home/topdown/server/config/Levels \
         /home/topdown/server/config/AI; do
    [ -d "$d" ] || continue
    chgrp tsu "$d" 2>/dev/null
    chmod 2775 "$d" 2>/dev/null
done
