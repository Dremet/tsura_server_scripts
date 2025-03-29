#!/bin/sh

# Pfad zur eventstats.json Datei
EVENT_STATS_FILE="./eventstats.json"
EVENT_STATS_DETAILS_FILE="./eventstats.details.log"
SESSION_STATS_FILE="./sessionstats.json"

# Erhalte den aktuellen Timestamp im gewünschten Format
CURRENT_TIMESTAMP=$(date "+%Y%m%d_%H%M%S")

# Verzeichnis, in das die Datei verschoben werden soll
DEST_DIR="/home/data/events/${CURRENT_TIMESTAMP}/raw"

# Stelle sicher, dass das Zielverzeichnis existiert
mkdir -p "$DEST_DIR"

# Versuche, den Streckennamen aus der JSON-Datei zu extrahieren
TRACK_NAME=$(jq -r '.level.name // empty' "$EVENT_STATS_FILE" 2>/dev/null | tr -d ' ')


# Basis für den neuen Dateinamen: Timestamp
NEW_FILE_NAME="${CURRENT_TIMESTAMP}"

# Füge den Streckennamen hinzu, falls vorhanden
if [ -n "$TRACK_NAME" ]; then
  NEW_FILE_NAME="${NEW_FILE_NAME}_${TRACK_NAME}"
fi

# Erweitere den Dateinamen um die Dateiendung
EVENT_FILE_NAME="${NEW_FILE_NAME}_event.json"
EVENT_DETAILS_FILE_NAME="${NEW_FILE_NAME}_event_details.log"
SESSION_FILE_NAME="${NEW_FILE_NAME}_session.json"

# Überprüfe, ob die Quelldatei existiert und nicht leer ist
if [ ! -s "$EVENT_STATS_FILE" ]; then
  echo "Warnung: Die Datei '$EVENT_STATS_FILE' ist leer oder existiert nicht. Es wird ein leeres Dokument verschoben."
fi

if [ ! -s "$EVENT_STATS_DETAILS_FILE" ]; then
  echo "Warning: The file '$EVENT_STATS_DETAILS_FILE' is empty or does not exist. An empty document will be moved."
fi

if [ ! -s "$SESSION_STATS_FILE" ]; then
  echo "Warnung: Die Datei '$SESSION_STATS_FILE' ist leer oder existiert nicht. Es wird ein leeres Dokument verschoben."
fi

# Verschiebe die eventstats.json Datei in das Zielverzeichnis mit dem neuen Dateinamen
mv "$EVENT_STATS_FILE" "$DEST_DIR/$EVENT_FILE_NAME"
echo "Event Stats Datei erfolgreich verschoben nach: $DEST_DIR/$EVENT_FILE_NAME"

mv "$EVENT_STATS_DETAILS_FILE" "$DEST_DIR/$EVENT_DETAILS_FILE_NAME"
echo "Event stats details log file successfully moved to: $DEST_DIR/$EVENT_DETAILS_FILE_NAME"

mv "$SESSION_STATS_FILE" "$DEST_DIR/$SESSION_FILE_NAME"
echo "Session Stats Datei erfolgreich verschoben nach: $DEST_DIR/$SESSION_FILE_NAME"

# trigger for data pipeline
cat "$DEST_DIR" > /home/data/new_event_files.trigger