#!/bin/bash

# steamcmd lives in /usr/games — not in PATH under sudo/cron
export PATH=/usr/games:$PATH

cd ~

steamcmd +force_install_dir ~/server +login anonymous +app_update 1815810 validate +quit

./restart_server.sh
