"""Status ledger tests: the transcripts are McVizn's cases, line by line.

Each scenario below is fed to the controller as raw script-port lines, exactly as
the server would send them, and then the journal is read back. The point is not
that the ledger reaches a verdict -- it deliberately does not -- but that the
facts a verdict needs are all present and attributed to the right race.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from td import ledger as ledger_mod  # noqa: E402

MCVIZN = 76561198131829686
FROZENI = 76561197989276622


def make_controller(tmpdir):
    """A controller with no socket, writing its journal into tmpdir."""
    import topdown_controller as tc

    ctl = tc.Controller.__new__(tc.Controller)
    ctl.dry_run = True
    ctl.sock = None
    ctl.buffer = b""
    ctl.config = dict(tc.DEFAULT_CONFIG)
    ctl.sent = []
    ctl.send = ctl.sent.extend
    ctl.ledger = ledger_mod.Ledger(tmpdir)
    ctl.who_expect = None
    ctl.who_buffer = {}
    ctl.spectator_expect = None
    ctl.spectator_buffer = {}
    ctl.who_settle_at = 0.0
    ctl.who_asked_at = 0.0
    ctl.last_who = 0.0
    ctl.who_reason = None
    ctl.spectators = {}

    class FakeMachine:
        """Only the parts the ledger path touches."""
        def __init__(self):
            self.humans = {}
            self.events_done = 0
            self.plan = {"rounds": [
                {"track": "E.V.M.C. V1", "track_guid": "11kcwn867t23-329n370",
                 "vehicle": "VoZzer", "vehicle_guid": "17xxzrmve5gb-3868ch8",
                 "laps": 3},
                {"track": "Jonno Island v1.0", "track_guid": "139k2kmmzws3-33vswqr",
                 "vehicle": "McTopper v1", "vehicle_guid": "128pn7m9fecb-32z2vmh",
                 "laps": 8},
            ]}

        def set_players(self, roster, now):
            self.humans = dict(roster)
            return []

        def on_event_ended(self, now):
            self.events_done += 1
            return []

        def on_session_started(self, now):
            return []

        def on_session_ended(self, now):
            return []

        def on_chat(self, *a):
            return []

    ctl.machine = FakeMachine()
    return ctl


def feed(ctl, lines, now=1000.0):
    """Play lines through the controller, one tick each."""
    for i, line in enumerate(lines):
        ctl.handle(line, now + i)
        # Stand in for the main loop's settle check: a reply with no spectator
        # block is only complete once nothing more has arrived.
        if ctl.who_settle_at and (now + i) >= ctl.who_settle_at:
            ctl.finish_who(now + i)
    if ctl.who_settle_at:
        ctl.finish_who(now + len(lines))


def read_journal(tmpdir):
    files = [f for f in os.listdir(tmpdir) if f.endswith(".jsonl")]
    assert len(files) == 1, f"expected one journal, got {files}"
    with open(os.path.join(tmpdir, files[0]), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def kinds(records, *types):
    return [r for r in records if r["t"] in types]


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctl = make_controller(self.tmp)
        self.ctl.ledger.start_heat(80, 2)

    def records(self):
        return read_journal(self.tmp)

    def last_roster(self, reason):
        found = [r for r in self.records()
                 if r["t"] == ledger_mod.ROSTER and r.get("reason") == reason]
        self.assertTrue(found, f"no roster snapshot for {reason!r}")
        return found[-1]


class TestRosterCapture(LedgerCase):
    def test_spectators_are_recorded_but_kept_out_of_the_lobby(self):
        """§4.1: a spectator is not a participant -- and must not start a heat."""
        feed(self.ctl, [
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
        ])
        snap = self.last_roster(None)
        self.assertEqual([p["steam_id"] for p in snap["racers"]], [FROZENI])
        self.assertEqual([p["steam_id"] for p in snap["spectators"]], [MCVIZN])
        # The matchmaking still only ever sees racers.
        self.assertEqual(set(self.ctl.machine.humans), {FROZENI})

    def test_reply_without_a_spectator_block_still_completes(self):
        """The server never sends "Spectators (0):", so nothing marks the end."""
        feed(self.ctl, [
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
        ])
        snap = self.last_roster(None)
        self.assertEqual(snap["spectators"], [])

    def test_empty_lobby_with_a_watcher(self):
        feed(self.ctl, [
            "Players (0):",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
        ])
        snap = self.last_roster(None)
        self.assertEqual(snap["racers"], [])
        self.assertEqual([p["steam_id"] for p in snap["spectators"]], [MCVIZN])

    def test_a_stale_spectator_does_not_leak_into_the_next_reply(self):
        feed(self.ctl, [
            "Players (0):",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
        ])
        feed(self.ctl, [
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
        ], now=2000.0)
        snap = self.last_roster(None)
        self.assertEqual([p["steam_id"] for p in snap["racers"]], [FROZENI])
        self.assertEqual(snap["spectators"], [])


class TestRaceInitSnapshot(LedgerCase):
    def test_status_at_race_init_and_start_is_captured(self):
        """§4: participation is decided at race init/start, so both are snapped."""
        feed(self.ctl, [
            "#EventInit",
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
            "#EventRunning",
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
        ])
        for reason in ("event_init", "event_start"):
            snap = self.last_roster(reason)
            self.assertEqual([p["steam_id"] for p in snap["racers"]], [FROZENI])
            self.assertEqual([p["steam_id"] for p in snap["spectators"]], [MCVIZN])

    def test_the_prose_line_does_not_open_a_second_event(self):
        """Both "Event 1 / 4 …" and "#EventInit" announce the same event."""
        feed(self.ctl, [
            "Event 1 / 4 is about to start in E.V.M.C. V1.",
            "#EventInit",
        ])
        self.assertEqual(len(kinds(self.records(), ledger_mod.EVENT_INIT)), 1)

    def test_round_and_phase_follow_the_quali_race_cursor(self):
        """A round is a qualifying and then a race; the journal says which."""
        seen = []
        for _ in range(4):
            feed(self.ctl, ["#EventInit"])
            feed(self.ctl, ["#EventEnd"])
        for rec in kinds(self.records(), ledger_mod.EVENT_INIT):
            seen.append((rec["round"], rec["phase"]))
        self.assertEqual(seen, [(1, "quali"), (1, "race"),
                                (2, "quali"), (2, "race")])

    def test_event_init_carries_the_track_and_car_of_that_round(self):
        feed(self.ctl, ["#EventInit"])
        rec = kinds(self.records(), ledger_mod.EVENT_INIT)[0]
        self.assertEqual(rec["track"], "E.V.M.C. V1")
        self.assertEqual(rec["vehicle"], "VoZzer")
        self.assertEqual(rec["laps"], 3)


class TestStatusTransitions(LedgerCase):
    def arm_race(self):
        """Frozeni starts the race as a racer."""
        feed(self.ctl, [
            "#EventInit",
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
            "#EventRunning",
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
        ])

    def test_player_to_spectator_is_recorded(self):
        """§4.4: the evidence for a DNF is this line, not a lap count."""
        self.arm_race()
        feed(self.ctl, ["[SR] Frozeni is now a spectator."], now=1100.0)
        rec = kinds(self.records(), ledger_mod.SPECTATE)
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["steam_id"], FROZENI)
        self.assertEqual(rec[0]["round"], 1)
        self.assertEqual(rec[0]["phase"], "quali")

    def test_unspectate_is_recorded_as_its_own_fact(self):
        """§4.4: it must not erase the spectator switch that came before it."""
        self.arm_race()
        feed(self.ctl, [
            "[SR] Frozeni is now a spectator.",
            "Players (0):",
            "Spectators (1):",
            " - (Spectator) [SR] Frozeni (76561197989276622)",
            "[SR] Frozeni is no longer a spectator.",
        ], now=1100.0)
        seq = [r["t"] for r in kinds(self.records(),
                                     ledger_mod.SPECTATE, ledger_mod.UNSPECTATE)]
        self.assertEqual(seq, [ledger_mod.SPECTATE, ledger_mod.UNSPECTATE])

    def test_unspectate_is_attributed_even_though_only_spectators_know_the_name(self):
        """The machine's roster has no spectators, so the lookup must not stop there."""
        feed(self.ctl, [
            "Players (0):",
            "Spectators (1):",
            " - (Spectator) [VSR] McVizn (76561198131829686)",
        ])
        feed(self.ctl, ["[VSR] McVizn is no longer a spectator."], now=1100.0)
        rec = kinds(self.records(), ledger_mod.UNSPECTATE)[0]
        self.assertEqual(rec["steam_id"], MCVIZN)

    def test_retired_is_recorded(self):
        """§3: an explicit give-up outranks every lap-count guess."""
        self.arm_race()
        feed(self.ctl, ["[SR] Frozeni retired."], now=1100.0)
        rec = kinds(self.records(), ledger_mod.RETIRED)
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["steam_id"], FROZENI)

    def test_disconnect_and_reconnect_stay_inside_one_race(self):
        """§4.3: the only interruption a race survives -- and it is still one race."""
        self.arm_race()
        feed(self.ctl, [
            "[SR] Frozeni disconnected.",
            "Players (0):",
            "Player connected: [SR] Frozeni (Champion of Speed)",
            "Players (1):",
            " - [SR] Frozeni (76561197989276622)",
        ], now=1100.0)
        recs = self.records()
        self.assertEqual(len(kinds(recs, ledger_mod.EVENT_INIT)), 1)
        self.assertEqual(len(kinds(recs, ledger_mod.LEAVE)), 1)
        self.assertEqual(len(kinds(recs, ledger_mod.JOIN)), 1)

    def test_a_spectator_disconnecting_is_marked_as_one(self):
        feed(self.ctl, ["(Spectator) [VSR] McVizn disconnected."])
        rec = kinds(self.records(), ledger_mod.LEAVE)[0]
        self.assertTrue(rec["spectator"])
        self.assertEqual(rec["name"], "[VSR] McVizn")

    def test_transitions_are_attributed_to_the_race_they_happened_in(self):
        feed(self.ctl, ["#EventInit"])
        feed(self.ctl, ["#EventEnd"])
        feed(self.ctl, ["#EventInit"])
        feed(self.ctl, ["[SR] Frozeni retired."], now=1200.0)
        rec = kinds(self.records(), ledger_mod.RETIRED)[0]
        self.assertEqual((rec["round"], rec["phase"]), (1, "race"))


