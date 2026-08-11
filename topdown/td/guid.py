"""TSU content GUIDs: the printed string and the two numbers behind it.

A level or a vehicle carries its identity inside the session files as
`{"a": <int64>, "b": <int32>}`, while everywhere else -- the AI line file names,
the web config, the track listing -- the same identity appears as
`139k2kmmzws3-33vswqr`. The two halves are `a` and `b` written in base32 over an
alphabet that leaves out the letters which read like digits (i, o, u, y).

Cracked on 2026-08-11 and verified against every level and vehicle known at the
time. It is what makes a car pool possible: the controller has to write the
chosen car's `m_guid` into each event's vehicles.json, and all the config knows
is the string.
"""

ALPHABET = "0123456789abcdefghjklmnpqrstvwxz"
_VALUES = {ch: i for i, ch in enumerate(ALPHABET)}


def decode_part(text):
    """One half of a GUID string as an integer."""
    text = str(text).strip().lower()
    if not text:
        raise ValueError("empty guid part")
    value = 0
    for ch in text:
        if ch not in _VALUES:
            raise ValueError(f"{ch!r} is not a guid character")
        value = value * 32 + _VALUES[ch]
    return value


def encode_part(value):
    """Inverse of `decode_part`."""
    value = int(value)
    if value < 0:
        raise ValueError("guid numbers are never negative")
    if value == 0:
        return "0"
    out = []
    while value:
        value, rest = divmod(value, 32)
        out.append(ALPHABET[rest])
    return "".join(reversed(out))


def decode(text):
    """`"139k2kmmzws3-33vswqr"` -> `(a, b)`."""
    parts = str(text).strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"not a guid: {text!r}")
    return decode_part(parts[0]), decode_part(parts[1])


def encode(a, b):
    """`(a, b)` -> `"139k2kmmzws3-33vswqr"`."""
    return f"{encode_part(a)}-{encode_part(b)}"


def to_doc(text):
    """The `{"a": ..., "b": ...}` form the session files use."""
    a, b = decode(text)
    return {"a": a, "b": b}


def from_doc(doc):
    """The printed form of a `{"a": ..., "b": ...}` block."""
    return encode(doc["a"], doc["b"])
