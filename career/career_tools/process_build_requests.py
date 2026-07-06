#!/usr/bin/env python3
"""Process admin "build & assign car" requests (career.car_build_requests).

For each pending request: build that one driver's tuned .veh from the current
DB tuning, update assignments.json, force it in-game live if the server is up,
and mark the row done. Safe to run mid-session (single-car build, unlike the
mass run_prepare which the session lock blocks).

Run by the career user via process_build_requests.sh (cron, every minute).
"""
import json
import os
import subprocess
import sys
import time

import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import career_prepare_session as cps
import career_vehicles

VEHICLES_DIR = "/home/career/server/config/Vehicles"
SCRIPTS_DIR = "/home/career/server/config/Scripts"
ASSIGN = os.path.join(SCRIPTS_DIR, "assignments.json")
AUTORUN = os.path.join(SCRIPTS_DIR, "autorun.src")

DB_URL = os.environ.get("CAREER_DB_URL")


def _server_running() -> bool:
    return subprocess.run(["pgrep", "-u", "career", "-f", "TSUs.x86_64"],
                          capture_output=True).returncode == 0


def _wait_autorun_free(timeout=30) -> bool:
    for _ in range(timeout * 2):
        if not os.path.exists(AUTORUN):
            return True
        time.sleep(0.5)
    return not os.path.exists(AUTORUN)


def _update_assignments(steam_id, veh_name, filename, driver, focus):
    data = {"assignments": []}
    if os.path.exists(ASSIGN):
        with open(ASSIGN, encoding="utf-8") as f:
            data = json.load(f)
    rows = [a for a in data.get("assignments", []) if a.get("steam_id") != str(steam_id)]
    rows.append({"steam_id": str(steam_id), "vehicle": veh_name,
                 "filename": filename, "driver": driver, "focus": focus})
    data["assignments"] = rows
    tmp = ASSIGN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ASSIGN)


def build_one(conn, season_id, steam_id) -> str:
    cur = conn.cursor(row_factory=psycopg.rows.dict_row)
    cur.execute("SELECT name, base_vehicle_veh FROM career.seasons WHERE id=%s",
                (season_id,))
    season = cur.fetchone()
    if not season:
        raise RuntimeError("season not found")
    cur.execute("SELECT axis, final_value, driver_name FROM mart.v_career_driver_cars "
                "WHERE season_id=%s AND steam_id=%s", (season_id, steam_id))
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("driver not enrolled / no tuning")
    driver = rows[0]["driver_name"]
    tuned = {r["axis"]: float(r["final_value"]) for r in rows
             if r["axis"] in cps.AXIS_TO_TUNE}
    # focus text (same as run_prepare) from credits spent per axis
    cur.execute("SELECT du.axis, du.tier * ua.cost_per_tier AS spent "
                "FROM career.driver_upgrades du JOIN career.upgrade_axes ua "
                "ON ua.season_id=du.season_id AND ua.axis=du.axis "
                "WHERE du.season_id=%s AND du.steam_id=%s", (season_id, steam_id))
    spent = {r["axis"]: r["spent"] for r in cur.fetchall()}
    focus = cps._focus_text(spent)

    veh_name = cps._unique_name(driver, set(), steam_id)
    out = os.path.join(VEHICLES_DIR,
                       career_vehicles._sanitize_filename(veh_name) + ".veh")
    career_vehicles.build_driver_vehicle(
        season["base_vehicle_veh"], out, display_name=veh_name,
        steam_id64=int(steam_id), tuned=tuned,
        description=f"{season['name']} car for {driver}.")
    _update_assignments(steam_id, veh_name, os.path.basename(out), driver, focus)

    forced = False
    if _server_running() and _wait_autorun_free():
        cmds = ["/refreshfiles",
                f"/vehicles /add '{veh_name}'",
                f"/forcevehicle {steam_id} '{veh_name}'",
                f"/broadcast <color=#ffc107>[Career]</color> {driver} — your car "
                f"was (re)built and assigned. Have fun!"]
        with open(AUTORUN, "w", encoding="utf-8") as f:
            f.write("\n".join(cmds) + "\n")
        forced = True
    return f"built {veh_name}" + (" + forced live" if forced else " (offline; forces next event)")


def main():
    if not DB_URL:
        print("ERROR: CAREER_DB_URL not set", file=sys.stderr)
        sys.exit(1)
    with psycopg.connect(DB_URL) as conn:
        cur = conn.cursor(row_factory=psycopg.rows.dict_row)
        cur.execute("SELECT id, season_id, steam_id FROM career.car_build_requests "
                    "WHERE status='pending' ORDER BY requested_at LIMIT 20")
        pending = cur.fetchall()
        for req in pending:
            try:
                note = build_one(conn, req["season_id"], req["steam_id"])
                status = "done"
            except Exception as e:            # noqa: BLE001
                note, status = f"{type(e).__name__}: {e}", "error"
            conn.execute(
                "UPDATE career.car_build_requests "
                "SET status=%s, processed_at=now(), note=%s WHERE id=%s",
                (status, note[:500], req["id"]))
            conn.commit()
            print(f"req {req['id']} ({req['steam_id']}): {status} — {note}")


if __name__ == "__main__":
    main()
