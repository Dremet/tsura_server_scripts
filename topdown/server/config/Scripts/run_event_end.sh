#!/bin/sh

# Stamp the heat and advance the quali/race cursor.
python3 run_event_end.py

# Hand the results to the pipeline (discards qualifying stats itself).
sh move_raw_files.sh >> move_raw_files.log 2>&1
