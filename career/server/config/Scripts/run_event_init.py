"""run_event_init.py (Career) — generates event_init_generated.src before each
event. Alternates quali (Hotlapping, 3 laps) and race using the
'next_event_is_quali' marker, and forces every driver onto their own tuned car.

Per-driver cars come from assignments.json (written by career_prepare_session.py).
Forced vehicles are cleared by the server when advancing to the next event, so
they are re-emitted here for BOTH the quali and the race of every track.
"""
import json
import os

# QUALI (3-lap qualifying sets the grid for the race)
QUALI_LAPS = 3
QUALI_MAX_MINUTES = 6

# RACE (a bit longer than the tripleheat races)
import random
RACE_LAPS = random.randint(12, 18)
RACE_MAX_MINUTES = 30

# fuel + tire wear like tripleheat: randomized per race
fuel = random.randint(230, 675)
tires = random.randint(500, 1700)


# Quali/race mode is restart-robust: it only advances when an event actually
# finished (run_event_end drops CAREER_EVENT_DONE). A restart re-fires this
# init WITHOUT an event-end, so the mode is kept instead of flipping.
MODE_FILE = "career_event_mode"   # "quali" or "race"
DONE_FILE = "career_event_done"   # present iff an event finished since last init


def is_next_event_quali():
    mode = "quali"
    if os.path.exists(MODE_FILE):
        mode = (open(MODE_FILE).read().strip() or "quali")
    if os.path.exists(DONE_FILE):        # genuine event completion -> advance
        mode = "race" if mode == "quali" else "quali"
        os.remove(DONE_FILE)
    with open(MODE_FILE, "w") as f:
        f.write(mode)
    return mode == "quali"


def vehicle_commands():
    """Choosable list of every driver's car + a /forcevehicle per Steam ID."""
    path = "assignments.json"
    if not os.path.exists(path):
        return ["/broadcast <color=#ffc107>[Career]</color> <color=#ff6b6b>No car assignments found — using default cars!</color>"]
    data = json.load(open(path, encoding="utf-8"))
    cmds = ["/vehicles /clear"]
    for a in data.get("assignments", []):
        cmds.append(f"/vehicles /add '{a['vehicle']}'")
    # force each driver onto their own car by Steam ID
    for a in data.get("assignments", []):
        cmds.append(f"/forcevehicle {a['steam_id']} '{a['vehicle']}'")
    return cmds


quali = is_next_event_quali()

# refresh between events (refused mid-event): picks up .veh files that were
# fixed/added after session start, before /vehicles + /forcevehicle run
refresh = ["/refreshfiles"]

if quali:
    commands = [
        "/broadcast <color=#ffc107>[Career]</color> Qualifying — 3 laps, you drive your own tuned car",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        "/race.startStyle = Countdown",
        "/race.ContactRules = EqualGhosts",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        "/damage.collisionDamageOn = 0",
    ]
else:
    commands = [
        "/broadcast <color=#ffc107>[Career]</color> Race — grid from qualifying",
        "/race.raceMode = Race",
        f"/race.maxLaps = {RACE_LAPS}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        "/race.startStyle = Standing",
        "/race.ContactRules = Normal",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/tireWear.compound1Endurance = {tires}",
        "/damage.collisionDamageOn = 0",
    ]

# force per-driver cars on every event (quali and race)
commands = refresh + commands + vehicle_commands()

with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

print(f"quali={quali}; {len(commands)} commands written")
