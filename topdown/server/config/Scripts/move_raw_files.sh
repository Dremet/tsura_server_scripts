#!/bin/sh
# Hand finished race results to the ingest pipeline.
#
# Careful: the file this was cloned from (inherited when topdown was copied off
# the events server in May) still pointed at /home/data/events, which would have
# mixed topdown results into the event server's data.

EVENT_STATS_FILE="./eventstats.json"
EVENT_STATS_DETAILS_FILE="./eventstats.details.log"
SESSION_STATS_FILE="./sessionstats.json"
HEAT_STAMP_FILE="./topdown_heat.json"

if [ ! -f "$EVENT_STATS_FILE" ]; then
  echo "no eventstats.json -- nothing to move"
  exit 0
fi

# Qualifying runs in hotlapping mode and yields no usable race stats. The pole
# point is taken from the following race's start_position instead.
if grep -q '"hotlapping": true' "$EVENT_STATS_FILE" 2>/dev/null; then
  echo "qualifying (hotlapping) -- discarding stats"
  rm -f "$EVENT_STATS_FILE" "$SESSION_STATS_FILE" "$EVENT_STATS_DETAILS_FILE"
  exit 0
fi

CURRENT_TIMESTAMP=$(date "+%Y%m%d_%H%M%S")
DEST_DIR="/home/data/topdown/${CURRENT_TIMESTAMP}/raw"
mkdir -p "$DEST_DIR"

# The pipeline runs as user `data`; both users are in group `tsu`.
chgrp -R tsu "$DEST_DIR/.." 2>/dev/null
chmod -R 774 "$DEST_DIR/.." 2>/dev/null

TRACK_NAME=$(jq -r '.level.name // empty' "$EVENT_STATS_FILE" 2>/dev/null | tr -d ' ')
NEW_FILE_NAME="${CURRENT_TIMESTAMP}"
if [ -n "$TRACK_NAME" ]; then
  NEW_FILE_NAME="${NEW_FILE_NAME}_${TRACK_NAME}"
fi

mv "$EVENT_STATS_FILE" "$DEST_DIR/${NEW_FILE_NAME}_event.json"
[ -f "$SESSION_STATS_FILE" ] && mv "$SESSION_STATS_FILE" "$DEST_DIR/${NEW_FILE_NAME}_session.json"
[ -f "$EVENT_STATS_DETAILS_FILE" ] && mv "$EVENT_STATS_DETAILS_FILE" "$DEST_DIR/${NEW_FILE_NAME}_event_details.log"
# Copied, not moved: the stamp stays put so a later event can still read it.
[ -f "$HEAT_STAMP_FILE" ] && cp "$HEAT_STAMP_FILE" "$DEST_DIR/${NEW_FILE_NAME}_heat.json"

chmod 664 "$DEST_DIR"/* 2>/dev/null

echo "$DEST_DIR" > /home/data/new_topdown_files.trigger
echo "moved results to $DEST_DIR"
