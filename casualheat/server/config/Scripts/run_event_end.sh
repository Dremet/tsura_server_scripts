#!/bin/sh

# In-game broadcast
python3 run_event_end.py

# Hotlapping-Rennen produzieren keine verwertbaren Stats → löschen und fertig
if grep -q '"hotlapping": true' ./eventstats.json 2>/dev/null; then
  echo "Hotlapping mode detected, removing stats files."
  rm -f ./eventstats.json ./sessionstats.json
  exit 0
fi

# Stats-Dateien in Pipeline-Struktur verschieben + Trigger setzen
sh move_raw_files.sh >> move_raw_files.log 2>&1
