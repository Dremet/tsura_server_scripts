"""Parser/writer for Turbo Sliders Unlimited vehicle files (.veh / properties.bin).

Reverse-engineered format (file FormatId 111, FormatVersion 6, creation-version 103
layout — the format written by current game builds).

File layout
===========
All values little-endian.

Header:
  0x00  u16  FormatId            = 111
  0x02  u16  FormatVersion       = 6
  0x04  u16  gameVersion         (writer's game data version, e.g. 106)
  0x06  u64  guid.a              (structured, validated by the game:
                                  ms-since-2020-01-01 << 18 | rand12 << 6 |
                                  tag; tag 0x0A = player guid, 0x0B = workshop
                                  guid; see make_guid_a())
  0x0E  u64  guid.b / makerId    (maker SteamID64 for player-made vehicles,
                                  workshop file id for workshop items; must
                                  match the guid.a tag)
  0x16  i64  creationTime        (.NET DateTime ticks)
  0x1E  u32  makerAccountId      (32-bit Steam account id of maker)
  0x22  u8   flag0               (always 0x01 observed)
  0x23  u8   flag1               (always 0x00 observed)
  0x24  u8   flag2               (always 0x10 observed)
  0x25  u8   flag3               (always 0x01 observed)
  0x26  u8   finalized           (1 = finalized/published, 0 = local WIP)
  0x27  u8   header bitmask + one byte per set bit
             (bit 5's value = game data version at creation time, e.g. 0x67=103;
              bit 3's value = 0x02 when present; meaning of others unknown,
              observed 0)

Strings (u32 length + UTF-8 bytes):
  name
  description
  [u32 modelId]      -- present in v103+ files (built-in body model index);
                        detected on read via string-length heuristic
  filenameWithoutExtension
  makerName

Then a sequence of *masked sections*. Each section is one byte: a presence
bitmask for up to 8 fields, followed by the values of the fields whose bit is
set, in bit order. Fields whose bit is clear take the game's default value.
Classes with more than 8 serialized fields use several consecutive masked
chunks (each chunk = mask byte + values).

Field value encodings:
  f    float32
  b    bool as 1 byte (0/1)
  u8   1 byte
  u16  2 bytes
  e32  int32 (enums)
  mb   boolean carried by the mask bit itself (no data bytes)

Mid-block sections (v103 layout):
  sec1 (unknown, observed empty)
  sec2 damage:   [maxHitPoints u16, ...]
  sec3 (unknown, observed empty)
  engine chunk1: [engineSound u16, pitch f, ? f, lowMax f, medMaxRel f,
                  highMax f, medExtra f, gasSpeed f]
  engine chunk2: [? f, gasOffPitch f, gasOffVolume f, pitchSpeed f, ...]
  gearRatios:    [ratio1 f .. ratio8 f]        (engine audio gear ratios)
  gearAudio2:    [gearAudio?, shiftUp f, shiftDown f, shiftDownIdle f, ...]

Physics block:
  u16 312 (CarPhysicsProperties.FormatId)
  u16 3   (CarPhysicsProperties.FormatVersion)
  masked sections:
    weight:         [mass f, massY f, massZ f, gravity f]
    speed:          [maxSpeed f, viscosity f, acceleration f,
                     engineFriction f, reverseMultiplier f, flyingViscosity f]
    braking:        [braking f, parkBraking f, parkSpeed f, lockingStartTime f,
                     complexLocking b, lockedBrakeMultiplier f,
                     cooldownMultiplier u8, lockedGripMultiplier f]
    steering:       [grip f, maxSteering f, changeSpeed f, changeReturnSpeed f,
                     neutralReturn f, changeReturnSpeedCounterSteering f,
                     changeReturnSpeedOnNeutral f, flyingSteering f]
    steering2:      [fullSteeringSpeed f, ...]
    oversteering:   [always f, sliding f, braking f, accelerating f]
    sliding:        [slidingAngle f, gradualRange f, gradualGrip b,
                     slideBraking f, slideDeceleration f, slideAcceleration f,
                     minSmokeAngle u8, minSmokeRange u8]
    spring:         [maxLength f, maxAcceleration f, damping f, backLength f,
                     backAcceleration f, backDamping f]
    downforce:      [downforce f, springAffectsGrip mb, springAffectsBraking mb,
                     maxSpringGs f, maxAccSpringGs f]
    weightTransfer: [turning f, braking f, accelerating f, viscosityReduction f]
    gears:          [gearCount? -- observed empty]
    contact:        [bounciness f, staticFriction f, dynamicFriction f,
                     bounceCombine e32, frictionCombine e32]
  5 trailing bytes (observed always 00) -- unknown empty sections
  u16 313 (CarPhysicsProperties.FormatIdEnd)

Game defaults (from IL2CPP metadata):
  mass=1000 massY=0 massZ=0 gravity=20 | maxSpeed=180 viscosity=0.75
  acceleration=1.0 engineFriction=0 reverseMultiplier=0.33 flyingViscosity=0.3
  braking=20 parkBraking=20 parkSpeed=2 lockingStartTime=0.5 complexLocking=F
  lockedBrakeMultiplier=1 cooldownMultiplier=2 lockedGripMultiplier=1
  grip=20 maxSteering=150 changeSpeed=2000 changeReturnSpeed=2000
  neutralReturn=1 flyingSteering=50 fullSteeringSpeed=10
  oversteering: always=30 sliding=0 braking=0 accelerating=0
  slidingAngle=22.5 gradualRange=0 slideBraking=10 slideAcceleration=1
  spring: maxLength=0.3 maxAcceleration=1 damping=0.2 back*=1
  downforce=0 maxSpringGs=0.5 maxAccSpringGs=0
  weightTransfer: all 0, viscosityReduction=0.5
  contact: bounciness=0.75 staticFriction=0.6 dynamicFriction=0.6
  damage: maxHitPoints=10000 | engine audio ratios: 2.5/1.6/1.25/0.975/0/0/0/0
"""
from __future__ import annotations

