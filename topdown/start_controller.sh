#!/bin/bash
# Watchdog: started every minute from cron, does nothing if the controller runs.
# The game servers have no systemd units, so this is how the house keeps a
# long-running process alive.

pgrep -u topdown -f "python3 .*topdown_controller.py" > /dev/null && exit 0

cd /home/topdown
setsid nohup /usr/bin/python3 /home/topdown/topdown_controller.py \
    < /dev/null >> /home/topdown/controller.out 2>&1 &
echo "$(date '+%Y-%m-%d %H:%M:%S') controller (re)started" >> /home/topdown/controller.out
