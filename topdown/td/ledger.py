"""Append-only journal of everything that decides a player's race status.

Why this exists
---------------
TSU's own result files answer "who finished where", never "who was even allowed
to be in this race". A player who sat out a race as a spectator, one who dropped
and came back, and one who gave up look identical in `eventstats.json`. Those
distinctions only ever appear as text on the script port, and until now the
controller wrote that stream to a rotating log nobody parsed.

So this module records the *facts* -- who was on track when the event was armed,
who spectated, disconnected, reconnected or retired, and when -- as one JSON
object per line. It deliberately does **not** decide what any of it means: the
rules for "is this a DNF or a disconnect" belong in the pipeline, where they can
be re-run over an existing journal when McVizn refines them. Writing verdicts
here would freeze today's interpretation into the raw data.

Layout
------
One file per heat, `<heat_uid>.jsonl`, in a directory the pipeline reads on its
own schedule. Nothing hands the file over at a particular moment, which is the
point: the results hook and the controller are separate processes, and a journal
that had to be finished before `move_raw_files.sh` ran would be a race we cannot
win. A heat that dies without ever producing result files still leaves its
journal behind.

Every record carries the heat, the round and the phase it belongs to, so a line
means the same thing on its own as it does in sequence.

Failure policy
--------------
Statistics must never cost a heat. Every write is best-effort: if the directory
is unwritable or the disk is full, the failure is logged once and the controller
carries on racing.
"""

import json
import os
import time

# Record types. `roster` is a snapshot, the rest are transitions.
HEAT_START = "heat_start"
HEAT_END = "heat_end"
EVENT_INIT = "event_init"
EVENT_START = "event_start"
EVENT_END = "event_end"
ROSTER = "roster"
JOIN = "join"
LEAVE = "leave"
SPECTATE = "spectate"
UNSPECTATE = "unspectate"
RETIRED = "retired"

FORMAT_VERSION = 1


def heat_uid(heat_id, when=None):
    """A heat key that stays unique across controller restarts.

    `heat_id` alone is not enough: the counter in topdown_state.json has been
    reset before, so the test heats of 2026-07-31 carry ids (100+) that the live
    counter will reach again. Pairing the id with its start time settles it.
    """
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(when if when else time.time()))
    return f"{stamp}-{int(heat_id)}"


class Ledger:
    """Writes one heat's journal. One instance per heat; reused across events."""

    def __init__(self, directory, log=None, clock=time.time):
        self.directory = directory
        self.log = log or (lambda msg: None)
        self.clock = clock
        self.heat_id = None
        self.heat_uid = None
        self.round = None
        self.phase = None
        self.path = None
        self._broken = False

    # --- writing ----------------------------------------------------------

    def _write(self, record_type, **fields):
        if self.path is None or self._broken:
            return
        record = {
            "t": record_type,
            "ts": round(self.clock(), 3),
            "heat_id": self.heat_id,
            "heat_uid": self.heat_uid,
            "round": self.round,
            "phase": self.phase,
        }
        record.update(fields)
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError as exc:                              # noqa: BLE001
            # Once, not once per line: a full disk would otherwise flood the log.
            self._broken = True
            self.log(f"status ledger unwritable ({exc}) -- continuing without it")

    # --- heat lifecycle ---------------------------------------------------

    def start_heat(self, heat_id, rounds_total, uid=None):
        now = self.clock()
        self.heat_id = int(heat_id)
        self.heat_uid = uid or heat_uid(heat_id, now)
        self.round = None
        self.phase = None
        self._broken = False
        self.path = os.path.join(self.directory, f"{self.heat_uid}.jsonl")
        self._write(HEAT_START, rounds_total=rounds_total, format=FORMAT_VERSION)
        return self.heat_uid

    def end_heat(self, reason="finished"):
        self._write(HEAT_END, reason=reason)
        self.path = None

    # --- event lifecycle --------------------------------------------------

    def init_event(self, round_no, phase, track=None, track_guid=None,
                   vehicle=None, vehicle_guid=None, laps=None):
        """An event has been armed. Everything after this belongs to it."""
        self.round = round_no
        self.phase = phase
        self._write(EVENT_INIT, track=track, track_guid=track_guid,
                    vehicle=vehicle, vehicle_guid=vehicle_guid, laps=laps)

    def start_event(self):
        self._write(EVENT_START)

    def end_event(self):
        self._write(EVENT_END)

    # --- player transitions ----------------------------------------------

    def roster(self, racers, spectators, reason=None):
        """Snapshot of who is on track and who is watching.

        `racers` and `spectators` are {steam_id: name}. Taken on every "/who /id"
        reply, and deliberately again the moment an event is armed and started --
        those two snapshots are what decides who counts as a participant.
        """
        self._write(
            ROSTER,
            reason=reason,
            racers=[{"steam_id": sid, "name": name}
                    for sid, name in sorted(racers.items())],
            spectators=[{"steam_id": sid, "name": name}
                        for sid, name in sorted(spectators.items())],
        )

    def join(self, steam_id, name, spectator):
        self._write(JOIN, steam_id=steam_id, name=name, spectator=bool(spectator))

    def leave(self, steam_id, name, spectator=False):
        self._write(LEAVE, steam_id=steam_id, name=name, spectator=bool(spectator))

    def spectate(self, steam_id, name):
        self._write(SPECTATE, steam_id=steam_id, name=name)

    def unspectate(self, steam_id, name):
        self._write(UNSPECTATE, steam_id=steam_id, name=name)

    def retired(self, steam_id, name):
        self._write(RETIRED, steam_id=steam_id, name=name)