import io
import struct
import zipfile

TICKS_2020 = 637134336000000000  # .NET ticks of 2020-01-01, guid time epoch


def make_guid_a(creation_ticks: int, workshop: bool = False,
                rand12: int | None = None) -> int:
    """Build a valid vehicle guid 'a' component.

    Layout: (ms since 2020-01-01 UTC) << 18 | 12 random bits << 6 | type tag.
    Type tag: 0x0A when guid 'b' is a SteamID64 (player-made),
              0x0B when guid 'b' is a workshop file id.
    The game validates this structure; a random u64 is rejected on load.
    """
    import random as _random
    ms = (creation_ticks - TICKS_2020) // 10000
    if ms < 0:
        raise ValueError("creation time before 2020-01-01")
    if rand12 is None:
        rand12 = _random.getrandbits(12)
    return (ms << 18) | ((rand12 & 0xFFF) << 6) | (0x0B if workshop else 0x0A)


FORMAT_ID = 111
FORMAT_VERSION = 6
GAME_VERSION = 106          # header gameVersion written by current game
CREATION_VERSION = 103      # layout version this module reads/writes
PHYS_ID = 312
PHYS_VERSION = 3
PHYS_ID_END = 313

# ---------------------------------------------------------------- section specs

MID_SECTIONS = [
    ("sec1", [("u0", "u8"), ("u1", "u8"), ("u2", "u8"), ("u3", "u8"),
              ("u4", "u8"), ("u5", "u8"), ("u6", "u8"), ("u7", "u8")]),
    ("damage", [("maxHitPoints", "u16"), ("d1", "u8"), ("d2", "u8"), ("d3", "u8"),
                ("d4", "u8"), ("d5", "u8"), ("d6", "u8"), ("d7", "u8")]),
    ("sec3", [("u0", "u8"), ("u1", "u8"), ("u2", "u8"), ("u3", "u8"),
              ("u4", "u8"), ("u5", "u8"), ("u6", "u8"), ("u7", "u8")]),
    # engine audio chunk 1 (editor: Engine / Pitch / Channels / Low Max /
    # Med Max Rel / High Max / Med Extra)
    ("engine", [("engineSound", "u8"), ("pitch", "f"), ("channels", "f"),
                ("lowMax", "f"), ("medMaxRel", "f"), ("highMax", "f"),
                ("medExtra", "f")]),
    # engine audio chunk 2 (editor: Gas Speed / Only Gas On / Gas Off Pitch /
    # Gas Off Volume / (Pitch Speed) / Flying Pitch)
    ("engine2", [("gasSpeed", "f"), ("onlyGasOn", "b"), ("gasOffPitch", "f"),
                 ("gasOffVolume", "f"), ("pitchSpeed", "f"),
                 ("flyingPitch", "f")]),
    # gear audio chunk 1 (editor: Gear Audio checkbox / Shift Up / Shift Down /
    # Shift Down Idle)
    ("gearAudio", [("gearAudio", "b"), ("shiftUp", "f"), ("shiftDown", "f"),
                   ("shiftDownIdle", "f")]),
    # gear audio chunk 2: ratios 1..8
    ("gearRatios", [("ratio1", "f"), ("ratio2", "f"), ("ratio3", "f"),
                    ("ratio4", "f"), ("ratio5", "f"), ("ratio6", "f"),
                    ("ratio7", "f"), ("ratio8", "f")]),
    # trailing section, always empty so far (possibly Special: camber angles)
    ("special", [("s0", "f"), ("s1", "f"), ("s2", "f"), ("s3", "f"),
                 ("s4", "f"), ("s5", "f"), ("s6", "f"), ("s7", "f")]),
]

