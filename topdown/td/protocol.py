"""Parsing of the TSU script-port line stream.

Everything the controller learns about the server arrives as plain text lines on
the script port. This module turns those lines into events; it holds no state and
talks to nothing, so it can be tested against recorded transcripts.

Verified against a live capture on 2026-07-31 (server build 1.07f):

    Script client connected.                       <- first line carries a UTF-8 BOM
    Player connected: [VSR] Dremet (Rubber Knight)
    **<[VSR] Dremet>** hi                          <- chat, note the asterisks
    Players (1):
     - [VSR] Dremet (76561197989276622)            <- reply to "/who /id"
    [VSR] Dremet disconnected.

Player names are decoration, never identity: they are user-chosen, changeable and
not unique (real servers have seen players literally named "Player 2"). Join and
chat lines carry no Steam ID, so the controller treats every name-bearing line as
a trigger to re-ask "/who /id", and only the reply establishes who is on track.
"""

import re

# --- event kinds -----------------------------------------------------------
JOIN = "join"
LEAVE = "leave"
CHAT = "chat"
WHO_HEADER = "who_header"
SPECTATOR_HEADER = "spectator_header"
WHO_ENTRY = "who_entry"
SPECTATE = "spectate"
UNSPECTATE = "unspectate"
RETIRED = "retired"
EVENT_UPCOMING = "event_upcoming"
EVENT_STARTED = "event_started"
EVENT_ENDED = "event_ended"
SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"

# The rank title the server appends to a joining player's name ("(Rubber Knight)").
# In the log file it is wrapped in a colour tag, on the script port it is not.
_TITLE = re.compile(r"\s*(?:<color=#[0-9a-fA-F]+>)?\([^()]*\)(?:</color>)?\s*$")
_COLOUR = re.compile(r"</?(?:color|mspace|noparse|pos|mark)(?:=[^>]*)?>")

_JOIN = re.compile(r"^Player connected:\s*(?P<name>.+?)\s*$")
_SPECTATOR = re.compile(r"^Spectator connected:\s*(?P<name>.+?)\s*$")
_LEAVE = re.compile(r"^(?P<name>.+?) disconnected\.\s*$")
# The game announces both directions of the spectator toggle. These are the only
# unambiguous evidence that a driver gave up a race they had started, so the
# stats ledger leans on them rather than on the 30s roster poll.
_SPECTATE = re.compile(r"^(?P<name>.+?) is now a spectator\.\s*$")
_UNSPECTATE = re.compile(r"^(?P<name>.+?) is no longer a spectator\.\s*$")
_RETIRED = re.compile(r"^(?P<name>.+?) retired\.\s*$")
# Chat on the script port is "**<name>** text"; the log file writes "<name> text".
_CHAT = re.compile(r"^(?:\*\*)?<(?P<name>.+?)>(?:\*\*)?\s?(?P<text>.*)$")
_WHO_HEADER = re.compile(r"^Players \((?P<count>\d+)\):\s*$")
# A "/who /id" reply lists racers first and, only when there are any, appends a
# second block of spectators. There is no "Spectators (0):" line.
_SPECTATOR_HEADER = re.compile(r"^Spectators \((?P<count>\d+)\):\s*$")
_WHO_ENTRY = re.compile(r"^\s*-\s*(?P<name>.+?)\s*\((?P<steam_id>\d{5,})\)\s*$")
# Entries in the spectator block carry this prefix; it is part of the name as
# the line arrives, so it has to come off before the name means anything.
_SPECTATOR_MARK = re.compile(r"^\(Spectator\)\s*")
_UPCOMING = re.compile(
    r"^Event (?P<index>\d+) / (?P<total>\d+) is about to start in (?P<track>.+?)\.\s*$"
)
# Only a handful of line kinds carry a timestamp; the rest arrive bare.
_STAMPED = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}): (?P<rest>.*)$"
)
_STATE = {
    "Event started.": EVENT_STARTED,
    "Event ended.": EVENT_ENDED,
    "Session started.": SESSION_STARTED,
    "Session ended.": SESSION_ENDED,
}

# The script port also emits structured markers that never reach the log file.
# These are the authoritative signals -- they arrive first and are unambiguous.
# Observed live on 2026-07-31; a marker line may carry trailing text, e.g.
# "#EventEnd #EventStats Event stats generated."
_MARKERS = {
    "#SessionInit": SESSION_STARTED,
    "#SessionEnd": SESSION_ENDED,
    "#EventInit": EVENT_UPCOMING,
    "#EventRunning": EVENT_STARTED,
    "#EventEnd": EVENT_ENDED,
}


def strip_tags(text):
    """Remove Unity rich-text tags the server sprinkles into names and messages."""
    return _COLOUR.sub("", text).strip()


