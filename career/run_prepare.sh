#!/bin/bash
# Generate every enrolled driver's tuned car for the active season and write
# them + assignments.json into the Career server. Run before the race night
# (e.g. a cron at ~20:45 on Mondays, before the 21:00 session start).
set -e
LOCK=/home/career/server/config/Scripts/session_active
if [ -f "$LOCK" ]; then
  echo "[career-prep] a session is active ($LOCK) — refusing to regenerate .veh mid-session." >&2
  exit 0
fi
cd "$(dirname "$0")/career_tools"
[ -f .env ] && { set -a; . ./.env; set +a; }
exec uv run --with 'psycopg[binary]' python career_prepare_session.py \
  --vehicles-dir /home/career/server/config/Vehicles \
  --scripts-dir  /home/career/server/config/Scripts \
  "$@"