PHYS_SECTIONS = [
    ("weight", [("mass", "f"), ("massY", "f"), ("massZ", "f"), ("gravity", "f")]),
    # bit4 is not shown in the editor (deprecated engineFriction)
    ("speed", [("maxSpeed", "f"), ("viscosity", "f"), ("acceleration", "f"),
               ("reverseMultiplier", "f"), ("engineFriction", "f"),
               ("flyingViscosity", "f")]),
    ("braking", [("braking", "f"), ("parkBraking", "f"), ("parkSpeed", "f"),
                 ("lockingStartTime", "f"), ("complexLocking", "b"),
                 ("lockedBrakeMultiplier", "f"), ("cooldownMultiplier", "u8"),
                 ("lockedGripMultiplier", "f")]),
    # confirmed via editor: bit5..7 = Flying Steering, Flying Change Mult,
    # Neutral Return; bit4 not shown in editor (deprecated field)
    ("steering", [("grip", "f"), ("maxSteering", "f"), ("changeSpeed", "f"),
                  ("changeReturnSpeed", "f"), ("limitingMode", "f"),
                  ("flyingSteering", "f"), ("flyingChangeMult", "f"),
                  ("neutralReturn", "f")]),
    ("steering2", [("fullSteeringSpeed", "f"), ("s1", "f"), ("s2", "f"),
                   ("s3", "f"), ("s4", "f"), ("s5", "f"), ("s6", "f"),
                   ("s7", "f")]),
    ("oversteering", [("always", "f"), ("sliding", "f"), ("braking", "f"),
                      ("accelerating", "f")]),
    ("sliding", [("slidingAngle", "f"), ("gradualRange", "f"),
                 ("gradualGrip", "b"), ("slideBraking", "f"),
                 ("slideDeceleration", "f"), ("slideAcceleration", "f"),
                 ("minSmokeAngle", "u8"), ("minSmokeRange", "u8")]),
    ("spring", [("maxLength", "f"), ("maxAcceleration", "f"), ("damping", "f"),
                ("backLength", "f"), ("backAcceleration", "f"),
                ("backDamping", "f")]),
    ("downforce", [("downforce", "f"), ("springAffectsGrip", "mb"),
                   ("springAffectsBraking", "mb"), ("maxSpringGs", "f"),
                   ("maxAccSpringGs", "f")]),
    ("weightTransfer", [("turning", "f"), ("braking", "f"),
                        ("accelerating", "f"), ("viscosityReduction", "f")]),
    ("gears", [("gearCount", "e32"), ("x1", "u8"), ("x2", "u8"), ("x3", "u8"),
               ("x4", "u8"), ("x5", "u8"), ("x6", "u8"), ("x7", "u8")]),
    ("contact", [("bounciness", "f"), ("staticFriction", "f"),
                 ("dynamicFriction", "f"), ("bounceCombine", "e32"),
                 ("frictionCombine", "e32")]),
]

N_TRAILING = 5  # unknown empty section masks before the 0x0139 end marker

