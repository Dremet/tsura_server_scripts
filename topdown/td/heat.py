"""Heat composition and scoring.

A heat is four tracks, each run as a one-lap qualifying followed by a race, so
eight game events in total. This module decides what gets driven -- which
tracks, how many laps and which car -- and how it is scored. It is deliberately
free of I/O and of wall-clock time: the caller passes in a random source, so a
heat can be replayed exactly in tests.

Scoring is McVizn's (2026-07-31):
  qualifying  1 point for P1, nothing else
  race        10 - 6 - 4 - 3 - 2 - 1, nothing from P7 down
Ties are broken by the better finishing positions across the heat: most wins
first, then most seconds, and so on.
"""

import os
import re

# Fallbacks used when the web config is missing or unreadable. A broken config
# must never stop a heat from running.
DEFAULT_QUALI_POINTS = [1]
DEFAULT_RACE_POINTS = [10, 6, 4, 3, 2, 1]
DEFAULT_TRACKS_PER_HEAT = 4
DEFAULT_LAP_BONUS_PCT = 20

# "ai-<level guid>-<vehicle guid>.aid", the layout McVizn uploaded on 2026-07-31.
_AI_FILE = re.compile(r"^ai-(?P<level>.+?)-(?P<vehicle>[^-]+-[^-]+)\.aid$", re.IGNORECASE)


def available_ai_lines(ai_dir):
    """Return the set of (level_guid, vehicle_guid) pairs that have a driving line.

    AI needs a line per track *and* per car, and TSU simply runs the race without
    bots when one is missing. Knowing which combinations are covered lets the
    controller say so out loud instead of leaving players wondering where the
    bots went.
    """
    pairs = set()
    try:
        names = os.listdir(ai_dir)
    except OSError:
        return pairs
    for fn in names:
        m = _AI_FILE.match(fn)
        if m:
            pairs.add((m.group("level").lower(), m.group("vehicle").lower()))
    return pairs


def has_ai_line(ai_pairs, level_guid, vehicle_guid):
    if not level_guid or not vehicle_guid:
        return False
    return (level_guid.lower(), vehicle_guid.lower()) in ai_pairs


def vehicle_pool(config):
    """The cars a heat may draw from, as a list of {name, guid, weight}.

    The config used to name exactly one car (`vehicle`/`vehicle_guid`); a pool
    lives in `vehicles`. Both are accepted so an old config keeps working, and
    the single-car form is simply a pool of one.
    """
    pool = []
    for entry in config.get("vehicles") or []:
        if isinstance(entry, dict) and entry.get("name"):
            pool.append({"name": entry["name"],
                         "guid": entry.get("guid", ""),
                         "weight": float(entry.get("weight", 1) or 0)})
    if pool:
        return pool
    if config.get("vehicle"):
        return [{"name": config["vehicle"],
                 "guid": config.get("vehicle_guid", ""), "weight": 1.0}]
    return []


def _weighted_draw(pool, rng):
    """Draw one entry, honouring weights; `pool` is modified."""
    weights = [float(p.get("weight", 1)) for p in pool]
    pick = rng.choices(pool, weights=weights, k=1)[0]
    pool.remove(pick)
    return pick


def pick_vehicles(vehicles, count, rng):
    """Choose the car for each of `count` races (André, 2026-08-11: per race).

    Weight 0 disables a car, same convention as the tracks. Cars are drawn from
    a bag that is refilled once empty, so with two cars and four races each is
    used twice instead of the same one possibly coming up four times in a row.
    """
    usable = [v for v in vehicles if float(v.get("weight", 1)) > 0]
    if not usable:
        return []
    chosen, bag = [], []
    for _ in range(count):
        if not bag:
            bag = list(usable)
        chosen.append(_weighted_draw(bag, rng))
    return chosen


def pick_tracks(tracks, count, rng):
    """Choose `count` distinct tracks, honouring per-track weights.

    Weight 0 disables a track (same convention as the TripleHeat config). If
    fewer tracks are enabled than requested, every enabled track is used once --
    a short heat beats no heat.
    """
    usable = [t for t in tracks if float(t.get("weight", 1)) > 0]
    if not usable:
        return []
    count = min(count, len(usable))
    pool = list(usable)
    return [_weighted_draw(pool, rng) for _ in range(count)]


def lap_bonus_pct(track, default=DEFAULT_LAP_BONUS_PCT):
    """How much a track's lap count may grow, in percent.

    Per track, because a two-minute lap and a thirty-second lap do not want the
    same swing; the global value stays as the fallback for tracks that say
    nothing. McVizn confirmed percent over absolute laps (2026-08-11).
    """
    value = track.get("lap_bonus_pct")
    if value in (None, ""):
        return float(default)
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return float(default)


