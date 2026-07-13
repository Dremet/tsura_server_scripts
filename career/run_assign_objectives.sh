#!/bin/bash
# Assign next Monday's race-day challenges so they are visible on
# tsura.org/career all week. Cron: Tuesdays 00:00, right after the race
# night's results have been scored by the pipeline.
set -e
cd "$(dirname "$0")/career_tools"
[ -f .env ] && { set -a; . ./.env; set +a; }
exec uv run --with 'psycopg[binary]' python assign_next_objectives.py "$@"