# Min/Max limits from the game's IL2CPP metadata constants (Min*/Max* fields).
# Only fields with known limits are listed; (min, max), None = unbounded side.
PHYS_RANGES = {
    "weight": {
        "mass": (1, 10000),
        "gravity": (0, 100),
    },
    "speed": {
        "maxSpeed": (1, 1000),
        "viscosity": (0.001, 10),
        "acceleration": (0.1, 10),
        "reverseMultiplier": (0.01, 4),
        "flyingViscosity": (0.001, None),
    },
    "braking": {
        "braking": (0, 1000),
    },
    "steering": {
        "grip": (0, 1000),
    },
    "oversteering": {
        "always": (-1000, 1000),
        "sliding": (-1000, 1000),
        "braking": (-1000, 1000),
        "accelerating": (-1000, 1000),
    },
    "sliding": {
        "slideBraking": (0, 1000),
    },
    "spring": {
        "maxLength": (None, 1.0),
        "backLength": (None, 5.0),
    },
}
MID_RANGES = {
    "damage": {
        "maxHitPoints": (500, 50000),
    },
}

# ---------------------------------------------------------------- enums / defaults
# Extracted from the game's IL2CPP metadata (see TOOLTIPS.md).

ENUMS = {
    "model": {  # TS.VehicleModelType — the "Model" dropdown / modelId u32
        "Sport1": 0, "Sport2": 1, "Civilian1": 2, "Sedan1": 3, "Drifter": 4,
        "Super1": 5, "Super2": 6, "HeavyFormula": 7, "Formula": 8,
        "Muscle1": 9, "Muscle2": 10, "Muscle3": 11, "Super3": 12,
        "Super4": 13, "Super5": 14, "Sport3": 15,
    },
    "engineSound": {  # TS.EngineSoundType — the "Engine" dropdown
        "None": 0, "I4_German_1": 1, "I4_German_2": 2, "I4_German_3": 3,
        "I4_Japanese": 4, "I4_Japanese_VTEC": 5, "I4_Serbian": 6,
        "Diesel_German": 7, "I6_German_1": 8, "I6_German_2": 9,
        "I6_German_M_1": 10, "I6_German_M_2": 11, "I6_German_M_3": 12,
        "I6_Japanese_1": 13, "I6_Japanese_2": 14, "Boxer_German": 15,
        "Boxer_Japanese_1": 16, "Boxer_Japanese_2": 17, "Rotary_X3": 18,
        "Rotary_X7": 19, "Rotary_X8F": 20, "Rotary_X8_1": 21,
        "Rotary_X8_2": 22, "Rotary_X8_3": 23, "Rotary_4_Rotor": 24,
        "V6_Japanese_1": 25, "V6_Japanese_2": 26,
        "V8_American_Classic_1": 27, "V8_American_Classic_2": 28,
        "V8_American_Modern_1": 29, "V8_American_Modern_2": 30,
        "V8_Italian_1": 31, "V8_Italian_2": 32, "V8_Formula_1": 33,
        "V8_Italian_F355": 34, "V8_German": 35, "V8_German_M_1": 36,
        "V8_German_M_2": 37, "V8_German_M_3": 38, "V10_German": 39,
        "V10_Italian": 40, "V12_British": 41, "V12_Italian": 42,
    },
    "channels": {  # EngineChannelMode
        "All": 0, "OnlyIdle": 1, "OnlyLow": 2, "OnlyMedium": 3, "OnlyHigh": 4,
    },
    "reverseSteering": {  # ReverseSteeringType
        "Realistic": 0, "Hovercraft": 1,
    },
    "combine": {  # PhysicMaterialCombine (bounceCombine / frictionCombine)
        "Average": 0, "Multiply": 1, "Minimum": 2, "Maximum": 3,
    },
}

# Tags: stored in the header bitmask section, bits 0-4.
# Unset bit = default (value 1: Common / Medium / EasySlider).
TAGS = {
    "style":        (0, {"Realistic": 0, "Common": 1, "Special": 2, "Crazy": 3}),
    "speed":        (1, {"LowSpeed": 0, "MediumSpeed": 1, "HighSpeed": 2}),
    "acceleration": (2, {"LowAccel": 0, "MediumAccel": 1, "HighAccel": 2}),
    "turning":      (3, {"QuickTurning": 0, "MediumTurning": 1, "SlowTurning": 2}),
    "sliding":      (4, {"AntiSlider": 0, "EasySlider": 1, "Slider": 2}),
}
TAG_DEFAULTS = {"style": 1, "speed": 1, "acceleration": 1, "turning": 1,
                "sliding": 1}
HEADER_VERSION_BIT = 5  # header mask bit 5 = game data version at creation

