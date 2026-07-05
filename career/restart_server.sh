#!/bin/bash

export PATH=/usr/games/:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/career/.local/share/Steam/server/linux64:/home/career/.local/share/Steam/steamcmd/linux64

# Change directory to where the game server executable is located
cd ~/server

# Stop the game server (only if it's running under the career user)
pkill -u career TSUs.x86_64
rm -f /home/career/server/config/Scripts/session_active
# a stale autorun.src (e.g. after a crash) would fire old commands at boot
rm -f /home/career/server/config/Scripts/autorun.src

# Wait a bit to ensure the server has stopped properly
sleep 60

# Start the game server
nohup ./TSUs.x86_64 -public -port 7765 -name "TSURA Career" -setup plain > error &