def clean_name(raw):
    """Normalise a player name: drop rich-text tags and the trailing rank title.

    The title is only stripped when something is left over, so a player who is
    literally called "(Anonymous)" keeps their name instead of becoming "".
    """
    name = strip_tags(raw)
    without_title = _TITLE.sub("", name).strip()
    return without_title or name


def parse_line(line):
    """Turn one stream line into an event dict, or None if it carries no meaning.

    Returns dicts of the form {"kind": ..., ...}. Unknown lines are ignored on
    purpose: the stream also carries lap times, vote tallies and free-form server
    chatter that the controller has no business reacting to.
    """
    if not line:
        return None
    # The very first line of a connection is prefixed with a BOM.
    line = line.lstrip("﻿").rstrip("\r\n")
    if not line.strip():
        return None

    if line.startswith("#"):
        kind = _MARKERS.get(line.split(None, 1)[0])
        if kind == EVENT_UPCOMING:
            # Distinct from the "Event 1 / 4 is about to start" line, which
            # carries the track name; this one only marks the transition.
            return {"kind": kind, "index": None, "total": None, "track": None}
        return {"kind": kind, "ts": None} if kind else None

    stamped = _STAMPED.match(line)
    if stamped:
        rest = stamped.group("rest").strip()
        kind = _STATE.get(rest)
        if kind:
            return {"kind": kind, "ts": stamped.group("ts")}
        return None

    # The log file stamps these lines, the script port does not (observed
    # 2026-07-31: the controller sat through a whole heat without ever seeing an
    # event end, because it only recognised the stamped form). Accept both.
    kind = _STATE.get(line.strip())
    if kind:
        return {"kind": kind, "ts": None}

    m = _WHO_HEADER.match(line)
    if m:
        return {"kind": WHO_HEADER, "count": int(m.group("count"))}

    m = _SPECTATOR_HEADER.match(line)
    if m:
        return {"kind": SPECTATOR_HEADER, "count": int(m.group("count"))}

    m = _WHO_ENTRY.match(line)
    if m:
        raw_name = strip_tags(m.group("name"))
        spectator = bool(_SPECTATOR_MARK.match(raw_name))
        return {
            "kind": WHO_ENTRY,
            "name": clean_name(_SPECTATOR_MARK.sub("", raw_name)),
            "steam_id": int(m.group("steam_id")),
            "spectator": spectator,
        }

    m = _UPCOMING.match(line)
    if m:
        return {
            "kind": EVENT_UPCOMING,
            "index": int(m.group("index")),
            "total": int(m.group("total")),
            "track": strip_tags(m.group("track")),
        }

    # Chat is checked before join/leave: a chat message could otherwise contain
    # text that looks like one of those lines.
    m = _CHAT.match(line)
    if m:
        return {
            "kind": CHAT,
            "name": clean_name(m.group("name")),
            "text": strip_tags(m.group("text")),
        }

    m = _SPECTATE.match(line)
    if m:
        return {"kind": SPECTATE, "name": clean_name(m.group("name"))}

    m = _UNSPECTATE.match(line)
    if m:
        return {"kind": UNSPECTATE, "name": clean_name(m.group("name"))}

    m = _RETIRED.match(line)
    if m:
        return {"kind": RETIRED, "name": clean_name(m.group("name"))}

    m = _JOIN.match(line)
    if m:
        return {"kind": JOIN, "name": clean_name(m.group("name")), "spectator": False}

    m = _SPECTATOR.match(line)
    if m:
        return {"kind": JOIN, "name": clean_name(m.group("name")), "spectator": True}

    m = _LEAVE.match(line)
    if m:
        raw_name = strip_tags(m.group("name"))
        spectator = bool(_SPECTATOR_MARK.match(raw_name))
        return {
            "kind": LEAVE,
            "name": clean_name(_SPECTATOR_MARK.sub("", raw_name)),
            "spectator": spectator,
        }

    return None


# --- chat commands ---------------------------------------------------------

# TSU intercepts lines starting with "/" as console commands, so a player's
# "/bot 14" may never reach the chat stream at all. Both prefixes are therefore
# accepted; the live test decides which one players actually get to use.
_CMD = re.compile(r"^\s*[/!](?P<cmd>[a-zA-Z]+)(?P<args>(?:\s+\S+)*)\s*$")


def parse_command(text):
    """Parse a chat message into (command, [args]) or None.

    Case is normalised, so "/BOT 14" and "!bot 14" are the same command.
    """
    m = _CMD.match(text or "")
    if not m:
        return None
    return m.group("cmd").lower(), m.group("args").split()


def quoted(name):
    """Quote a track/vehicle name for a console command.

    TSU has no escaping, so a name containing both quote characters cannot be
    expressed at all -- that is a configuration error worth failing loudly on
    rather than silently sending a broken command.
    """
    if "'" not in name:
        return f"'{name}'"
    if '"' not in name:
        return f'"{name}"'
    raise ValueError(f"name contains both quote characters: {name!r}")