# Serialization defaults (game metadata Default* constants). A field omitted
# from the file takes this value.
PHYS_DEFAULTS = {
    "weight": {"mass": 1000.0, "massY": 0.0, "massZ": 0.0, "gravity": 20.0},
    "speed": {"maxSpeed": 180.0, "viscosity": 0.75, "acceleration": 1.0,
              "reverseMultiplier": 0.33, "engineFriction": 0.0,
              "flyingViscosity": 0.3},
    "braking": {"braking": 20.0, "parkBraking": 20.0, "parkSpeed": 2.0,
                "lockingStartTime": 0.5, "complexLocking": False,
                "lockedBrakeMultiplier": 1.0, "cooldownMultiplier": 2,
                "lockedGripMultiplier": 1.0},
    "steering": {"grip": 20.0, "maxSteering": 150.0, "changeSpeed": 2000.0,
                 "changeReturnSpeed": 2000.0, "limitingMode": 0.0,
                 "flyingSteering": 50.0, "flyingChangeMult": 0.2,
                 "neutralReturn": 1.0},
    "steering2": {"fullSteeringSpeed": 10.0},
    "oversteering": {"always": 30.0, "sliding": 0.0, "braking": 0.0,
                     "accelerating": 0.0},
    "sliding": {"slidingAngle": 22.5, "gradualRange": 0.0, "gradualGrip": True,
                "slideBraking": 10.0, "slideDeceleration": 0.0,
                "slideAcceleration": 1.0, "minSmokeAngle": 10,
                "minSmokeRange": 10},
    "spring": {"maxLength": 0.3, "maxAcceleration": 1.0, "damping": 0.2,
               "backLength": 1.0, "backAcceleration": 1.0, "backDamping": 1.0},
    "downforce": {"downforce": 0.0, "springAffectsGrip": False,
                  "springAffectsBraking": False, "maxSpringGs": 0.5,
                  "maxAccSpringGs": 0.0},
    "weightTransfer": {"turning": 0.0, "braking": 0.0, "accelerating": 0.0,
                       "viscosityReduction": 0.5},
    "gears": {"gearCount": 2},
    "contact": {"bounciness": 0.75, "staticFriction": 0.6,
                "dynamicFriction": 0.6, "bounceCombine": 0,
                "frictionCombine": 0},
}
MID_DEFAULTS = {
    "damage": {"maxHitPoints": 10000},
    "engine": {"engineSound": 31, "pitch": 1.0, "channels": 0, "lowMax": 0.3,
               "medMaxRel": 0.5, "highMax": 0.8, "medExtra": 0.2},
    "engine2": {"gasSpeed": 5.0, "onlyGasOn": False, "gasOffPitch": 0.9,
                "gasOffVolume": 0.75, "pitchSpeed": 2.0, "flyingPitch": 0.25},
    "gearAudio": {"gearAudio": True, "shiftUp": 0.9, "shiftDown": 0.8,
                  "shiftDownIdle": 0.6},
    "gearRatios": {"ratio1": 2.5, "ratio2": 1.6, "ratio3": 1.25,
                   "ratio4": 0.975, "ratio5": 0.0, "ratio6": 0.0,
                   "ratio7": 0.0, "ratio8": 0.0},
}


# string limits (game metadata: MaxNameLength / MaxDescriptionLength /
# MaxFilenameLength)
NAME_MAX = 20  # metadata says 40, but the game refuses to LOAD names > 20 (verified 2026-07-05)
DESCRIPTION_MAX = 256
FILENAME_MAX = 64
_FILENAME_BAD = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


