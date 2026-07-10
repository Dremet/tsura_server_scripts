import os
import random

try:
    import webconfig
except Exception:  # a missing/broken helper must never kill a session
    class webconfig:
        load = staticmethod(lambda server: {})
        get_num = staticmethod(lambda cfg, path, default: default)
        get_range = staticmethod(lambda cfg, s, a, b, default: default)
        get_weighted = staticmethod(lambda cfg, key, default: default)
        get_strlist = staticmethod(lambda cfg, key, default: default)
        get_admins = staticmethod(lambda cfg, default: default)

### SETUP
# Values managed via the tsura.org admin panel (defaults = previous hardcoded values)
_CFG = webconfig.load("tripleheat")

# QUALI
QUALI_LAPS = webconfig.get_num(_CFG, ("quali", "laps"), 1)
QUALI_MAX_MINUTES = webconfig.get_num(_CFG, ("quali", "max_minutes"), 3)
QUALI_START_STYLE = webconfig.get_str(_CFG, ("quali", "start_style"), "Countdown")
QUALI_CONTACT_RULES = webconfig.get_str(_CFG, ("quali", "contact_rules"), "EqualGhosts")
QUALI_POINTS = webconfig.get_intlist(_CFG, ("quali", "points"), [3, 2, 1])
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
race_laps = random.randint(*webconfig.get_range(_CFG, "race", "laps_min", "laps_max", (8, 10)))
RACE_MAX_MINUTES = webconfig.get_num(_CFG, ("race", "max_minutes"), 1440)
RACE_START_STYLE = webconfig.get_str(_CFG, ("race", "start_style"), "Random")
RACE_CONTACT_RULES = webconfig.get_str(_CFG, ("race", "contact_rules"), "Normal")
RACE_POINTS = webconfig.get_intlist(_CFG, ("race", "points"),
                                    [20, 16, 13, 10, 8, 6, 4, 3, 2, 1])
# handling tweaks (2026-07-10): less tire-wear oversteer, stronger slipstream
TIRE_OVERSTEER_EFFECT = webconfig.get_num(_CFG, ("race", "tire_oversteering_effect"), 5)
DRAFT_SPEED = webconfig.get_num(_CFG, ("race", "drafting_speed_effect"), 5)
DRAFT_DIST = webconfig.get_num(_CFG, ("race", "drafting_max_distance"), 45)
DRAFT_ANGLE = webconfig.get_num(_CFG, ("race", "drafting_max_angle"), 20)
DRAFT_DOWNFORCE_RED = webconfig.get_num(_CFG, ("race", "drafting_downforce_reduction"), 12)
DRAFT_FOR_MAX = webconfig.get_num(_CFG, ("race", "drafting_for_maximum_effect"), 90)
DRAFT_ATTEN = webconfig.get_num(_CFG, ("race", "drafting_attenuation_power"), 1.5)
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(*webconfig.get_range(_CFG, "race", "fuel_min", "fuel_max", (230, 675)))
tires = random.randint(*webconfig.get_range(_CFG, "race", "tires_min", "tires_max", (500, 1700)))


### HELPER ###
def build_point_commands(points):
    """Point commands for positions 1..20 from a points table."""
    points = list(points)[:20]
    cmds = [f"/points.position{i} = {p}" for i, p in enumerate(points, 1)]
    cmds += [f"/points.position{i} = 0" for i in range(len(points) + 1, 21)]
    return cmds
def is_next_event_quali():
    """
    Checks if a file called 'next_event_is_quali' exists,
    and deletes it if it does.
    """
    exists = os.path.exists("next_event_is_quali")

    if exists:
        os.remove("next_event_is_quali")
    else:
        with open("next_event_is_quali", "w") as file:
            pass

    return exists


### MAIN ###

quali = is_next_event_quali()
print(quali)
if quali:
    point_commands = build_point_commands(QUALI_POINTS)

    commands = [
        "/broadcast <color=#dc3545>[TripleHeat]</color> Qualifying coming up…",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        f"/race.startStyle = {QUALI_START_STYLE}",
        f"/race.ContactRules = {QUALI_CONTACT_RULES}",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        # f"/fuelFullGasTime = {QUALI_FUEL}",
        # f"/tireWear.compound1Endurance = {QUALI_TIRES}",
        "/broadcast <color=#dc3545>[TripleHeat]</color> <color=#aaaaaa>UI may show a different mode — this is the quali.</color>",
    ]

    commands = point_commands + commands
else:
    point_commands = build_point_commands(RACE_POINTS)

    commands = [
        "/broadcast <color=#dc3545>[TripleHeat]</color> Race coming up…",
        "/race.raceMode = Race",
        f"/race.maxLaps = {race_laps}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        f"/race.startStyle = {RACE_START_STYLE}",
        f"/race.ContactRules = {RACE_CONTACT_RULES}",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/tireWear.compound1Endurance = {tires}",
        f"/tireWear.tireWearOversteeringEffect = {TIRE_OVERSTEER_EFFECT}",
        f"/drafting.draftingSpeedEffect = {DRAFT_SPEED}",
        f"/drafting.maxDraftingDistance = {DRAFT_DIST}",
        f"/drafting.maxDraftingAngle = {DRAFT_ANGLE}",
        f"/drafting.draftingDownforceReduction = {DRAFT_DOWNFORCE_RED}",
        f"/drafting.draftingForMaximumEffect = {DRAFT_FOR_MAX}",
        f"/drafting.draftingAttenuationPower = {DRAFT_ATTEN}",
        "/broadcast <color=#dc3545>[TripleHeat]</color> <color=#aaaaaa>UI may show a different mode — this is the race.</color>",
    ]

    commands = point_commands + commands


print(commands)
with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
