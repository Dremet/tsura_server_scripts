#!/bin/bash
# Process admin "build & assign car" requests. Cron: every minute.
# Single-car builds are safe mid-session (unlike run_prepare), so no lock check.
set -e
cd "$(dirname "$0")/career_tools"
[ -f .env ] && { set -a; . ./.env; set +a; }
exec uv run --with 'psycopg[binary]' python process_build_requests.py