def validate(d: dict) -> list[str]:
    """Return a list of range/type violations for a vehicle dict."""
    problems = []

    name = d.get("name", "")
    desc = d.get("description", "")
    fname = d.get("filename", "")
    if not isinstance(name, str) or not name.strip():
        problems.append("name: must be a non-empty string")
    elif len(name) > NAME_MAX:
        problems.append(f"name: {len(name)} chars, max {NAME_MAX}")
    if not isinstance(desc, str):
        problems.append("description: must be a string")
    elif len(desc) > DESCRIPTION_MAX:
        problems.append(f"description: {len(desc)} chars, max {DESCRIPTION_MAX}")
    if not isinstance(fname, str) or not fname.strip():
        problems.append("filename: must be a non-empty string")
    else:
        if len(fname) > FILENAME_MAX:
            problems.append(f"filename: {len(fname)} chars, max {FILENAME_MAX}")
        bad = sorted({c for c in fname if c in _FILENAME_BAD})
        if bad:
            problems.append(f"filename: illegal characters {bad}")
        if fname != fname.rstrip(". "):
            problems.append("filename: must not end with a dot or space")

    def check(kind, sections, specs, ranges):
        spec_map = dict(specs)
        for sec, vals in sections.items():
            spec = dict(spec_map.get(sec, []))
            for name, v in vals.items():
                typ = spec.get(name)
                if typ == "b" or typ == "mb":
                    if not isinstance(v, bool):
                        problems.append(f"{kind}.{sec}.{name}: expected bool, got {v!r}")
                    continue
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    problems.append(f"{kind}.{sec}.{name}: expected number, got {v!r}")
                    continue
                if typ == "u8" and not 0 <= v <= 255:
                    problems.append(f"{kind}.{sec}.{name}: {v} outside u8 range 0..255")
                if typ == "u16" and not 0 <= v <= 65535:
                    problems.append(f"{kind}.{sec}.{name}: {v} outside u16 range 0..65535")
                lo, hi = ranges.get(sec, {}).get(name, (None, None))
                if lo is not None and v < lo:
                    problems.append(f"{kind}.{sec}.{name}: {v} < min {lo}")
                if hi is not None and v > hi:
                    problems.append(f"{kind}.{sec}.{name}: {v} > max {hi}")

    check("physics", d.get("physics", {}), PHYS_SECTIONS, PHYS_RANGES)
    check("mid", d.get("mid", {}), MID_SECTIONS, MID_RANGES)
    return problems


class FormatError(Exception):
    pass


# ---------------------------------------------------------------- reader

class Reader:
    def __init__(self, data: bytes):
        self.b = data
        self.o = 0

    def take(self, n):
        if self.o + n > len(self.b):
            raise FormatError(f"EOF at offset {self.o}, wanted {n} bytes")
        v = self.b[self.o:self.o + n]
        self.o += n
        return v

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def string(self):
        n = self.u32()
        if n > 4096:
            raise FormatError(f"implausible string length {n} at {self.o - 4}")
        return self.take(n).decode("utf-8")

    def section(self, spec):
        """Read one masked section; returns dict of present fields."""
        mask = self.u8()
        out = {}
        for i, (name, typ) in enumerate(spec):
            if not (mask >> i) & 1:
                continue
            if typ == "f":
                out[name] = self.f32()
            elif typ == "b":
                v = self.u8()
                if v > 1:
                    raise FormatError(f"bool field {name} = {v} at {self.o - 1}")
                out[name] = bool(v)
            elif typ == "u8":
                out[name] = self.u8()
            elif typ == "u16":
                out[name] = self.u16()
            elif typ == "e32":
                out[name] = struct.unpack("<i", self.take(4))[0]
            elif typ == "mb":
                out[name] = True
            else:
                raise AssertionError(typ)
        if mask >> len(spec):
            raise FormatError(
                f"mask {mask:#04x} has bits beyond known {len(spec)} fields "
                f"at offset {self.o}")
        return out


def parse(data: bytes) -> dict:
    r = Reader(data)
    fmt, ver, gamever = r.u16(), r.u16(), r.u16()
    if fmt != FORMAT_ID:
        raise FormatError(f"bad FormatId {fmt}")
    if ver != FORMAT_VERSION:
        raise FormatError(f"unsupported FormatVersion {ver}")
    d = {
        "gameVersion": gamever,
        "guid": r.u64(),
        "makerId": r.u64(),
        "creationTicks": r.i64(),
        "makerAccountId": r.u32(),
        "flags": list(r.take(5)),
    }
    hmask = r.u8()
    hbytes = {}
    for i in range(8):
        if (hmask >> i) & 1:
            hbytes[i] = r.u8()
    d["headerMask"] = hmask
    d["headerBytes"] = hbytes
    creation_ver = hbytes.get(5, 0)
    d["creationVersion"] = creation_ver

    d["name"] = r.string()
    d["description"] = r.string()

    # optional modelId u32 (creation-version dependent); detect via heuristic
    d["modelId"] = None
    save = r.o
    peek = r.u32()
    nxt_len = struct.unpack_from("<I", r.b, r.o)[0]
    is_str_next = (
        0 < nxt_len <= 128 and r.o + 4 + nxt_len <= len(r.b)
        and all(32 <= c < 127 for c in r.b[r.o + 4:r.o + 4 + nxt_len]))
    if is_str_next and peek <= 0xFFFF:
        d["modelId"] = peek
    else:
        r.o = save

    d["filename"] = r.string()
    d["maker"] = r.string()

    mid = {}
    for name, spec in MID_SECTIONS:
        mid[name] = r.section(spec)
    d["mid"] = mid

    if r.u16() != PHYS_ID:
        raise FormatError(f"physics FormatId marker not found at {r.o - 2}")
    if r.u16() != PHYS_VERSION:
        raise FormatError("unsupported physics FormatVersion")
    phys = {}
    for name, spec in PHYS_SECTIONS:
        phys[name] = r.section(spec)
    d["physics"] = phys

    trailing = r.take(N_TRAILING)
    if trailing != b"\x00" * N_TRAILING:
        raise FormatError(f"unexpected trailing bytes {trailing.hex()}")
    if r.u16() != PHYS_ID_END:
        raise FormatError("physics end marker not found")
    if r.o != len(r.b):
        raise FormatError(f"{len(r.b) - r.o} unparsed bytes at end")
    return d


