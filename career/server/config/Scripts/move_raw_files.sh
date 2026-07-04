#!/bin/sh

# Stats files produced by the Career server after each race event
EVENT_STATS_FILE="./eventstats.json"
EVENT_STATS_DETAILS_FILE="./eventstats.details.log"
SESSION_STATS_FILE="./sessionstats.json"

CURRENT_TIMESTAMP=$(date "+%Y%m%d_%H%M%S")

# Destination on the carrot data server (picked up by the pipeline's career loop)
DEST_DIR="/home/data/career/${CURRENT_TIMESTAMP}/raw"

mkdir -p "$DEST_DIR"

# make files accessible to the data user
chgrp -R tsu "$DEST_DIR/.."
chmod -R 774 "$DEST_DIR/.."

TRACK_NAME=$(jq -r '.level.name // empty' "$EVENT_STATS_FILE" 2>/dev/null | tr -d ' ')

NEW_FILE_NAME="${CURRENT_TIMESTAMP}"
if [ -n "$TRACK_NAME" ]; then
  NEW_FILE_NAME="${NEW_FILE_NAME}_${TRACK_NAME}"
fi

EVENT_FILE_NAME="${NEW_FILE_NAME}_event.json"
EVENT_DETAILS_FILE_NAME="${NEW_FILE_NAME}_event_details.log"
SESSION_FILE_NAME="${NEW_FILE_NAME}_session.json"

if [ ! -s "$EVENT_STATS_FILE" ]; then
  echo "Warning: '$EVENT_STATS_FILE' is empty or does not exist."
fi
if [ ! -s "$EVENT_STATS_DETAILS_FILE" ]; then
  echo "Warning: '$EVENT_STATS_DETAILS_FILE' is empty or does not exist."
fi
if [ ! -s "$SESSION_STATS_FILE" ]; then
  echo "Warning: '$SESSION_STATS_FILE' is empty or does not exist."
fi

[ -s "$EVENT_STATS_FILE" ]         && mv "$EVENT_STATS_FILE"         "$DEST_DIR/$EVENT_FILE_NAME"         && echo "Moved: $DEST_DIR/$EVENT_FILE_NAME"
[ -s "$EVENT_STATS_DETAILS_FILE" ] && mv "$EVENT_STATS_DETAILS_FILE" "$DEST_DIR/$EVENT_DETAILS_FILE_NAME" && echo "Moved: $DEST_DIR/$EVENT_DETAILS_FILE_NAME"
[ -s "$SESSION_STATS_FILE" ]       && mv "$SESSION_STATS_FILE"       "$DEST_DIR/$SESSION_FILE_NAME"       && echo "Moved: $DEST_DIR/$SESSION_FILE_NAME"

# Signal for the pipeline
echo "$DEST_DIR" > /home/data/new_career_files.trigger
