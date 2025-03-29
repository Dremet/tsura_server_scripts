#!/bin/bash

export PATH=/usr/games/:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/heat/.local/share/Steam/server/linux64:/home/heat/.local/share/Steam/steamcmd/linux64

# Change directory to where your game server executable is located
cd ~/server

# Stop the game server (only if it's running under the steam user)
pkill -u heat TSUs.x86_64

# Wait for a few seconds to ensure the server has stopped properly
sleep 5

# Start the game server
nohup ./TSUs.x86_64 -public -port 7757 -setup plain > error &
