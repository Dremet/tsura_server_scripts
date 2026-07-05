import os
import random

### SETUP
# QUALI
QUALI_LAPS = 1
QUALI_MAX_MINUTES = 3
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
race_laps = random.randint(8, 10)
RACE_MAX_MINUTES = 1440
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(230, 675)  # random.randint(230, 625)
tires = random.randint(500, 1700)  # random.randint(500, 1600)


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
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <b>Qualifying</b> coming up…",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        "/race.startStyle = Countdown",
        "/race.ContactRules = EqualGhosts",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        # f"/fuelFullGasTime = {QUALI_FUEL}",
        # f"/tireWear.compound1Endurance = {QUALI_TIRES}",
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <color=#aaaaaa>UI may show a different mode — this is the quali.</color>",
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
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <b>Race</b> coming up…",
        "/race.raceMode = Race",
        f"/race.maxLaps = {race_laps}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        "/race.startStyle = Random",
        "/race.ContactRules = Normal",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/tireWear.compound1Endurance = {tires}",
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <color=#aaaaaa>UI may show a different mode — this is the race.</color>",
    ]

    commands = point_commands + commands


print(commands)
with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
