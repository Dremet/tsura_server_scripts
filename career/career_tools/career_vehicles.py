"""Career per-driver vehicle generation.

Decoupled building block for the TSU Career mode: given a base Workshop car
(a .veh chosen per season) and a driver's *final* tuned physics values, produce
a per-driver .veh whose only differences from the base are the tunable
axes plus a per-driver identity (name / filename / maker steam-id -> unique guid).

The tier -> value mapping lives in the web/DB layer (season upgrade config);
this module only takes the resolved numeric values, so it stays independent of
the economy rules.

Requires tsu_veh.py + make_veh.py (the tsu_vehicle_tools repo) on sys.path.
"""
from __future__ import annotations

import os
import re
import sys

# tsu_vehicle_tools must be importable
import make_veh
import tsu_veh

# The tunable axes -> (physics section, field). Central mapping so the
# web UI, the DB and the generator all agree on what "Top Speed" etc. means.
TUNING_FIELDS = {
    "top_speed":             ("speed", "maxSpeed"),
    "acceleration":          ("speed", "engineFriction"),  # TSU editor "Acceleration" == .veh engineFriction
    "braking":               ("braking", "braking"),
    "downforce":             ("downforce", "downforce"),
    "grip":                  ("steering", "grip"),
    "sliding_gradual_range": ("sliding", "gradualRange"),
    "spring_max_length":     ("spring", "maxLength"),
    "locking_start_time":    ("braking", "lockingStartTime"),
    "oversteering_braking":  ("oversteering", "braking"),
}


def _sanitize_filename(s: str) -> str:
    """Filesystem- and game-safe (game rejects illegal fn chars); generated
    filenames must not contain spaces."""
    s = re.sub(r"[^A-Za-z0-9 _.\-]", "", s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:64] or "career_car"


def build_driver_vehicle(
    base_veh: str,
    out_path: str,
    *,
    display_name: str,
    steam_id64: int,
    tuned: dict,
    maker: str = "TSURA Career",
    description: str | None = None,
) -> dict:
    """Generate one driver's .veh from the season base car + tuned values.

    base_veh    path to the season's base Workshop .veh (or a dumped .json)
    out_path    where to write the .veh
    display_name in-game vehicle name (<=40 chars)
    steam_id64  driver's SteamID64 -> becomes the vehicle guid.b (unique per driver)
    tuned       {"top_speed": float, "acceleration": float,
                 "braking": float, "downforce": float}  (any subset; omitted
                 axes fall back to the base car's value)

    Returns the spec dict actually built (useful for logging / debugging).
    """
    physics: dict = {}
    for axis, value in tuned.items():
        if axis not in TUNING_FIELDS:
            raise ValueError(f"unknown tuning axis {axis!r}; "
                             f"valid: {', '.join(TUNING_FIELDS)}")
        if value is None:
            continue
        sec, field = TUNING_FIELDS[axis]
        physics.setdefault(sec, {})[field] = float(value)

    spec = {
        "template": base_veh,          # inherit everything from the base car
        "name": display_name[:40],
        "filename": _sanitize_filename(display_name),
        "maker": maker,
        "makerSteamId64": int(steam_id64),
        "finalized": True,
        "physics": physics,
    }
    if description is not None:
        spec["description"] = description[:256]

    d = make_veh.from_spec(spec)
    tsu_veh.validate(d)            # enforce the game's min/max before writing
    tsu_veh.write_veh(out_path, d)
    return spec


if __name__ == "__main__":
    # smoke test against the repo's example car
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(here, "claude_gt4_test.veh")
    out = os.path.join(here, "_career_driver_test.veh")
    spec = build_driver_vehicle(
        base, out,
        display_name="Career S1 Dremet",
        steam_id64=76561197960287930,
        tuned={"top_speed": 240.0, "acceleration": 1.4,
               "braking": 30.0, "downforce": 0.6},
        description="TSURA Career Season 1 car for Dremet.",
    )
    # round-trip: read it back and confirm the tuned fields landed
    back = make_veh.to_spec(tsu_veh.read_veh(out))
    print("wrote", out, os.path.getsize(out), "bytes")
    print("name:", back["name"], "| maker:", back["maker"])
    print("speed:", back["physics"].get("speed"))
    print("braking.braking:", back["physics"].get("braking", {}).get("braking"))
    print("downforce.downforce:", back["physics"].get("downforce", {}).get("downforce"))
