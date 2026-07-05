#!/bin/bash
# host_session.sh — spontaneously host a TSU Career session (same flow as the
# Monday cron: prepare cars -> announce -> start; wind down when done).
#
#   ./host_session.sh start [minutes]   generate tuned cars, announce in-game,
#                                       start ~1 min later; auto wind-down
#                                       after <minutes> (default 120)
#   ./host_session.sh stop              wind down now (/continue)
#   ./host_session.sh status            is a session active?
#
# Safe against the Monday automation: start refuses while a session is active
# (same session_active lock the cron chain uses).
set -euo pipefail

SCRIPTS=/home/career/server/config/Scripts
LOCK="$SCRIPTS/session_active"
TIMER_PID_FILE=/home/career/.host_session_timer.pid

kill_timer() {
  if [ -f "$TIMER_PID_FILE" ]; then
    kill "$(cat "$TIMER_PID_FILE")" 2>/dev/null || true
    rm -f "$TIMER_PID_FILE"
  fi
}

case "${1:-}" in
  start)
    if [ -f "$LOCK" ]; then
      echo "A career session is already active ($LOCK)." >&2
      echo "Wind it down first with: $0 stop" >&2
      exit 1
    fi
    DURATION_MIN="${2:-120}"
    kill_timer
    echo "[career] generating tuned cars for all enrolled drivers..."
    /home/career/run_prepare.sh
    echo "[career] announcing — session starts in ~1 minute..."
    cd "$SCRIPTS"
    /usr/bin/python3 create_autorun.py announce_1_minute
    sleep 60
    /usr/bin/python3 create_autorun.py start_session
    echo "[career] session started (2 tracks, quali + race each)."
    nohup bash -c "sleep $((DURATION_MIN * 60)); cd '$SCRIPTS' && /usr/bin/python3 create_autorun.py skip_to_new_session; rm -f '$TIMER_PID_FILE'" >/dev/null 2>&1 &
    echo $! > "$TIMER_PID_FILE"
    echo "[career] auto wind-down in $DURATION_MIN min — or earlier via: $0 stop"
    ;;
  stop)
    kill_timer
    cd "$SCRIPTS"
    /usr/bin/python3 create_autorun.py skip_to_new_session
    echo "[career] wind-down sent (/continue)."
    ;;
  status)
    if [ -f "$LOCK" ]; then
      echo "session ACTIVE since $(stat -c '%y' "$LOCK" | cut -d. -f1)"
      [ -f "$TIMER_PID_FILE" ] && echo "auto wind-down timer running (pid $(cat "$TIMER_PID_FILE"))"
    else
      echo "no active session"
    fi
    ;;
  *)
    echo "usage: $0 start [duration-minutes] | stop | status" >&2
    exit 2
    ;;
esac
