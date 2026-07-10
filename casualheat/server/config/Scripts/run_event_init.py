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
_CFG = webconfig.load("casual_heat")

DEFAULT_CARS = [
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

CARS = webconfig.get_weighted(_CFG, "cars", DEFAULT_CARS)

# QUALI
QUALI_LAPS = webconfig.get_num(_CFG, ("quali", "laps"), 2)
QUALI_MAX_MINUTES = webconfig.get_num(_CFG, ("quali", "max_minutes"), 5)
QUALI_START_STYLE = webconfig.get_str(_CFG, ("quali", "start_style"), "Countdown")
QUALI_CONTACT_RULES = webconfig.get_str(_CFG, ("quali", "contact_rules"), "EqualGhosts")
QUALI_POINTS = webconfig.get_intlist(_CFG, ("quali", "points"), [3, 2, 1])
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
RACE_LAPS = webconfig.get_num(_CFG, ("race", "max_laps"), 500)
RACE_MAX_MINUTES = webconfig.get_num(_CFG, ("race", "max_minutes"), 8)
RACE_START_STYLE = webconfig.get_str(_CFG, ("race", "start_style"), "Random")
RACE_CONTACT_RULES = webconfig.get_str(_CFG, ("race", "contact_rules"), "Normal")
RACE_POINTS = webconfig.get_intlist(_CFG, ("race", "points"),
                                    [20, 16, 13, 10, 8, 6, 4, 3, 2, 1])
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(*webconfig.get_range(_CFG, "race", "fuel_min", "fuel_max", (180, 450)))
tire_deg = random.randint(*webconfig.get_range(_CFG, "race", "tires_min", "tires_max", (500, 1300)))

max_compounds = max(1, min(2, int(webconfig.get_num(_CFG, ("race", "max_compounds"), 2))))
number_compounds = random.randint(1, max_compounds)

if number_compounds == 2:
    soft_tire_deg = int(round(tire_deg / 2, 0))


### HELPER ###


def build_point_commands(points):
    """Point commands for positions 1..20 from a points table."""
    points = list(points)[:20]
    cmds = [f"/points.position{i} = {p}" for i, p in enumerate(points, 1)]
    cmds += [f"/points.position{i} = 0" for i in range(len(points) + 1, 21)]
    return cmds


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

    point_commands = build_point_commands(QUALI_POINTS)

    commands = [
        "/broadcast <color=#0d6efd>[Casual Heat]</color> Qualifying coming up…",
        "/race.raceMode = Hotlapping",
        f"/race.maxLaps = {QUALI_LAPS}",
        f"/race.maxMinutes = {QUALI_MAX_MINUTES}",
        f"/race.startStyle = {QUALI_START_STYLE}",
        f"/race.ContactRules = {QUALI_CONTACT_RULES}",
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
    point_commands = build_point_commands(RACE_POINTS)

    commands = [
        "/broadcast <color=#0d6efd>[Casual Heat]</color> Race coming up…",
        "/race.raceMode = Race",
        f"/race.maxLaps = {RACE_LAPS}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        f"/race.startStyle = {RACE_START_STYLE}",
        f"/race.ContactRules = {RACE_CONTACT_RULES}",
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
