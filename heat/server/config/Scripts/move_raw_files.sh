#!/bin/sh

# Pfad zu den Stats-Dateien (erzeugt vom Tripleheat-Server nach Rennende)
EVENT_STATS_FILE="./eventstats.json"
EVENT_STATS_DETAILS_FILE="./eventstats.details.log"
SESSION_STATS_FILE="./sessionstats.json"

# Timestamp für Dateinamen und Zielverzeichnis
CURRENT_TIMESTAMP=$(date "+%Y%m%d_%H%M%S")

# Zielverzeichnis auf dem carrot-Datenserver
DEST_DIR="/home/data/heats/${CURRENT_TIMESTAMP}/raw"

mkdir -p "$DEST_DIR"

# Dateizugriff für den data-User sicherstellen
chgrp -R tsu "$DEST_DIR/.."
chmod -R 774 "$DEST_DIR/.."

# Streckennamen aus JSON extrahieren (Leerzeichen entfernen)
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

mv "$EVENT_STATS_FILE"         "$DEST_DIR/$EVENT_FILE_NAME"
echo "Moved: $DEST_DIR/$EVENT_FILE_NAME"

mv "$EVENT_STATS_DETAILS_FILE" "$DEST_DIR/$EVENT_DETAILS_FILE_NAME"
echo "Moved: $DEST_DIR/$EVENT_DETAILS_FILE_NAME"

mv "$SESSION_STATS_FILE"       "$DEST_DIR/$SESSION_FILE_NAME"
echo "Moved: $DEST_DIR/$SESSION_FILE_NAME"

# Trigger für die Pipeline auf carrot
cat "$DEST_DIR" > /home/data/new_heat_files.trigger
