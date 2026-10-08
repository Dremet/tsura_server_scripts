#!/bin/sh
# Collect the game's result files for later analysis. NOTHING reads them yet:
# the format of the fun modes (Sumo, Capture the Flag, ...) is unknown, so the
# files are only filed away -- the pipeline does not look into /home/data/fun.
#
# usage: archive_stats.sh event   -> move event stats, COPY session stats
#        archive_stats.sh session -> move everything that is left
#
# The game writes the files into its working directory (~/server). Layout of
# the archive (same naming scheme as the other servers, so a loader can be
# added later without reorganising):
#   /home/data/fun/archive/<YYYYmmdd_HHMMSS>/raw/<ts>[_<level>]_{event.json,
#                                                  event_details.log,session.json}
MODE="${1:-event}"
SRC=/home/fun/server
BASE=/home/data/fun/archive

cd "$SRC" || exit 0

EVENT=eventstats.json
DETAILS=eventstats.details.log
SESSION=sessionstats.json

have=0
for f in "$EVENT" "$DETAILS" "$SESSION"; do
  [ -s "$f" ] && have=1
done
[ "$have" = 0 ] && exit 0

TS=$(date "+%Y%m%d_%H%M%S")
DEST="$BASE/$TS/raw"
mkdir -p "$DEST" || { echo "cannot create $DEST"; exit 1; }

# level name for the file name -- best effort, the fun modes may not have one
NAME="$TS"
LEVEL=$(jq -r '.level.name // empty' "$EVENT" 2>/dev/null | tr -cd 'A-Za-z0-9._-')
[ -n "$LEVEL" ] && NAME="${TS}_${LEVEL}"

[ -s "$EVENT" ]   && mv "$EVENT"   "$DEST/${NAME}_event.json"
[ -s "$DETAILS" ] && mv "$DETAILS" "$DEST/${NAME}_event_details.log"
if [ -s "$SESSION" ]; then
  if [ "$MODE" = "session" ]; then
    mv "$SESSION" "$DEST/${NAME}_session.json"
  else
    cp "$SESSION" "$DEST/${NAME}_session.json"
  fi
fi

# nothing archived (e.g. only empty files)? don't leave an empty folder
rmdir "$DEST" 2>/dev/null && rmdir "$BASE/$TS" 2>/dev/null

chgrp -R tsu "$BASE/$TS" 2>/dev/null
chmod -R g+rwX "$BASE/$TS" 2>/dev/null
echo "$(date '+%F %T') archived $MODE stats -> $DEST"
