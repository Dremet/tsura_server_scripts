#!/usr/bin/env python3
"""career_prepare_session.py — build every enrolled driver's tuned car for the
active season and write the per-driver vehicle files + the forceVehicle
assignment map, ready for the Career race night.

Run before the session starts (well before 21:00). Steps:
  1. read the active season + each enrolled driver's resolved tuning values
     (mart.v_career_driver_cars) from the DB;
  2. generate one .veh per driver from the season's base car into the server's
     config/Vehicles/ directory (career_vehicles.build_driver_vehicle);
  3. write assignments.json (steam_id -> in-game vehicle name) into the Scripts
     dir, which run_event_init.py turns into /vehicles /add + /forcevehicle lines.

Env / args:
  CAREER_DB_URL        DB DSN (read-only is enough; needs SELECT on career.* +
                       mart.v_career_driver_cars). Falls back to TSU_PROD_POSTGRES_URL.
  --vehicles-dir       output dir for .veh files (default: server config/Vehicles)
  --scripts-dir        where to write assignments.json (default: config/Scripts)
  --base-veh           override the season's base .veh path (testing)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import psycopg

import career_vehicles

AXIS_TO_TUNE = {
    "top_speed": "top_speed",
    "acceleration": "acceleration",
    "braking": "braking",
    "downforce": "downforce",
    "grip": "grip",
    "sliding_gradual_range": "sliding_gradual_range",
    "spring_max_length": "spring_max_length",
    "locking_start_time": "locking_start_time",
    "oversteering_braking": "oversteering_braking",
}


FOCUS_LABELS = {
    "top_speed": "Top Speed", "acceleration": "Acceleration",
    "braking": "Braking", "grip": "Grip", "downforce": "Downforce",
    "sliding_gradual_range": "Sliding Control", "spring_max_length": "Suspension",
    "locking_start_time": "Brake Locking", "oversteering_braking": "Stability",
}


def _focus_text(spent_by_axis: dict) -> str | None:
    """One human phrase describing where a driver put their credits."""
    total = sum(spent_by_axis.values())
    if total <= 0:
        return None
    ranked = sorted(spent_by_axis.items(), key=lambda kv: -kv[1])
    top_axis, top_spent = ranked[0]
    nonzero = [a for a, s in ranked if s > 0]
    if len(nonzero) >= 4 and top_spent / total < 0.4:
        return f"balanced build ({total} cr invested)"
    if len(nonzero) == 1:
        return f"all-in on {FOCUS_LABELS[top_axis]} ({total} cr invested)"
    if ranked[1][1] >= top_spent / 2:
        return (f"focused on {FOCUS_LABELS[top_axis]} & "
                f"{FOCUS_LABELS[ranked[1][0]]} ({total} cr invested)")
    return f"focused on {FOCUS_LABELS[top_axis]} ({total} cr invested)"


OBJECTIVE_CREDITS = 100


def _objective_spec(key, rival, rival_name):
    """(threshold n, human description, params) for one objective type."""
    if key == "rival_race":
        return 2, f"Beat {rival_name} in 2 of tonight's races", {"rival": rival}
    if key == "rival_quali":
        return 2, f"Out-qualify {rival_name} twice tonight", {"rival": rival}
    if key == "overtaker":
        return 2, "Finish ahead of your grid position in 2 races tonight", {}
    if key == "underdog":
        return 2, "Beat a more upgraded car in 2 races tonight", {}
    if key == "pole":
        return 1, "Take pole position in at least one qualifying tonight", {}
    if key == "fastest_lap":
        return 1, "Set the fastest race lap at least once tonight", {}
    if key == "podium2":
        return 2, "Finish on the podium in 2 of tonight's races", {}
    raise ValueError(key)


def assign_objectives(conn, season_id, race_date):
    """One random, standings-appropriate challenge per enrolled driver for
    this race day. Drivers that already have one keep it, so re-runs of the
    prep are no-ops. Pays OBJECTIVE_CREDITS when achieved; the scoring runs
    in the pipeline (tsu_pipeline.career.evaluate_objectives).

    Pools depend on the championship position so every challenge is
    realistically achievable: the leader hunts pole/fastest lap (nobody is
    ahead to beat), the top 3 get the full menu, everyone else duels the
    driver directly ahead ("rival"), overtakes or plays underdog. Unranked
    drivers chase the last ranked driver.

    Requires migration 014 (career.objectives + INSERT grant for this role);
    the caller treats failures as non-fatal so car generation never breaks.
    """
    import random

    cur = conn.cursor()
    cur.execute("SELECT CASE WHEN to_regclass('career.objectives') IS NOT NULL "
                "THEN has_table_privilege('career.objectives', 'INSERT') "
                "ELSE false END AS ok")
    if not cur.fetchone()["ok"]:
        print("[career-prep] career.objectives missing or not writable - "
              "skipping challenges (apply pipeline migration 014)",
              file=sys.stderr)
        return {}
    cur.execute("SELECT steam_id, description FROM career.objectives "
                "WHERE season_id = %s AND race_date = %s",
                (season_id, race_date))
    assigned = {r["steam_id"]: r["description"] for r in cur.fetchall()}
    cur.execute("SELECT steam_id FROM career.enrollments WHERE season_id = %s",
                (season_id,))
    enrolled = [r["steam_id"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT steam_id, driver_name "
                "FROM mart.v_career_driver_cars WHERE season_id = %s",
                (season_id,))
    names = {r["steam_id"]: r["driver_name"] for r in cur.fetchall()}
    cur.execute("SELECT steam_id FROM mart.v_career_standings "
                "WHERE season_id = %s ORDER BY points_total DESC, wins DESC",
                (season_id,))
    ranked = [r["steam_id"] for r in cur.fetchall()]
    cur.execute("SELECT du.steam_id, SUM(du.tier * ua.cost_per_tier) AS total "
                "FROM career.driver_upgrades du "
                "JOIN career.upgrade_axes ua "
                "  ON ua.season_id = du.season_id AND ua.axis = du.axis "
                "WHERE du.season_id = %s GROUP BY du.steam_id", (season_id,))
    spent = {r["steam_id"]: int(r["total"] or 0) for r in cur.fetchall()}

    for sid in enrolled:
        if sid in assigned:
            continue
        rank = ranked.index(sid) + 1 if sid in ranked else len(ranked) + 1
        rival = ranked[rank - 2] if (ranked and rank >= 2) else None
        richer = sorted(x for x in enrolled
                        if x != sid and spent.get(x, 0) > spent.get(sid, 0))
        if not ranked:
            pool = ["overtaker"] + (["underdog"] if richer else [])
        elif rank == 1:
            pool = ["pole", "fastest_lap"]
        elif rank <= 3:
            pool = (["rival_race", "rival_quali", "overtaker", "podium2",
                     "pole", "fastest_lap"] + (["underdog"] if richer else []))
        else:
            pool = (["rival_race", "rival_quali", "overtaker"]
                    + (["underdog"] if richer else []))
        if rival is None:
            pool = [k for k in pool if not k.startswith("rival")] or ["overtaker"]
        key = random.choice(pool)
        n, desc, params = _objective_spec(key, rival,
                                          names.get(rival, str(rival)))
        params["n"] = n
        if key == "underdog":
            params["richer"] = richer
        cur.execute(
            "INSERT INTO career.objectives (season_id, steam_id, race_date, "
            " objective, params, description, credits, progress) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (season_id, steam_id, race_date) DO NOTHING",
            (season_id, sid, race_date, key, json.dumps(params), desc,
             OBJECTIVE_CREDITS, f"0/{n}"))
        assigned[sid] = desc
    conn.commit()
    return assigned


def _unique_name(base: str, used: set, steam_id: int) -> str:
    # apostrophes would break the quoted /vehicles-/forcevehicle commands
    base = base.replace("'", "")
    name = f"Career {base}"[:20].rstrip(" (-_.")
    if name in used:
        name = f"{name[:14]} #{str(steam_id)[-4:]}"
    used.add(name)
    return name


def prepare(db_url: str, vehicles_dir: str, scripts_dir: str,
            base_veh_override: str | None = None,
            objectives_date: datetime.date | None = None) -> dict:
    os.makedirs(vehicles_dir, exist_ok=True)
    os.makedirs(scripts_dir, exist_ok=True)

    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, base_vehicle_name, base_vehicle_veh "
                    "FROM career.seasons WHERE status='active' LIMIT 1")
        season = cur.fetchone()
        if not season:
            raise SystemExit("no active season")
        base_veh = base_veh_override or season["base_vehicle_veh"]
        if not os.path.isfile(base_veh):
            raise SystemExit(f"base vehicle not found: {base_veh}")

        cur.execute("SELECT steam_id, driver_name, axis, final_value "
                    "FROM mart.v_career_driver_cars WHERE season_id=%s "
                    "ORDER BY driver_name", (season["id"],))
        rows = cur.fetchall()

        cur.execute("SELECT du.steam_id, du.axis, du.tier * ua.cost_per_tier AS spent "
                    "FROM career.driver_upgrades du "
                    "JOIN career.upgrade_axes ua "
                    "ON ua.season_id = du.season_id AND ua.axis = du.axis "
                    "WHERE du.season_id=%s", (season["id"],))
        spent_rows = cur.fetchall()

        # race-day challenges: assign before the session, never fatal
        race_date = objectives_date or datetime.date.today()
        try:
            objectives = assign_objectives(conn, season["id"], race_date)
        except Exception as exc:
            print(f"[career-prep] WARNING: challenge assignment failed: {exc}",
                  file=sys.stderr)
            objectives = {}

    drivers: dict = {}
    for r in rows:
        d = drivers.setdefault(r["steam_id"],
                               {"name": r["driver_name"], "tuned": {}})
        if r["axis"] in AXIS_TO_TUNE:
            d["tuned"][AXIS_TO_TUNE[r["axis"]]] = float(r["final_value"])

    spent: dict = {}
    for r in spent_rows:
        spent.setdefault(r["steam_id"], {})[r["axis"]] = r["spent"]

    used_names: set = set()
    assignments = []
    for steam_id, d in drivers.items():
        veh_name = _unique_name(d["name"], used_names, steam_id)
        out_path = os.path.join(vehicles_dir,
                                career_vehicles._sanitize_filename(veh_name) + ".veh")
        career_vehicles.build_driver_vehicle(
            base_veh, out_path,
            display_name=veh_name, steam_id64=steam_id, tuned=d["tuned"],
            description=f"{season['name']} car for {d['name']}.")
        assignments.append({"steam_id": str(steam_id), "vehicle": veh_name,
                            "filename": os.path.basename(out_path),
                            "driver": d["name"],
                            "focus": _focus_text(spent.get(steam_id, {})),
                            "objective": objectives.get(steam_id)})

    out = {"season": season["name"], "season_id": season["id"],
           "base_vehicle_name": season["base_vehicle_name"],
           "assignments": assignments}
    with open(os.path.join(scripts_dir, "assignments.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicles-dir",
                    default="/home/career/server/config/Vehicles")
    ap.add_argument("--scripts-dir",
                    default="/home/career/server/config/Scripts")
    ap.add_argument("--base-veh", default=None)
    ap.add_argument("--objectives-date", default=None,
                    help="ISO date override for challenge assignment (testing)")
    args = ap.parse_args()
    db_url = os.environ.get("CAREER_DB_URL") or os.environ.get("TSU_PROD_POSTGRES_URL")
    if not db_url:
        print("ERROR: CAREER_DB_URL / TSU_PROD_POSTGRES_URL not set", file=sys.stderr)
        sys.exit(1)
    obj_date = (datetime.date.fromisoformat(args.objectives_date)
                if args.objectives_date else None)
    out = prepare(db_url, args.vehicles_dir, args.scripts_dir, args.base_veh,
                  objectives_date=obj_date)
    print(f"[career-prep] season '{out['season']}': "
          f"{len(out['assignments'])} cars generated into {args.vehicles_dir}")
    n_obj = sum(1 for a_ in out["assignments"] if a_.get("objective"))
    print(f"[career-prep] challenges assigned: {n_obj}")
    for a in out["assignments"]:
        print(f"  {a['steam_id']} -> {a['vehicle']} ({a['filename']})")


if __name__ == "__main__":
    main()
