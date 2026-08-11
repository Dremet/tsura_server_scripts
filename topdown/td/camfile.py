"""Read and write TSU camera files (.cam) from session archives.

Format, per the serialisation code the game's developer supplied (2026-08-01):

    byte  0     format version (1)
    then three blocks, each starting with a bitmask byte where bit N says
    whether field N was written at all. A clear bit means "field has its default
    value" and nothing follows; a set bit means the value follows, little endian.
    Booleans never write a value -- the bit itself carries it.

This is why the files are so small (41 bytes) and why guessing at fixed offsets
failed: which fields are present varies per file.

`encode` is the inverse and reproduces every .cam McVizn has exported so far
byte for byte (verified over all 18 of them, 2026-08-11), so a camera can be
tweaked -- a zoom level, say -- without asking him to re-export the session.
"""

import os
import struct

# (name, kind, default). Order matters -- it is the serialisation order.
BLOCK1 = [
    ("cameraPosition", "enum", 1),        # CameraPositionMode.BehindVelocity
    ("followHistory", "float", 0.0),
    ("distance", "float", 30.0),
    ("verticalAngle", "float", 30.0),
    ("horizontalAngle", "float", 0.0),
    ("behindVelocitySpeed", "float", 20.0),
    ("smoothingTime", "float", 0.15),
    ("lookMode", "enum", 0),              # CameraLookMode.LookAtTarget
]
BLOCK2 = [
    ("rankLockedTarget", "bool", False),
    ("fov", "float", 45.0),
    ("targetYPosition", "float", 0.5),
    ("predictionTime", "float", 0.0),
    ("predictionSmoothTime", "float", 0.3),
    ("blockReactionTime", "float", 1.0),
    ("followSecondaryTargetAmount", "byte", 50),
    ("tracksideSwitchPhase", "int", 50),
]
BLOCK3 = [
    ("keepCloseInFreeCamera", "bool", False),
    ("tracksideInterval", "int", 600),
    ("tracksideCameraFixed", "bool", False),
]

# Written even when it still holds the default. Every exported file carries it,
# so leaving it out would produce a shorter file than the game ever writes.
ALWAYS_WRITTEN = {"tracksideInterval"}

CAMERA_POSITION_NAMES = [
    "FixedAngle", "BehindVelocity", "BehindForward", "AlignTarget",
    "Free", "PlayableArea", "FullPlayableArea", "Trackside",
]
LOOK_MODE_NAMES = ["LookAtTarget", "AlignTarget", "Free"]


def _read_block(data, offset, fields):
    """Read one selective block; returns (values, new offset)."""
    if offset >= len(data):
        return {f[0]: f[2] for f in fields}, offset
    mask = data[offset]
    offset += 1
    values = {}
    for bit, (name, kind, default) in enumerate(fields):
        if not (mask >> bit) & 1:
            values[name] = default
            continue
        if kind == "bool":
            # The bit is the value; nothing is written.
            values[name] = not default
        elif kind in ("enum", "byte"):
            values[name] = data[offset]
            offset += 1
        elif kind == "float":
            values[name] = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        elif kind == "int":
            values[name] = struct.unpack_from("<i", data, offset)[0]
            offset += 4
    return values, offset


def decode(data):
    """Decode a .cam file into a dict of camera properties."""
    if not data:
        raise ValueError("empty camera file")
    version = data[0]
    if version < 1:
        raise ValueError(f"unsupported camera file version {version}")
    offset = 1
    out = {}
    for fields in (BLOCK1, BLOCK2, BLOCK3):
        values, offset = _read_block(data, offset, fields)
        out.update(values)
    return out


def decode_file(path):
    with open(path, "rb") as fh:
        return decode(fh.read())


def _write_block(props, fields):
    """Write one selective block; returns the mask byte plus its payload."""
    mask = 0
    body = bytearray()
    for bit, (name, kind, default) in enumerate(fields):
        value = props.get(name, default)
        if kind == "bool":
            # The bit is the value; nothing is written.
            if bool(value) != bool(default):
                mask |= 1 << bit
            continue
        if value == default and name not in ALWAYS_WRITTEN:
            continue
        mask |= 1 << bit
        if kind in ("enum", "byte"):
            body.append(int(value) & 0xFF)
        elif kind == "float":
            body += struct.pack("<f", float(value))
        elif kind == "int":
            body += struct.pack("<i", int(value))
    return bytes([mask]) + bytes(body)


def encode(props):
    """Encode camera properties back into a .cam file. Inverse of `decode`."""
    out = bytearray([1])                       # format version
    for fields in (BLOCK1, BLOCK2, BLOCK3):
        out += _write_block(props, fields)
    return bytes(out)


def encode_file(path, props):
    """Write `props` to `path`, replacing it atomically."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(encode(props))
    os.replace(tmp, path)


def to_camera_json(props):
    """Map decoded properties onto the keys used in camera.json.

    The names line up one to one; enums are stored as their numeric value.
    """
    return dict(props)


def describe(props):
    """Human-readable summary, for logs and for sanity-checking a config."""
    pos = props.get("cameraPosition", 1)
    look = props.get("lookMode", 0)
    pos_name = CAMERA_POSITION_NAMES[pos] if 0 <= pos < len(CAMERA_POSITION_NAMES) else pos
    look_name = LOOK_MODE_NAMES[look] if 0 <= look < len(LOOK_MODE_NAMES) else look
    return (f"{pos_name}/{look_name} dist={props.get('distance'):.2f} "
            f"vert={props.get('verticalAngle'):.2f} "
            f"horz={props.get('horizontalAngle'):.2f} "
            f"fov={props.get('fov'):.2f}")
