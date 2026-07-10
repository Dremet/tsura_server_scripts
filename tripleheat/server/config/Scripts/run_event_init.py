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
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
race_laps = random.randint(*webconfig.get_range(_CFG, "race", "laps_min", "laps_max", (8, 10)))
RACE_MAX_MINUTES = webconfig.get_num(_CFG, ("race", "max_minutes"), 1440)
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(*webconfig.get_range(_CFG, "race", "fuel_min", "fuel_max", (230, 675)))
tires = random.randint(*webconfig.get_range(_CFG, "race", "tires_min", "tires_max", (500, 1700)))


### HELPER ###
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
    point_commands = [
        "/points.position1 = 3",
        "/points.position2 = 2",
        "/points.position3 = 1",
    ]

    for i in range(4, 21):
        point_commands.append(f"/points.position{i} = 0")

    commands = [
        "/broadcast <color=#dc3545>[TripleHeat]</color> Qualifying coming up…",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        "/race.startStyle = Countdown",
        "/race.ContactRules = EqualGhosts",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        # f"/fuelFullGasTime = {QUALI_FUEL}",
        # f"/tireWear.compound1Endurance = {QUALI_TIRES}",
        "/broadcast <color=#dc3545>[TripleHeat]</color> <color=#aaaaaa>UI may show a different mode — this is the quali.</color>",
    ]

    commands = point_commands + commands
else:
    point_commands = [
        "/points.position1 = 20",
        "/points.position2 = 16",
        "/points.position3 = 13",
        "/points.position4 = 10",
        "/points.position5 = 8",
        "/points.position6 = 6",
        "/points.position7 = 4",
        "/points.position8 = 3",
        "/points.position9 = 2",
        "/points.position10 = 1",
    ]

    for i in range(11, 21):
        point_commands.append(f"/points.position{i} = 0")

    commands = [
        "/broadcast <color=#dc3545>[TripleHeat]</color> Race coming up…",
        "/race.raceMode = Race",
        f"/race.maxLaps = {race_laps}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        "/race.startStyle = Random",
        "/race.ContactRules = Normal",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/tireWear.compound1Endurance = {tires}",
        "/broadcast <color=#dc3545>[TripleHeat]</color> <color=#aaaaaa>UI may show a different mode — this is the race.</color>",
    ]

    commands = point_commands + commands


print(commands)
with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
