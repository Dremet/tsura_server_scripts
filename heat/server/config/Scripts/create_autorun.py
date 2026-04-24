import os
import sys
import time
import random


### CONSTANTS ###

NUMBER_TRACKS = 4

TRACKS = [
    ("Bilster Berg v1.01", 1),
    ("Sliders Island v1.0", 1),
    ("Charlotte Speedway RC A V1.02", 1),
    ("Lotta Sisu Circuit v1.2", 1),
    ("Singapore Street Circuit v1.1", 1),
    ("Testing Sebring v1.2", 1),
    ("Taupo Motorsport Park T1 v1.0.0", 1),
    ("Tomula GP v2.01", 1),
    ("Jäädytetty Indeksi - Club Layout", 1),
    ("Sachsenring GP Circuit v1.2", 1),
    ("Il Giro (short) v5.0", 1),
    ("UlpettilaSörkit v11", 1),
    ("Rosenholm Circuit", 1),
    ("Donnington Park (Prewar) v2", 1),
    ("Hassain Sula GP v1.00", 1),
    ("Bristol (Road Course) v1.2", 1),
    ("Nordschleife.zip v1.1", 1),
    ("VSR-Homeland V1.5", 1),
    ("CSup - Lost Lagoons v1", 1),
    ("Buffalo Hill - Rallycross v1.0", 1),
    ("Bristol Motor Speedway v1.0", 1),
    ("Il Giro (full) v5.0", 1),
    ("Castle Combe Circuit V1.00", 1),
    ("Nashville Music City GP v1.02", 1),
    ("Queensland Raceway V1.00", 1),
    ("Norisring v1.03", 1),
    ("Lime Rock Park V2.00", 1),
    ("Candyville Sfinx v1.3", 1),
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
        "/broadcast Session starts in 1 minute!",
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
        "/broadcast Session started! Setting things up…",
        "/admins /clear",
        "/admins /add 76561197989276622",  # dremet
        "/admins /add 76561198131829686",  # mcvizn
        "/admins /add 76561198096169747",  # cyberpunk
        "/vehicles /clear",
        "/levels /clear",
        # turn off fuel selection at beginning of race
    ]

    # as no vehicles are selected, it will auto-select sporty but we will change that at event init

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
        "/broadcast ### Success! Everything has been set up! Enjoy the races!",
        "/broadcast # There is a 2 lap qualifier for each track. Starting order is always 'Last Event'.",
        "/broadcast # Fuel consumption and tire degradation are randomized for each race.",
        "/broadcast # In this heat cars are also selected randomly for each track.",
    ]

    write_to_autorun(commands)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(select_random_elements_with_weights(TRACKS, NUMBER_TRACKS))
        print("Usage: python create_autorun.py <function_name>")
    else:
        function_name = sys.argv[1]
        run_function_by_name(function_name)
