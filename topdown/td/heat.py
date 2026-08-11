"""Heat composition and scoring.

A heat is four tracks, each run as a one-lap qualifying followed by a race, so
eight game events in total. This module decides what gets driven and how it is
scored. It is deliberately free of I/O and of wall-clock time: the caller passes
in a random source, so a heat can be replayed exactly in tests.

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
    chosen = []
    pool = list(usable)
    for _ in range(count):
        weights = [float(t.get("weight", 1)) for t in pool]
        pick = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def laps_for(track, rng, bonus_pct=DEFAULT_LAP_BONUS_PCT):
    """Lap count for one race: the configured base plus a random 0-`bonus_pct`%.

    McVizn asked for "10-20% more, but never fewer", so the bonus only ever
    rounds up: a 10-lap track runs 10 to 12 laps, never 9.
    """
    base = int(track.get("laps", 0) or 0)
    if base < 1:
        base = 1
    bonus = rng.uniform(0, max(0.0, bonus_pct) / 100.0)
    return base + int(base * bonus + 0.999) if bonus > 0 else base


def build_heat_plan(config, rng, ai_pairs=frozenset()):
    """Compose one heat: which tracks, how many laps, and whether bots can run.

    Returns a plain dict so it can be written to disk for the event-init hook
    and handed to the results layer unchanged.
    """
    tracks = config.get("tracks") or []
    vehicle = config.get("vehicle") or ""
    vehicle_guid = config.get("vehicle_guid") or ""
    per_heat = int(config.get("tracks_per_heat", DEFAULT_TRACKS_PER_HEAT))
    bonus = float(config.get("lap_bonus_max_pct", DEFAULT_LAP_BONUS_PCT))

    picked = pick_tracks(tracks, per_heat, rng)
    rounds = []
    for t in picked:
        rounds.append({
            "track": t.get("name", ""),
            "track_guid": t.get("guid", ""),
            "track_type": t.get("type", ""),
            "laps": laps_for(t, rng, bonus),
            "pit": bool(t.get("pit", False)),
            "ai_lines": has_ai_line(ai_pairs, t.get("guid", ""), vehicle_guid),
            # Players default to a chase camera, which makes a top-down series
            # look wrong. Each track needs its own horizontal angle so the
            # circuit sits sensibly in frame; the event-init hook writes these
            # into camera.json just before the track loads.
            "camera_settings": t.get("camera_settings")
            or config.get("camera_settings"),
        })
    return {
        "vehicle": vehicle,
        "vehicle_guid": vehicle_guid,
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
