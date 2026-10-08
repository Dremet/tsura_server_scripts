#!/bin/sh
D=/home/fun/server/config/Scripts
sh "$D/archive_stats.sh" event >> "$D/archive_stats.log" 2>&1
