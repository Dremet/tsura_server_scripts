#!/bin/bash

export PATH=/usr/games/:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/hotlapping/.local/share/Steam/server/linux64:/home/hotlapping/.local/share/Steam/steamcmd/linux64

# Change directory to where your game server executable is located
cd ~/server

# Stop the game server (only if it's running under the steam user)
pkill -u hotlapping TSUs.x86_64

# Wait for a few seconds to ensure the server has stopped properly
sleep 60

# Remove stale autorun + web-config applied marker so the tsura.org
# config is re-applied by apply_web_config.py once the server is back up
rm -f ~/server/config/Scripts/autorun.src
rm -f /srv/tsura/server_config/hotlapping.applied.json

# Start the game server
nohup ./TSUs.x86_64 -public -port 7759 -setup plain > error &