class TestJournalShape(LedgerCase):
    def test_every_record_carries_its_heat(self):
        feed(self.ctl, ["#EventInit", "[SR] Frozeni retired."])
        for rec in self.records():
            self.assertEqual(rec["heat_id"], 80)
            self.assertTrue(rec["heat_uid"])
            self.assertIn("ts", rec)

    def test_heat_uid_survives_a_reset_of_the_id_counter(self):
        """The July test heats used ids the live counter will hand out again."""
        first = ledger_mod.heat_uid(100, when=1753920000)
        second = ledger_mod.heat_uid(100, when=1785456000)
        self.assertNotEqual(first, second)

    def test_a_second_heat_gets_its_own_file(self):
        first = self.ctl.ledger.heat_uid
        self.ctl.ledger.end_heat()
        second = self.ctl.ledger.start_heat(81, 2, uid="20260825T120000-81")
        self.ctl.ledger.retired(MCVIZN, "[VSR] McVizn")
        self.assertNotEqual(first, second)
        self.assertEqual(
            sorted(f for f in os.listdir(self.tmp) if f.endswith(".jsonl")),
            sorted([f"{first}.jsonl", f"{second}.jsonl"]),
        )

    def test_records_stop_once_a_heat_is_closed(self):
        """A stray line after the heat must not reopen a finished journal."""
        self.ctl.ledger.end_heat()
        before = len(self.records())
        self.ctl.ledger.retired(MCVIZN, "[VSR] McVizn")
        self.assertEqual(len(self.records()), before)

    def test_an_unwritable_directory_does_not_stop_the_heat(self):
        """Statistics must never cost a race."""
        led = ledger_mod.Ledger("/proc/nope/definitely-not-writable")
        led.start_heat(1, 3)
        led.retired(MCVIZN, "[VSR] McVizn")
        led.end_heat()


if __name__ == "__main__":
    unittest.main(verbosity=2)
