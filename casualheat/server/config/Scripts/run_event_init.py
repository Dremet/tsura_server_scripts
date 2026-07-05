import os
import random

### SETUP

CARS = [
    ("Hawk v3", 1),
    ("Countach Retro GT", 1),
    ("F3 Proto-R v2", 1),
    ("Opel Kadett 2.0", 1),
    ("LMP1 v2", 1),
    ("Buick GNX-JB GrT", 1),
    ("F_Xtreme 2", 1),
    ("Honda NSX GT3", 1),
    ("McSimCadeR v3", 1),
    ("Ford MustangGT V8 v4", 1),
    ("Porsche 911 GT2", 1),
    ("Tourist Car", 1),
    ("Vost 1.1", 1),
]

# QUALI
QUALI_LAPS = 2
QUALI_MAX_MINUTES = 5
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
RACE_LAPS = 500
RACE_MAX_MINUTES = 8
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(180, 450)  # random.randint(230, 625)
tire_deg = random.randint(500, 1300)  # random.randint(500, 1600)

number_compounds = random.randint(1, 2)

if number_compounds == 2:
    soft_tire_deg = int(round(tire_deg / 2, 0))


### HELPER ###


def get_tire_deg_desc(deg):
    """Get a description string for tire degradation value."""
    if deg < 350:
        return "Extremely High!"
    elif deg < 550:
        return "Very High"
    elif deg < 700:
        return "High"
    elif deg < 850:
        return "Above Average"
    elif deg < 1000:
        return "Moderate"
    elif deg < 1150:
        return "Below Average"
    else:
        return "Low"


def get_fuel_cons_desc(cons):
    """Get a description string for fuel consumption value."""
    if cons < 270:
        return "Above Average"
    elif cons < 360:
        return "Moderate"
    else:
        return "Below Average"


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


def select_random_elements_with_weights(cars_with_weights, n=1):
    """
    Select `n` random elements from a list of (element, weight) tuples with weighted probabilities.
    Elements with lower weights are less likely to be selected.
    """
    if n > len(cars_with_weights):
        raise ValueError("n cannot be greater than the length of the list.")

    # Split the list of tuples into separate lists for items and weights
    items, weights = zip(*cars_with_weights)

    # Use random.choices with weights to bias selection
    selected = random.choices(items, weights=weights, k=n)

    # Ensure unique selections (if duplicates occur, reselect)
    while len(set(selected)) < n:
        selected = random.choices(items, weights=weights, k=n)

    return selected


### MAIN ###

quali = is_next_event_quali()
print(quali)
if quali:
    car = select_random_elements_with_weights(CARS, 1)[0]

    point_commands = [
        "/points.position1 = 3",
        "/points.position2 = 2",
        "/points.position3 = 1",
    ]

    for i in range(4, 21):
        point_commands.append(f"/points.position{i} = 0")

    commands = [
        "/broadcast <color=#0d6efd>[Casual Heat]</color> Qualifying coming up…",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        "/race.startStyle = Countdown",
        "/race.ContactRules = EqualGhosts",
        "/fuel.fuelOn = 0",
        "/tireWear.tireWearOn = 0",
        "/vehicles /clear",
        f"/vehicles /add '{car}'",
        # f"/fuelFullGasTime = {QUALI_FUEL}",
        # f"/tireWear.compound1Endurance = {QUALI_TIRES}",
        f"/broadcast <color=#0d6efd>[Casual Heat]</color> Selected car: {car}",
        "/broadcast <color=#0d6efd>[Casual Heat]</color> <color=#aaaaaa>UI may show a different mode — this is the quali.</color>",
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
        "/broadcast <color=#0d6efd>[Casual Heat]</color> Race coming up…",
        "/race.raceMode = Race",
        f"/race.maxLaps = {RACE_LAPS}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        "/race.startStyle = Random",
        "/race.ContactRules = Normal",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/broadcast <color=#0d6efd>[Casual Heat]</color> Tire compounds: {number_compounds}",
    ]

    commands = point_commands + commands

    desc_tire_deg = get_tire_deg_desc(tire_deg)
    desc_fuel_cons = get_fuel_cons_desc(fuel)

    if number_compounds == 1:
        commands.append(f"/tireWear.tireCompoundCount = 1")
        commands.append(f"/tireWear.compound1Endurance = {tire_deg}")
        commands.append(f"/tireWear.compound1InitialPerformance = 100")
        commands.append(f"/broadcast <color=#0d6efd>[Casual Heat]</color> Tire degradation: {desc_tire_deg} <color=#aaaaaa>({tire_deg})</color>")
    else:
        desc_soft_tire_deg = get_tire_deg_desc(soft_tire_deg)
        commands.append(f"/tireWear.tireCompoundCount = 2")
        commands.append(f"/tireWear.compound1Endurance = {soft_tire_deg}")
        commands.append(
            f"/broadcast <color=#0d6efd>[Casual Heat]</color> Compound 1 (Soft): {desc_soft_tire_deg} <color=#aaaaaa>({soft_tire_deg}, initial performance 100)</color>"
        )
        commands.append(f"/tireWear.compound1InitialPerformance = 100")
        commands.append(f"/tireWear.compound2Endurance = {tire_deg}")
        commands.append(
            f"/broadcast <color=#0d6efd>[Casual Heat]</color> Compound 2 (Medium): {desc_tire_deg} <color=#aaaaaa>({tire_deg}, initial performance 88)</color>"
        )
        commands.append(f"/tireWear.compound2InitialPerformance = 88")

    commands += [
        f"/broadcast <color=#0d6efd>[Casual Heat]</color> Fuel consumption: {desc_fuel_cons} <color=#aaaaaa>({fuel})</color>",
        "/broadcast <color=#0d6efd>[Casual Heat]</color> <color=#aaaaaa>UI may show a different mode — this is the race.</color>",
    ]


print(commands)
with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")