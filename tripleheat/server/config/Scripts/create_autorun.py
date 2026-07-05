import os
import sys
import time
import random


### CONSTANTS ###

NUMBER_TRACKS = 3

TRACKS = [
    ("Sebring v0.9967", 1),
    ("Automotodrom Zaluzani v1 R", 1),
    ("Bikernieki (HSR) v1.0 R", 1),
    ("Suzuka (East Circuit) v1 R", 1),
    ("Lime Rock Park GP V2.02", 1),
    ("Buriram Intl. Circuit V1.01", 1),
    ("Circuit Zandvoort V1.04", 1),
    ("Brands Hatch GP Circuit V2.01", 1),
    ("Mexico City Eprix 2026 V1.00", 1),
    ("Buenos Aires Eprix Circuit V1.01", 1),
    ("Circuito Vasco Sameiro v1.1 Xmas", 1),
    ("Punta del Este Eprix V1.00", 1),
    ("Sanya Eprix Circuit V1.00", 1),
    ("Portland Int. Raceway V1.01", 1),
    ("Lusail Intl. Circuit V3.02", 1),
    ("Abu Dhabi GP v1.03", 1),
    ("Circuit de Reims Gueux V1.01", 1),
    ("Circuit of the Americas v1.043", 0.3),
    ("Sepang Circuit V2.02", 0.3),
    ("Barcelona GP - Catalunya v1.1", 0.3),
    ("Silverstone Circuit V1.07", 0.3),
    ("Japanese GP v2.13", 0.3),
    ("Balaton Park Circuit v1.01", 0.3),
    ("Hockenheimring GP v1.42", 0.3),
    ("Motorsport Arena Oschersleben v2", 0.3),
    ("National Racetrack Monza v1.5", 0.3),
    ("Nanoli Full Circuit v1.4", 0.3),
    ("TT Circuit Assen V1.7", 0.3),
    ("Elethasia Island Circuit v1.01", 0.3),
    ("Watkins Glen International v1.5", 0.3),
    ("Spa Francorchamps GP v3.22", 0.3),
    ("Hungaroring V2.04", 0.3),
    ("Canadian GP v1.23", 0.3),
    ("Australian GP v1.16", 0.3),
    ("Daytona Road Course V2.01", 0.3),
    ("Brazilian GP v1.04", 0.3),
    ("Raijin Mountain Circuit v1.00nsd", 0.3),
    ("Circuit Zolder v1.03", 0.3),
    ("Imola GP v1.16", 0.3),
    ("RedBull Ring GP v1.40", 0.3),
    ("Monaco GP v1.03", 0.3),
    ("Long Beach Circuit v1.1", 0.3),
    ("Road America V2.02", 0.3),
    ("Shanghai Circuit V2.01", 0.3),
    ("Laguna Seca Raceway v1.5", 0.3),
    ("Miami GP v1.02", 0.3),
]

VEHICLES = [
    "Mercedes-AMG GT3 v5",
    "Ford Mustang GT3 v5",
    "Ferrari 296 GT3 v5"
]


### HELPER FUNCTIONS ###


def run_function_by_name(function_name):
    """Run a function in this file by its name."""
    if function_name in globals() and callable(globals()[function_name]):
        globals()[function_name]()
    else:
        print(f"Error: Function '{function_name}' not found or is not callable.")


def wait_for_autorun_file(func):
    """Decorator to wait until 'autorun.src' file disappears before running the function."""

    def wrapper(*args, **kwargs):
        while os.path.exists("autorun.src"):
            print("Waiting for 'autorun.src' to be removed...")
            time.sleep(0.5)
        return func(*args, **kwargs)

    return wrapper


def write_to_autorun(commands):
    """
    Helper function to write commands to 'autorun.src' file.
    Overwrites the file if it exists.
    """
    with open("autorun.src", "w") as file:
        file.write("\n".join(commands) + "\n")


def select_random_elements_with_weights(tracks_with_weights, n=3):
    """
    Select `n` random elements from a list of (element, weight) tuples with weighted probabilities.
    Elements with lower weights are less likely to be selected.
    """
    if n > len(tracks_with_weights):
        raise ValueError("n cannot be greater than the length of the list.")

    # Split the list of tuples into separate lists for items and weights
    items, weights = zip(*tracks_with_weights)

    # Use random.choices with weights to bias selection
    selected = random.choices(items, weights=weights, k=n)

    # Ensure unique selections (if duplicates occur, reselect)
    while len(set(selected)) < n:
        selected = random.choices(items, weights=weights, k=n)

    return selected


def save_quali_marker_file():
    """
    Creates an empty file called 'next_event_is_quali'.
    Used to allow the other python scripts to know at which state of the session we are.
    """
    with open("next_event_is_quali", "w") as file:
        pass


### FUNCTIONS TO RUN AT CERTAIN TIMES ###


@wait_for_autorun_file
def announce_1_minute():
    commands = [
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> Session starts in <b>1 minute</b>!",
    ]
    write_to_autorun(commands)


@wait_for_autorun_file
def skip_to_new_session():
    commands = [
        "/continue",
    ]
    write_to_autorun(commands)


@wait_for_autorun_file
def start_session():
    save_quali_marker_file()

    commands = [
        "/timerOn = True",
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> Session started! Setting things up…",
        "/admins /clear",
        "/admins /add 76561197989276622",  # dremet
        "/admins /add 76561198131829686",  # mcvizn
        "/admins /add 76561198096169747",  # cyberpunk
        "/vehicles /clear",
        "/levels /clear",
        # turn off fuel selection at beginning of race
    ]

    # add vehicles
    commands += [f"/vehicle /add '{vehicle}'" for vehicle in VEHICLES]

    # add randomly selected tracks
    tracks = select_random_elements_with_weights(TRACKS, NUMBER_TRACKS)

    # duplicate each track for qualification
    duplicated_tracks = []
    for track in tracks:
        # Add the track twice (first for hotlapping, then for race)
        duplicated_tracks.append(track)  # Hotlapping
        duplicated_tracks.append(track)  # Race

    commands += [f"/level /add '{track}'" for track in duplicated_tracks]

    print(commands)

    commands += [
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <b>Ready!</b> Enjoy the races!",
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> 1-lap quali per track — starting order is always <b>Last Event</b>.",
        "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> Fuel & tire wear are <b>randomized</b> each race.",
    ]

    write_to_autorun(commands)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(select_random_elements_with_weights(TRACKS, NUMBER_TRACKS))
        print("Usage: python create_autorun.py <function_name>")
    else:
        function_name = sys.argv[1]
        run_function_by_name(function_name)
