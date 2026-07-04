"""CLI to inspect and generate Turbo Sliders Unlimited vehicle files (.veh).

Usage:
  python make_veh.py dump   <file.veh | properties.bin>      # print as JSON spec
  python make_veh.py build  <spec.json> [-o out.veh] [--install]
  python make_veh.py schema [-o schema.json]                 # full parameter schema

`schema` emits a machine-readable description of every tunable parameter:
type, serialization default, min/max limits, the game's official tooltip text,
and all dropdown/enum options — intended for driving a web UI (sliders,
dropdowns, hover help) that produces specs for `build`.

`dump` prints an existing vehicle as a JSON spec that `build` accepts, so the
easiest workflow is: dump a vehicle you like, tweak values, rebuild.

Spec format (all keys optional except name):
{
  "template": "path/to/donor.veh",     // start from an existing vehicle
  "name": "My Car",
  "description": "...",
  "maker": "YourName",
  "filename": "MyCar",                 // in-game file name (no extension)
  "makerSteamId64": 76561197989276622, // 0 = anonymous
  "finalized": false,                  // false = editable local vehicle
  "modelId": "Super3",                 // body model: name or number (see schema)
  "tags": {                            // dropdowns; name or number
    "style": "Realistic",              // Realistic/Common/Special/Crazy
    "speed": "HighSpeed",              // LowSpeed/MediumSpeed/HighSpeed
    "acceleration": "MediumAccel",     // LowAccel/MediumAccel/HighAccel
    "turning": "MediumTurning",        // QuickTurning/MediumTurning/SlowTurning
    "sliding": "AntiSlider"            // AntiSlider/EasySlider/Slider
  },
  "maxHitPoints": 10000,
  "engineSound": "V8_German",          // name or number (see schema)
  "gearRatios": [2.8, 2.0, 1.6, 1.3, 1.1, 1.0],   // audio gear ratios (max 8)
  "audioExtra": {                      // any other audio fields, e.g.
    "engine":    {"pitch": 1.0, "lowMax": 0.3},
    "engine2":   {"gasSpeed": 5.0},
    "gearAudio": {"shiftUp": 0.9, "shiftDown": 0.8, "shiftDownIdle": 0.6}
  },
  "physics": { "<section>": {"<field>": value, ...}, ... }   // see schema
}

Omitted fields use the game's serialization defaults (listed in the schema).
Values are validated against the game's min/max limits; build fails on
violations.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import zipfile

import tsu_veh

STEAM_ACCOUNT_BASE = 76561197960265728
VEHICLES_DIR = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\Turbo Sliders\Unlimited")

DOTNET_EPOCH_OFFSET = 62135596800  # seconds from 0001-01-01 to 1970-01-01

# fields that carry an enum (spec accepts name or number)
ENUM_FIELDS = {
    ("mid", "engine", "engineSound"): "engineSound",
    ("mid", "engine", "channels"): "channels",
    ("physics", "contact", "bounceCombine"): "combine",
    ("physics", "contact", "frictionCombine"): "combine",
}
# serialized fields hidden in the in-game editor (deprecated/disabled)
HIDDEN_FIELDS = {
    ("physics", "speed", "engineFriction"),
    ("physics", "sliding", "slideDeceleration"),
    ("physics", "steering", "limitingMode"),
}
# mapping (kind, section) -> metadata class for tooltip lookup
TOOLTIP_CLASS = {
    ("physics", "weight"): "WeightProperties",
    ("physics", "speed"): "SpeedProperties",
    ("physics", "braking"): "BrakingProperties",
    ("physics", "steering"): "SteeringProperties",
    ("physics", "steering2"): "SteeringProperties",
    ("physics", "oversteering"): "OversteeringProperties",
    ("physics", "sliding"): "SlidingProperties",
    ("physics", "spring"): "SpringProperties",
    ("physics", "downforce"): "DownforceProperties",
    ("physics", "weightTransfer"): "WeightTransferProperties",
    ("physics", "gears"): "GearProperties",
    ("physics", "contact"): "ContactProperties",
    ("mid", "damage"): "VehicleDamageProperties",
    ("mid", "engine"): "VehicleEngineAudioProperties",
    ("mid", "engine2"): "VehicleEngineAudioProperties",
    ("mid", "gearAudio"): "VehicleGearAudioProperties",
    ("mid", "gearRatios"): "VehicleGearAudioProperties",
}
TOOLTIP_FIELD_ALIAS = {
    ("speed", "engineFriction"): "deprecatedEngineFriction",
    ("sliding", "slideDeceleration"): "deprecatedSlideDeceleration",
    ("engine", "engineSound"): "engine",
}


def now_ticks() -> int:
    return int((time.time() + DOTNET_EPOCH_OFFSET) * 10_000_000)


def load_any(path: str) -> dict:
    if path.lower().endswith(".veh"):
        return tsu_veh.read_veh(path)
    return tsu_veh.parse(open(path, "rb").read())


def resolve_enum(enum_name: str, value, context: str):
    """Accept an enum member name or numeric value; return the number."""
    table = tsu_veh.ENUMS[enum_name] if enum_name in tsu_veh.ENUMS else None
    if table is None:
        raise SystemExit(f"internal: unknown enum {enum_name}")
    if isinstance(value, str):
        if value not in table:
            raise SystemExit(f"{context}: unknown value {value!r}; "
                             f"valid: {', '.join(table)}")
        return table[value]
    if value not in table.values():
        raise SystemExit(f"{context}: {value} is not a valid {enum_name} value "
                         f"(valid: {sorted(table.values())})")
    return value


def enum_name_of(enum_name: str, value):
    for k, v in tsu_veh.ENUMS[enum_name].items():
        if v == value:
            return k
    return value


# ---------------------------------------------------------------- dump

def to_spec(d: dict) -> dict:
    """Convert a parsed vehicle into the friendlier spec shape."""
    mid = d["mid"]
    spec = {
        "name": d["name"],
        "description": d["description"],
        "maker": d["maker"],
        "filename": d["filename"],
        "makerSteamId64": d["makerId"],
        "finalized": bool(d["flags"][4]),
        "modelId": enum_name_of("model", d["modelId"])
                   if d["modelId"] is not None else None,
        "gameVersion": d["gameVersion"],
        "creationVersion": d["creationVersion"],
    }
    tags = {}
    for tag, (bit, options) in tsu_veh.TAGS.items():
        raw = d["headerBytes"].get(bit, tsu_veh.TAG_DEFAULTS[tag])
        name = next((k for k, v in options.items() if v == raw), raw)
        tags[tag] = name
    spec["tags"] = tags
    if "maxHitPoints" in mid.get("damage", {}):
        spec["maxHitPoints"] = mid["damage"]["maxHitPoints"]
    if "engineSound" in mid.get("engine", {}):
        spec["engineSound"] = enum_name_of("engineSound",
                                           mid["engine"]["engineSound"])
    ratios = mid.get("gearRatios", {})
    if ratios:
        spec["gearRatios"] = [ratios.get(f"ratio{i}", 0.0) for i in
                              range(1, 1 + max(int(k[5:]) for k in ratios))]
    extra = {}
    for sec in ("sec1", "sec3", "engine", "engine2", "gearAudio", "special",
                "damage"):
        v = {k: val for k, val in mid.get(sec, {}).items()
             if not (sec == "engine" and k == "engineSound")
             and not (sec == "damage" and k == "maxHitPoints")}
        if v:
            extra[sec] = v
    if extra:
        spec["audioExtra"] = extra
    spec["physics"] = {name: vals for name, vals in d["physics"].items() if vals}
    return spec


# ---------------------------------------------------------------- build

def from_spec(spec: dict) -> dict:
    if "template" in spec:
        d = load_any(spec["template"])
    else:
        d = {
            "gameVersion": tsu_veh.GAME_VERSION,
            "guid": 0,
            "makerId": 0,
            "creationTicks": 0,
            "makerAccountId": 0,
            "flags": [1, 0, 0x10, 1, 0],
            "headerMask": 1 << tsu_veh.HEADER_VERSION_BIT,
            "headerBytes": {tsu_veh.HEADER_VERSION_BIT: tsu_veh.CREATION_VERSION},
            "name": "",
            "description": "",
            "modelId": tsu_veh.ENUMS["model"]["Super3"],
            "filename": "",
            "maker": "",
            "mid": {},
            "physics": {},
        }
    # fresh identity for every build
    d["creationTicks"] = now_ticks()
    if "makerSteamId64" in spec:
        sid = spec["makerSteamId64"]
        d["makerId"] = sid
        d["makerAccountId"] = (sid - STEAM_ACCOUNT_BASE) if sid > STEAM_ACCOUNT_BASE else sid
    # guid.a must encode creation time + owner type or the game rejects the file
    d["guid"] = tsu_veh.make_guid_a(
        d["creationTicks"],
        workshop=0 < d.get("makerId", 0) < STEAM_ACCOUNT_BASE)
    if "name" not in spec:
        raise SystemExit("spec must contain at least a name")
    d["name"] = spec["name"]
    d["description"] = spec.get("description", d.get("description", ""))
    d["maker"] = spec.get("maker", d.get("maker", ""))
    d["filename"] = spec.get("filename", d["name"])
    if "modelId" in spec:
        d["modelId"] = resolve_enum("model", spec["modelId"], "modelId")
    if "finalized" in spec:
        d["flags"][4] = 1 if spec["finalized"] else 0

    # tags -> header bitmask bytes (bit set = explicit value stored)
    for tag, value in spec.get("tags", {}).items():
        if tag not in tsu_veh.TAGS:
            raise SystemExit(f"unknown tag {tag!r}; valid: "
                             f"{', '.join(tsu_veh.TAGS)}")
        bit, options = tsu_veh.TAGS[tag]
        if isinstance(value, str):
            if value not in options:
                raise SystemExit(f"tags.{tag}: unknown value {value!r}; "
                                 f"valid: {', '.join(options)}")
            value = options[value]
        elif value not in options.values():
            raise SystemExit(f"tags.{tag}: {value} invalid; "
                             f"valid: {sorted(options.values())}")
        d["headerMask"] |= 1 << bit
        d["headerBytes"][bit] = value

    mid = d.setdefault("mid", {})
    if "maxHitPoints" in spec:
        mid.setdefault("damage", {})["maxHitPoints"] = spec["maxHitPoints"]
    if "engineSound" in spec:
        mid.setdefault("engine", {})["engineSound"] = \
            resolve_enum("engineSound", spec["engineSound"], "engineSound")
    if "gearRatios" in spec:
        ratios = spec["gearRatios"]
        if len(ratios) > 8:
            raise SystemExit("at most 8 gear ratios")
        mid["gearRatios"] = {f"ratio{i+1}": float(v)
                             for i, v in enumerate(ratios) if v}
    known_mid = dict(tsu_veh.MID_SECTIONS)
    for sec, vals in spec.get("audioExtra", {}).items():
        if sec not in known_mid:
            raise SystemExit(f"unknown audioExtra section {sec!r}")
        for f, v in vals.items():
            key = ("mid", sec, f)
            if key in ENUM_FIELDS:
                vals = dict(vals)
                vals[f] = resolve_enum(ENUM_FIELDS[key], v, f"audioExtra.{sec}.{f}")
        mid.setdefault(sec, {}).update(vals)

    phys = d.setdefault("physics", {})
    known = dict(tsu_veh.PHYS_SECTIONS)
    for sec, vals in spec.get("physics", {}).items():
        if sec not in known:
            raise SystemExit(f"unknown physics section {sec!r}; "
                             f"valid: {', '.join(known)}")
        fields = {n for n, _ in known[sec]}
        bad = set(vals) - fields
        if bad:
            raise SystemExit(f"unknown fields in physics.{sec}: {sorted(bad)}; "
                             f"valid: {sorted(fields)}")
        resolved = {}
        for f, v in vals.items():
            key = ("physics", sec, f)
            if key in ENUM_FIELDS:
                v = resolve_enum(ENUM_FIELDS[key], v, f"physics.{sec}.{f}")
            resolved[f] = v
        phys.setdefault(sec, {}).update(resolved)
    return d


# ---------------------------------------------------------------- schema

def build_schema() -> dict:
    """Full parameter schema for UI generation (web tuning frontend)."""
    tooltips = {}
    tt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "tooltips.json")
    if os.path.exists(tt_path):
        tooltips = json.load(open(tt_path, encoding="utf-8"))

    def desc_for(kind, sec, field):
        cls = TOOLTIP_CLASS.get((kind, sec))
        if not cls:
            return None
        fname = TOOLTIP_FIELD_ALIAS.get((sec, field), field)
        strs = tooltips.get(cls, {}).get(fname)
        if not strs:
            return None
        return " ".join(" ".join(s.split()) for s in strs)

    def sections(kind, specs, defaults, ranges):
        out = {}
        for sec, fields in specs:
            if kind == "mid" and sec in ("sec1", "sec3", "special"):
                continue  # unknown/unused sections
            sec_out = {}
            for name, typ in fields:
                info = {"type": {"f": "float", "b": "bool", "mb": "bool",
                                 "u8": "int", "u16": "int",
                                 "e32": "int"}[typ]}
                dflt = defaults.get(sec, {}).get(name)
                if dflt is not None:
                    info["default"] = dflt
                lo, hi = ranges.get(sec, {}).get(name, (None, None))
                if lo is not None:
                    info["min"] = lo
                if hi is not None:
                    info["max"] = hi
                if typ == "u8":
                    info.setdefault("min", 0); info.setdefault("max", 255)
                if typ == "u16":
                    info.setdefault("min", 0); info.setdefault("max", 65535)
                enum = ENUM_FIELDS.get((kind, sec, name))
                if enum:
                    info["type"] = "enum"
                    info["options"] = tsu_veh.ENUMS[enum]
                d = desc_for(kind, sec, name)
                if d:
                    info["description"] = d
                if (kind, sec, name) in HIDDEN_FIELDS or name.startswith(("s", "x")) and name[1:].isdigit():
                    info["hidden"] = True
                sec_out[name] = info
            if sec_out:
                out[sec] = sec_out
        return out

    return {
        "formatVersion": {"formatId": tsu_veh.FORMAT_ID,
                          "formatVersion": tsu_veh.FORMAT_VERSION,
                          "gameVersion": tsu_veh.GAME_VERSION},
        "vehicle": {
            "name": {"type": "string", "maxLength": 40},
            "description": {"type": "string", "maxLength": 256},
            "maker": {"type": "string"},
            "filename": {"type": "string", "maxLength": 64},
            "makerSteamId64": {"type": "int"},
            "finalized": {"type": "bool", "default": False},
            "modelId": {"type": "enum", "options": tsu_veh.ENUMS["model"],
                        "default": "Super3",
                        "description": "Built-in body model."},
            "engineSound": {"type": "enum",
                            "options": tsu_veh.ENUMS["engineSound"],
                            "default": "V8_Italian_1",
                            "description": "Built-in engine sound sample."},
            "maxHitPoints": {"type": "int", "default": 10000, "min": 500,
                             "max": 50000,
                             "description": desc_for("mid", "damage",
                                                     "maxHitPoints")},
            "gearRatios": {"type": "float[]", "maxItems": 8,
                           "default": [2.5, 1.6, 1.25, 0.975],
                           "description": "Audio gear ratios (cosmetic; "
                                          "defines shift points of the engine "
                                          "sound)."},
        },
        "tags": {
            tag: {"type": "enum", "options": options,
                  "default": next(k for k, v in options.items()
                                  if v == tsu_veh.TAG_DEFAULTS[tag])}
            for tag, (bit, options) in tsu_veh.TAGS.items()
        },
        "physics": sections("physics", tsu_veh.PHYS_SECTIONS,
                            tsu_veh.PHYS_DEFAULTS, tsu_veh.PHYS_RANGES),
        "audio": sections("mid", tsu_veh.MID_SECTIONS,
                          tsu_veh.MID_DEFAULTS, tsu_veh.MID_RANGES),
    }


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_dump = sub.add_parser("dump", help="print a vehicle as a JSON spec")
    p_dump.add_argument("file")
    p_build = sub.add_parser("build", help="build a .veh from a JSON spec")
    p_build.add_argument("spec")
    p_build.add_argument("-o", "--output", help="output .veh path")
    p_build.add_argument("--install", action="store_true",
                         help="copy into the game's local Vehicles folder")
    p_schema = sub.add_parser("schema",
                              help="print the full parameter schema as JSON")
    p_schema.add_argument("-o", "--output", help="write to file instead")
    args = ap.parse_args()

    if args.cmd == "dump":
        d = load_any(args.file)
        print(json.dumps(to_spec(d), indent=2))
        return

    if args.cmd == "schema":
        s = json.dumps(build_schema(), indent=2, ensure_ascii=False)
        if args.output:
            open(args.output, "w", encoding="utf-8").write(s + "\n")
            print(f"wrote {args.output}")
        else:
            print(s)
        return

    spec = json.load(open(args.spec, encoding="utf-8"))
    d = from_spec(spec)
    problems = tsu_veh.validate(d)
    if problems:
        print("spec validation failed:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        raise SystemExit(1)
    out = args.output or (d["filename"] + ".veh")
    tsu_veh.write_veh(out, d)
    print(f"wrote {out} ({os.path.getsize(out)} bytes)")

    if args.install:
        base = VEHICLES_DIR
        profiles = [p for p in os.listdir(base)
                    if os.path.isdir(os.path.join(base, p, "Vehicles"))]
        if not profiles:
            raise SystemExit("no TSU profile with a Vehicles folder found")
        for prof in profiles:
            dst = os.path.join(base, prof, "Vehicles",
                               os.path.basename(out))
            with open(out, "rb") as f_in, open(dst, "wb") as f_out:
                f_out.write(f_in.read())
            print(f"installed -> {dst}")


if __name__ == "__main__":
    main()
