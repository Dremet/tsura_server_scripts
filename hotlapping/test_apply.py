"""Offline tests for the hotlapping applier. Run: python3 test_apply.py

Uses the real server logs copied to fixtures/ plus synthetic cases; touches
nothing outside a temp dir.
"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_web_config as A  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


def sandbox():
    """Point the module at a throwaway copy of the fixtures."""
    tmp = tempfile.mkdtemp(prefix="hltest.")
    shutil.copytree(os.path.join(FIX, "Logs"), os.path.join(tmp, "Logs"))
    shutil.copytree(os.path.join(FIX, "Levels"), os.path.join(tmp, "Levels"))
    shutil.copytree(os.path.join(FIX, "Scripts"), os.path.join(tmp, "Scripts"))
    A.LOGS_DIR = os.path.join(tmp, "Logs")
    A.LEVELS_DIR = os.path.join(tmp, "Levels")
    A.SCRIPTS_DIR = os.path.join(tmp, "Scripts")
    A.VEHICLES_JSON = os.path.join(tmp, "Scripts", "vehicles.json")
    A.AUTORUN = os.path.join(tmp, "Scripts", "autorun.src")
    A.CONFIG = os.path.join(tmp, "hotlapping.json")
    A.APPLIED = os.path.join(tmp, "hotlapping.applied.json")
    A.LIVE = os.path.join(tmp, "hotlapping.live.json")
    A.FORCED = os.path.join(tmp, "hotlapping.forced.json")
    A.RESTART_LOCK = os.path.join(tmp, ".restarting")
    A.EVENT_ROOT = os.path.join(tmp, "noevents")
    return tmp


def write_log(tmp, name, text):
    with open(os.path.join(tmp, "Logs", name), "w", encoding="utf-8") as f:
        f.write(text)


CFG = {
    "track": "Cadwell Park (Woodlands) R v2.0",
    "vehicle": "Mazda MX-5 Cup '16",
    "hotlap_behind_distance": 800,
    "events_per_session": 4,
    "ingame_admins": [["76561197989276622", "owner"]],
}

print("\n1) Sensor gegen die echten Server-Logs")
tmp = sandbox()
combo = A.read_live_combo()
check("live combo = zuletzt geloggte Combo (25.7.)",
      (combo or {}).get("track"), "Cadwell Park (Woodlands) R v2.0")
check("Auto aus vehicles.json", (combo or {}).get("vehicle"), "Mazda MX-5 Cup '16")
check("observed_at = 25.7. nachmittags/abends",
      time.strftime("%Y-%m-%d", time.localtime(combo["observed_at"])), "2026-07-25")

# nur die Logs bis zum 24. -> Bangowitch (der 24er Log enthaelt selbst keine
# Setup-Zeile, der Sensor muss also in den 23er Log zurueckblaettern)
os.remove(os.path.join(tmp, "Logs", "log.20260725.050101.txt"))
combo = A.read_live_combo()
check("blaettert in aelteren Log zurueck, wenn der aktuelle Boot nichts setzte",
      (combo or {}).get("track"), "Cadwell Park (Woodlands)")

print("\n2) Sonderfaelle des Parsers")
tmp = sandbox()
for f in os.listdir(A.LOGS_DIR):
    os.remove(os.path.join(A.LOGS_DIR, f))
write_log(tmp, "log.20260726.050101.txt",
          "2026-07-26 05:01:01: Log started.\n"
          "2026-07-26 05:01:03: Session started.\n"
          "No levels\n")
check("'No levels' -> empty", A.read_live_combo(), {"empty": True,
      "observed_at": A._epoch("2026-07-26 05:01:03")})

write_log(tmp, "log.20260726.050101.txt",
          "2026-07-26 05:01:03: Session started.\n"
          "No levels\n"
          "Hotlapping 5 laps or 5 min with Mazda MX-5 Cup '16\n"
          "2 levels: Inturbolagos, Inturbolagos\n"
          "4 levels: Inturbolagos, Inturbolagos, Inturbolagos, Inturbolagos\n")
check("letzte Setup-Zeile gewinnt", (A.read_live_combo() or {}).get("track"), "Inturbolagos")

write_log(tmp, "log.20260726.050101.txt",
          "2026-07-26 05:01:03: Session started.\n"
          "4 levels: Cadwell Park (Woodlands) R v2.0, Cadwell Park (Woodlands) R v2.0...\n")
check("abgeschnittene Liste, erster Name vollstaendig",
      (A.read_live_combo() or {}).get("track"), "Cadwell Park (Woodlands) R v2.0")

# erster Name selbst abgeschnitten -> nur ueber die Level-Dateien aufloesbar
open(os.path.join(A.LEVELS_DIR, "Ein sehr langer Streckenname der abgeschnitten wird.lvl"), "w").close()
write_log(tmp, "log.20260726.050101.txt",
          "2026-07-26 05:01:03: Session started.\n"
          "4 levels: Ein sehr langer Streckenname der abgeschnitte...\n")
check("abgeschnittener Name wird ueber die .lvl-Dateien aufgeloest",
      (A.read_live_combo() or {}).get("track"),
      "Ein sehr langer Streckenname der abgeschnitten wird")

open(os.path.join(A.LEVELS_DIR, "Ein sehr langer Streckenname der abgeschnitten wird 2.lvl"), "w").close()
check("mehrdeutig abgeschnitten -> lieber keine Antwort", A.read_live_combo(), None)

print("\n3) Race-Guard und Verifikation")
tmp = sandbox()
A.write_json(A.CONFIG, CFG)
A.write_json(A.APPLIED, dict(CFG, track="Etwas anderes"))
open(A.RESTART_LOCK, "w").close()
A.main()
check("Restart laeuft -> kein autorun geschrieben", os.path.exists(A.AUTORUN), False)
os.utime(A.RESTART_LOCK, (time.time() - A.LOCK_MAX_AGE - 60,) * 2)
check("veraltetes Lock wird ignoriert", A.restart_in_progress(), False)

check("wait_consumed: Datei verschwindet -> True",
      A.wait_consumed(os.path.join(tmp, "gibtsnicht"), 1), True)
open(A.AUTORUN, "w").close()
check("wait_consumed: Datei bleibt liegen -> False", A.wait_consumed(A.AUTORUN, 1), False)
os.remove(A.AUTORUN)

print("\n4) main(): Capture, Panel-Save, leerer Server")
tmp = sandbox()
# a) Live-Combo weicht ab, kein Panel-Save pending -> Capture in die Web-Config
applied = dict(CFG, track="Bangowitch Circuit 1.02 (F3O)", vehicle="FoRc Feralheart v2")
A.write_json(A.CONFIG, applied)
A.write_json(A.APPLIED, applied)
os.utime(A.APPLIED, (0, A._epoch("2026-07-25 05:01:01")))
A.main()
check("Capture schreibt die live gefahrene Combo in die Web-Config",
      A.read_json(A.CONFIG)["track"], "Cadwell Park (Woodlands) R v2.0")
check("Capture markiert sie zugleich als applied (kein Re-Push)",
      A.read_json(A.APPLIED)["track"], "Cadwell Park (Woodlands) R v2.0")
check("Capture schreibt keinen autorun", os.path.exists(A.AUTORUN), False)

# b) Stale-Guard: Live-Beobachtung aelter als der letzte Apply -> kein Capture
tmp = sandbox()
A.write_json(A.CONFIG, applied)
A.write_json(A.APPLIED, applied)
os.utime(A.APPLIED, (0, time.time()))
A.main()
check("Beobachtung vor dem letzten Apply -> kein Capture",
      A.read_json(A.CONFIG)["track"], "Bangowitch Circuit 1.02 (F3O)")

# c) Panel-Save (cfg != applied) -> Setup-Push mit Broadcast
tmp = sandbox()
A.write_json(A.CONFIG, dict(CFG, track="Inturbolagos"))
A.write_json(A.APPLIED, CFG)
A.server_uptime = lambda: 3600
A.wait_consumed = lambda p, t: True
A.main()
cmds = open(A.AUTORUN).read() if os.path.exists(A.AUTORUN) else ""
check("Panel-Save pusht die Strecke", "/level /add 'Inturbolagos'" in cmds, True)
check("Panel-Save pusht 4x (events_per_session)", cmds.count("/level /add"), 4)
check("Panel-Save broadcastet 'New setup'", "New setup: Inturbolagos" in cmds, True)
check("Panel-Save springt zum naechsten Event", cmds.strip().endswith("/continue"), True)

# d) nur Admin-Liste invalidiert (das macht restart_server.sh) -> kein /continue
tmp = sandbox()
A.write_json(A.CONFIG, CFG)
A.write_json(A.APPLIED, dict(CFG, ingame_admins=None))
A.server_uptime = lambda: 3600
A.wait_consumed = lambda p, t: True
A.main()
cmds = open(A.AUTORUN).read() if os.path.exists(A.AUTORUN) else ""
check("Admin-Sync pusht /admins", "/admins /add 76561197989276622" in cmds, True)
check("Admin-Sync unterbricht die laufende Session nicht", "/continue" in cmds, False)
check("Admin-Sync fasst die Strecke nicht an", "/level" in cmds, False)

# e) Server ohne Levels -> stiller Restore, aber nur einmal pro Boot
tmp = sandbox()
for f in os.listdir(A.LOGS_DIR):
    os.remove(os.path.join(A.LOGS_DIR, f))
write_log(tmp, "log.20260726.050101.txt",
          "2026-07-26 05:01:03: Session started.\nNo levels\n")
A.write_json(A.CONFIG, CFG)
A.write_json(A.APPLIED, CFG)  # nichts geaendert -> normalerweise Nichtstun
A.server_uptime = lambda: 3600
A.boot_stamp = lambda: 12345.0
A.wait_consumed = lambda p, t: True
A.main()
cmds = open(A.AUTORUN).read() if os.path.exists(A.AUTORUN) else ""
check("leerer Server wird wiederhergestellt", "/level /add" in cmds, True)
check("Wiederherstellung bleibt still (kein Broadcast)", "New setup" in cmds, False)
os.remove(A.AUTORUN)
A.main()
check("zweiter Lauf im selben Boot laesst es sein", os.path.exists(A.AUTORUN), False)

print(f"\n{ok} ok, {fail} fehlgeschlagen")
sys.exit(1 if fail else 0)