def laps_for(track, rng, bonus_pct=DEFAULT_LAP_BONUS_PCT):
    """Lap count for one race: the configured base plus a random 0-`bonus_pct`%.

    McVizn asked for "10-20% more, but never fewer", so the bonus only ever
    rounds up: a 10-lap track runs 10 to 12 laps, never 9.
    """
    base = int(track.get("laps", 0) or 0)
    if base < 1:
        base = 1
    bonus = rng.uniform(0, lap_bonus_pct(track, bonus_pct) / 100.0)
    return base + int(base * bonus + 0.999) if bonus > 0 else base


def build_heat_plan(config, rng, ai_pairs=frozenset()):
    """Compose one heat: which tracks, how many laps, and whether bots can run.

    Returns a plain dict so it can be written to disk for the event-init hook
    and handed to the results layer unchanged.
    """
    tracks = config.get("tracks") or []
    per_heat = int(config.get("tracks_per_heat", DEFAULT_TRACKS_PER_HEAT))
    bonus = float(config.get("lap_bonus_max_pct", DEFAULT_LAP_BONUS_PCT))

    picked = pick_tracks(tracks, per_heat, rng)
    cars = pick_vehicles(vehicle_pool(config), len(picked), rng)
    rounds = []
    for i, t in enumerate(picked):
        car = cars[i] if i < len(cars) else {}
        rounds.append({
            "track": t.get("name", ""),
            "track_guid": t.get("guid", ""),
            "track_type": t.get("type", ""),
            "laps": laps_for(t, rng, bonus),
            "pit": bool(t.get("pit", False)),
            # One car per race, not per heat (André, 2026-08-11). It fits the
            # way a heat is built anyway: every event gets its own entry in the
            # session archive, so the car can change between them.
            "vehicle": car.get("name", ""),
            "vehicle_guid": car.get("guid", ""),
            "ai_lines": has_ai_line(ai_pairs, t.get("guid", ""),
                                    car.get("guid", "")),
            # Players default to a chase camera, which makes a top-down series
            # look wrong. Each track needs its own horizontal angle so the
            # circuit sits sensibly in frame; the session archive carries these
            # as the track's camera5.cam.
            "camera_settings": t.get("camera_settings")
            or config.get("camera_settings"),
            # Which track to borrow a camera from when this one has none.
            "camera_from": t.get("camera_from", ""),
        })
    first = rounds[0] if rounds else {}
    return {
        # The heat's first car. Only the fallback path without a session archive
        # uses this -- with an archive every round carries its own.
        "vehicle": first.get("vehicle", ""),
        "vehicle_guid": first.get("vehicle_guid", ""),
        "quali_laps": int(config.get("quali", {}).get("laps", 1)),
        "rounds": rounds,
    }


# --- scoring ---------------------------------------------------------------

def points_for(position, table):
    """Points for a finishing position (1-based); 0 beyond the table."""
    if not position or position < 1:
        return 0
    table = list(table or [])
    if position <= len(table):
        return int(table[position - 1])
    return 0


def score_results(rounds, quali_points=None, race_points=None):
    """Aggregate a heat into per-driver standings.

    `rounds` is a list of {"kind": "quali"|"race", "positions": {driver: pos}}.
    Drivers are identified by whatever key the caller uses -- Steam ID for
    humans, bot name for AI.

    Returns a list of dicts sorted by the final classification, each carrying the
    points and the position histogram used for the tie-break.
    """
    quali_points = DEFAULT_QUALI_POINTS if quali_points is None else quali_points
    race_points = DEFAULT_RACE_POINTS if race_points is None else race_points

    totals = {}
    for rnd in rounds:
        table = quali_points if rnd.get("kind") == "quali" else race_points
        for driver, pos in (rnd.get("positions") or {}).items():
            entry = totals.setdefault(driver, {
                "driver": driver, "points": 0, "positions": [], "starts": 0,
            })
            entry["points"] += points_for(pos, table)
            entry["starts"] += 1
            if pos:
                entry["positions"].append(int(pos))

    ranked = sorted(totals.values(), key=lambda e: _rank_key(e), reverse=True)
    for i, entry in enumerate(ranked, 1):
        entry["rank"] = i
    return ranked


def _rank_key(entry):
    """Sort key: points first, then the count-back over finishing positions.

    The count-back compares how often a driver finished first, then second, and
    so on -- the usual motorsport tie-break, and what McVizn asked for ("bessere
    erreichte Positionen"). Positions are capped at 20 (the grid size) so the key
    stays a fixed-length tuple that sorts correctly.
    """
    histogram = [0] * 20
    for pos in entry["positions"]:
        if 1 <= pos <= 20:
            histogram[pos - 1] += 1
    return (entry["points"], tuple(histogram))
