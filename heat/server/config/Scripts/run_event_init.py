import os
import random

### SETUP

CARS = [
    ("Hawk v3", 1),
    ("Countach 5k QV v1", 1),
    ("F3 Proto-R", 1),
    ("Opel Kadett 2.0", 1),
    ("LMP1 v2", 1),
    ("Buick GNX-JB GrT", 1),
    ("F_Xtreme 2", 1),
    ("Honda NSX GT3", 1),
]

# QUALI
QUALI_LAPS = 2
QUALI_MAX_MINUTES = 5
# QUALI_FUEL = 500
# QUALI_TIRES = 800

# RACE
RACE_LAPS = 500
RACE_MAX_MINUTES = 11
# generate random fuel consumption
# the bigger the value, the longer the stints
fuel = random.randint(500, 700)  # random.randint(230, 625)
tire_deg = random.randint(700, 1700)  # random.randint(500, 1600)

number_compounds = random.randint(1, 2)

if number_compounds == 2:
    soft_tire_deg = int(round(tire_deg / 2, 0))


### HELPER ###


def get_tire_deg_desc(deg):
    """Get a description string for tire degradation value."""
    if deg < 500:
        return "Extremely High!"
    elif deg < 700:
        return "Very High"
    elif deg < 950:
        return "High"
    elif deg < 1100:
        return "Above Average"
    elif deg < 1300:
        return "Moderate"
    elif deg < 1500:
        return "Below Average"
    else:
        return "Low"


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

    commands = [
        "/broadcast Setting up Qualifying",
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
        f"/broadcast Selected car: {car}",
        "/broadcast Hotlapping now, even if the User Interface might show different",
    ]
else:
    commands = [
        "/broadcast Setting up Race",
        "/race.raceMode = Race",
        f"/race.maxLaps = {RACE_LAPS}",
        f"/race.maxMinutes = {RACE_MAX_MINUTES}",
        "/race.startStyle = Random",
        "/race.ContactRules = Normal",
        "/fuel.fuelOn = 1",
        "/tireWear.tireWearOn = 1",
        f"/fuelFullGasTime = {fuel}",
        f"/broadcast Number of tire compounds: {number_compounds}",
    ]

    desc_tire_deg = get_tire_deg_desc(tire_deg)

    if number_compounds == 1:
        commands.append(f"/tireWear.tireCompoundCount = 1")
        commands.append(f"/tireWear.compound1Endurance = {tire_deg}")
        commands.append(f"/tireWear.compound1InitialPerformance = 100")

    else:
        desc_soft_tire_deg = get_tire_deg_desc(soft_tire_deg)
        commands.append(f"/tireWear.tireCompoundCount = 2")
        commands.append(f"{soft_tire_deg} {tire_deg}")
        commands.append(f"/tireWear.compound1Endurance = {soft_tire_deg}")
        commands.append(
            f"/broadcast Degradation of Tire Compound 1 (Soft): {desc_soft_tire_deg}"
        )
        commands.append(f"/tireWear.compound1InitialPerformance = 100")
        commands.append(f"/tireWear.compound2Endurance = {tire_deg}")
        commands.append(
            f"/broadcast Degradation of Tire Compound 2 (Medium): {desc_tire_deg}"
        )
        commands.append(f"/tireWear.compound2InitialPerformance = 88")

    commands.append(
        "/broadcast Race now, even if the User Interface might show different"
    )


print(commands)
with open("event_init_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
