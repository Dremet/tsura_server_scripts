"""create_autorun.py (Career) — cron-driven session bootstrap for the TSURA
Career server. Adapted from the tripleheat template.

Career specifics:
  * NUMBER_TRACKS = 2  -> two races per evening, each preceded by a quali
    (each track is queued twice: first Hotlapping/quali, then Race).
  * No fixed vehicle list: each driver races their own tuned car. The cars are
    generated + placed in config/Vehicles/ by career_prepare_session.py before
    the session; start_session issues /refreshfiles so the server picks them up.
    The choosable list + per-driver /forcevehicle are emitted per event by
    run_event_init.py (they must be re-applied every event).
"""
import os
import sys
import time
import random

### CONSTANTS ###
NUMBER_TRACKS = 2

TRACKS = [
    # same track pool as tripleheat, EQUAL probability (all weight 1)
    ('Sebring v0.9967', 1),
    ('Automotodrom Zaluzani v1 R', 1),
    ('Bikernieki (HSR) v1.0 R', 1),
    ('Suzuka (East Circuit) v1 R', 1),
    ('Lime Rock Park GP V2.02', 1),
    ('Buriram Intl. Circuit V1.01', 1),
    ('Circuit Zandvoort V1.04', 1),
    ('Brands Hatch GP Circuit V2.01', 1),
    ('Mexico City Eprix 2026 V1.00', 1),
    ('Buenos Aires Eprix Circuit V1.01', 1),
    ('Circuito Vasco Sameiro v1.1 Xmas', 1),
    ('Punta del Este Eprix V1.00', 1),
    ('Sanya Eprix Circuit V1.00', 1),
    ('Portland Int. Raceway V1.01', 1),
    ('Lusail Intl. Circuit V3.02', 1),
    ('Abu Dhabi GP v1.03', 1),
    ('Circuit de Reims Gueux V1.01', 1),
    ('Circuit of the Americas v1.043', 1),
    ('Sepang Circuit V2.02', 1),
    ('Barcelona GP - Catalunya v1.1', 1),
    ('Silverstone Circuit V1.07', 1),
    ('Japanese GP v2.13', 1),
    ('Balaton Park Circuit v1.01', 1),
    ('Hockenheimring GP v1.42', 1),
    ('Motorsport Arena Oschersleben v2', 1),
    ('National Racetrack Monza v1.5', 1),
    ('Nanoli Full Circuit v1.4', 1),
    ('TT Circuit Assen V1.7', 1),
    ('Elethasia Island Circuit v1.01', 1),
    ('Watkins Glen International v1.5', 1),
    ('Spa Francorchamps GP v3.22', 1),
    ('Hungaroring V2.04', 1),
    ('Canadian GP v1.23', 1),
    ('Australian GP v1.16', 1),
    ('Daytona Road Course V2.01', 1),
    ('Brazilian GP v1.04', 1),
    ('Raijin Mountain Circuit v1.00nsd', 1),
    ('Circuit Zolder v1.03', 1),
    ('Imola GP v1.16', 1),
    ('RedBull Ring GP v1.40', 1),
    ('Monaco GP v1.03', 1),
    ('Long Beach Circuit v1.1', 1),
    ('Road America V2.02', 1),
    ('Shanghai Circuit V2.01', 1),
    ('Laguna Seca Raceway v1.5', 1),
    ('Miami GP v1.02', 1),
]

ADMINS = [
    "76561197989276622",  # dremet
    "76561198131829686",  # mcvizn
    "76561198813518085",  # igiava
]


### HELPERS ###
def run_function_by_name(function_name):
    if function_name in globals() and callable(globals()[function_name]):
        globals()[function_name]()
    else:
        print(f"Error: Function '{function_name}' not found or is not callable.")


def wait_for_autorun_file(func):
    def wrapper(*args, **kwargs):
        while os.path.exists("autorun.src"):
            print("Waiting for 'autorun.src' to be removed...")
            time.sleep(0.5)
        return func(*args, **kwargs)
    return wrapper


def write_to_autorun(commands):
    with open("autorun.src", "w") as file:
        file.write("\n".join(commands) + "\n")


def select_random_elements_with_weights(tracks_with_weights, n=2):
    if n > len(tracks_with_weights):
        raise ValueError("n cannot be greater than the length of the list.")
    items, weights = zip(*tracks_with_weights)
    selected = random.choices(items, weights=weights, k=n)
    while len(set(selected)) < n:
        selected = random.choices(items, weights=weights, k=n)
    return selected


def save_quali_marker_file():
    with open("next_event_is_quali", "w") as file:
        pass


### CRON ENTRY POINTS ###
@wait_for_autorun_file
def announce_1_minute():
    write_to_autorun(["/broadcast TSU Career session starts in 1 minute!"])


@wait_for_autorun_file
def skip_to_new_session():
    write_to_autorun(["/continue"])


@wait_for_autorun_file
def start_session():
    save_quali_marker_file()
    # session lock: run_prepare.sh must NOT regenerate .veh while this exists
    open("session_active", "w").close()

    commands = [
        "/timerOn = True",
        "/broadcast TSU Career session started! Setting things up…",
        "/admins /clear",
    ]
    commands += [f"/admins /add {sid}" for sid in ADMINS]
    # make the freshly generated per-driver .veh files known to the server
    commands += [
        "/refreshfiles",
        "/vehicles /clear",
        "/levels /clear",
    ]

    tracks = select_random_elements_with_weights(TRACKS, NUMBER_TRACKS)
    duplicated_tracks = []
    for track in tracks:
        duplicated_tracks.append(track)  # quali (Hotlapping)
        duplicated_tracks.append(track)  # race
    commands += [f"/level /add '{track}'" for track in duplicated_tracks]

    commands += [
        "/broadcast ### TSU Career ready! Two races tonight, each with a 3-lap quali.",
        "/broadcast # You drive your own tuned car — upgrade it on tsura.org.",
    ]
    write_to_autorun(commands)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(select_random_elements_with_weights(TRACKS, NUMBER_TRACKS))
        print("Usage: python create_autorun.py <function_name>")
    else:
        run_function_by_name(sys.argv[1])