# ---------------------------------------------------------------- writer

class Writer:
    def __init__(self):
        self.buf = io.BytesIO()

    def raw(self, b):
        self.buf.write(b)

    def u8(self, v):
        self.raw(struct.pack("<B", v))

    def u16(self, v):
        self.raw(struct.pack("<H", v))

    def u32(self, v):
        self.raw(struct.pack("<I", v))

    def u64(self, v):
        self.raw(struct.pack("<Q", v))

    def i64(self, v):
        self.raw(struct.pack("<q", v))

    def f32(self, v):
        self.raw(struct.pack("<f", v))

    def string(self, s):
        b = s.encode("utf-8")
        self.u32(len(b))
        self.raw(b)

    def section(self, spec, values: dict):
        known = {n for n, _ in spec}
        unknown = set(values) - known
        if unknown:
            raise FormatError(f"unknown fields {unknown} for section {spec}")
        mask = 0
        for i, (name, typ) in enumerate(spec):
            if name in values and not (typ == "mb" and values[name] is False):
                mask |= 1 << i
        self.u8(mask)
        for i, (name, typ) in enumerate(spec):
            if not (mask >> i) & 1:
                continue
            v = values[name]
            if typ == "f":
                self.f32(v)
            elif typ == "b":
                self.u8(1 if v else 0)
            elif typ == "u8":
                self.u8(v)
            elif typ == "u16":
                self.u16(v)
            elif typ == "e32":
                self.raw(struct.pack("<i", v))
            elif typ == "mb":
                pass
            else:
                raise AssertionError(typ)


def write(d: dict) -> bytes:
    w = Writer()
    w.u16(FORMAT_ID)
    w.u16(FORMAT_VERSION)
    w.u16(d.get("gameVersion", GAME_VERSION))
    w.u64(d["guid"])
    w.u64(d.get("makerId", 0))
    w.i64(d["creationTicks"])
    w.u32(d.get("makerAccountId", 0))
    w.raw(bytes(d.get("flags", [1, 0, 0x10, 1, 0])))
    hmask = d.get("headerMask", 0x31)
    hbytes = d.get("headerBytes", {0: 0, 4: 0, 5: CREATION_VERSION})
    w.u8(hmask)
    for i in range(8):
        if (hmask >> i) & 1:
            w.u8(hbytes[i])
    w.string(d["name"])
    w.string(d["description"])
    if d.get("modelId") is not None:
        w.u32(d["modelId"])
    w.string(d["filename"])
    w.string(d["maker"])
    mid = d.get("mid", {})
    for name, spec in MID_SECTIONS:
        w.section(spec, mid.get(name, {}))
    w.u16(PHYS_ID)
    w.u16(PHYS_VERSION)
    phys = d.get("physics", {})
    for name, spec in PHYS_SECTIONS:
        w.section(spec, phys.get(name, {}))
    w.raw(b"\x00" * N_TRAILING)
    w.u16(PHYS_ID_END)
    return w.buf.getvalue()


# ---------------------------------------------------------------- .veh zip io

def read_veh(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        return parse(z.read("properties.bin"))


def write_veh(path: str, d: dict):
    data = write(d)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("properties.bin", data)
