"""State machine tests: a full heat is replayed without a game server."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from td import heat as heat_mod  # noqa: E402
from td.machine import COOLDOWN, COUNTDOWN, HEAT, IDLE, HeatMachine  # noqa: E402

ALICE, BOB, CARA = 76561197989276622, 76561198131829686, 76561198096169747
ADMIN = ALICE

TRACKS = [
    {"name": "Buffalo Hill - Rallycross v1.0", "guid": "z1s768q5723-2z9rhj7", "laps": 10},
    {"name": "CSup - Lost Lagoons v1", "guid": "xvf09b5nq83-2xw55w3", "laps": 10},
    {"name": "CSup Sugar Hill V1.0", "guid": "z316kaggp23-2zcdqea", "laps": 10},
    {"name": "Maple Ridge v1.1", "guid": "13ng23pntnl3-3472zvj", "laps": 10},
    {"name": "Jonno Island v1.0", "guid": "139k2kmmzws3-33vswqr", "laps": 10},
    {"name": "E.V.M.C. V1", "guid": "11kcwn867t23-329n370", "laps": 10},
]
VOZZER = "17xxzrmve5gb-3868ch8"
AI_PAIRS = {(t["guid"].lower(), VOZZER.lower()) for t in TRACKS}


def make_machine(**over):
    config = {
        "tracks": TRACKS, "vehicle": "VoZzer", "vehicle_guid": VOZZER,
        "tracks_per_heat": 4, "countdown_seconds": 90, "cooldown_seconds": 60,
        "vote_seconds": 60, "bot_fill": 14, "max_drivers": 20,
        "bots_off_from_humans": 6,
        "ingame_admins": [[str(ADMIN), "owner"]],
    }
    config.update(over)
    rng = random.Random(1)
    counter = {"n": 0}

    def build_plan():
        counter["n"] += 1
        plan = heat_mod.build_heat_plan(config, rng, AI_PAIRS)
        plan["heat_id"] = counter["n"]
        return plan

    return HeatMachine(config, rng, build_plan)


def joined(*ids):
    return {i: f"player{i}" for i in ids}


def start_heat(m, ids=(ALICE,), t0=0.0):
    """Empty lobby -> countdown -> heat live (server reports #SessionInit)."""
    m.set_players(joined(*ids), t0)
    cmds = m.tick(t0 + 91)
    m.on_session_started(t0 + 92)      # the session we asked for is up
    return cmds


def run_heat_to_end(m, t0=0.0):
    """Drive a machine from empty lobby through one complete heat."""
    start_heat(m, (ALICE,), t0)
    for i in range(m.events_total):
        m.on_event_ended(t0 + 100 + i)
    m.on_session_ended(t0 + 200)       # server closes the session after the list
    return m


class TestCountdown(unittest.TestCase):
    def test_first_join_starts_the_countdown(self):
        m = make_machine()
        cmds = m.set_players(joined(ALICE), 0)
        self.assertEqual(m.state, COUNTDOWN)
        self.assertTrue(any("90 seconds" in c for c in cmds))

    def test_countdown_is_fixed_and_further_joins_do_not_extend_it(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        deadline = m.deadline
        m.set_players(joined(ALICE, BOB), 30)
        m.set_players(joined(ALICE, BOB, CARA), 60)
        self.assertEqual(m.deadline, deadline, "B1: the countdown must not reset")

    def test_marks_are_announced_once_each(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        said = []
        for t in range(1, 90):
            said += m.tick(t)
        for mark in (60, 30, 10):
            hits = [c for c in said if f"in {mark} seconds" in c]
            self.assertEqual(len(hits), 1, f"the {mark}s mark should be announced once")

    def test_heat_starts_when_the_countdown_expires(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        cmds = m.tick(91)
        self.assertEqual(m.state, HEAT)
        self.assertIn("/continue", cmds)

    def test_everyone_leaving_during_the_countdown_returns_to_idle(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        m.set_players({}, 10)
        self.assertEqual(m.state, IDLE)
        m.tick(200)
        self.assertEqual(m.state, IDLE, "no heat may start in an empty lobby")


class TestHeatSetup(unittest.TestCase):
    """Tracks/cars/AI are applied by run_session_init.py, not from here.

    TSU refuses them outside session init ("Cannot change levels after session
    init"), which is what broke the first live heat.
    """

    def test_asks_the_server_for_a_fresh_session(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        cmds = m.tick(91)
        self.assertIn("/abortsession Yes", cmds)
        self.assertIn("/continue", cmds)
        self.assertTrue(cmds.index("/abortsession Yes") < cmds.index("/continue"),
                        "end the old session before starting the next")

    def test_does_not_push_level_commands_mid_session(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        cmds = m.tick(91)
        for forbidden in ("/level /add", "/levels /clear", "/vehicle /add",
                          "/set ai."):
            self.assertFalse(any(c.startswith(forbidden) for c in cmds),
                             f"{forbidden} would be refused outside session init")

    def test_heat_only_counts_events_once_the_session_is_live(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        m.tick(91)
        m.on_event_ended(92)          # the aborted event of the OLD session
        self.assertEqual(m.events_done, 0, "must not count the old session's event")
        m.on_session_started(93)
        m.on_event_ended(94)
        self.assertEqual(m.events_done, 1)

    def test_retries_when_the_session_never_starts(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        m.tick(91)
        cmds = m.tick(91 + 31)
        self.assertIn("/continue", cmds, "nudge the server again")

    def test_gives_up_after_repeated_failures(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        m.tick(91)
        t, said = 91, []
        for _ in range(5):
            t += 31
            said += m.tick(t)
        self.assertEqual(m.state, IDLE)
        self.assertTrue(any("tell an admin" in c for c in said))
        self.assertEqual(said.count("/continue"), 3, "bounded retries, then stop")

    def test_no_tracks_configured_does_not_wedge_the_machine(self):
        m = make_machine(tracks=[])
        m.set_players(joined(ALICE), 0)
        cmds = m.tick(91)
        self.assertEqual(m.state, IDLE)
        self.assertTrue(any("No tracks configured" in c for c in cmds))


class TestHeatProgress(unittest.TestCase):
    def test_eight_events_complete_the_heat(self):
        m = make_machine()
        start_heat(m)
        self.assertEqual(m.events_total, 8)
        for i in range(7):
            m.on_event_ended(100 + i)
            self.assertEqual(m.state, HEAT)
        cmds = m.on_event_ended(200)
        self.assertEqual(m.state, COOLDOWN)
        self.assertTrue(any("complete" in c for c in cmds))

    def test_next_heat_starts_after_the_cooldown(self):
        m = make_machine()
        run_heat_to_end(m)
        first = m.heat_id
        self.assertEqual(m.state, COOLDOWN)
        m.tick(1000)
        self.assertEqual(m.state, HEAT)
        self.assertNotEqual(m.heat_id, first, "a new heat gets a new id")

    def test_empty_lobby_after_a_heat_goes_idle(self):
        m = make_machine()
        start_heat(m)
        m.set_players({}, 95)
        m.on_event_ended(100)          # bots finish the current event
        self.assertEqual(m.state, IDLE)


class TestAbandonment(unittest.TestCase):
    def test_bots_finish_the_current_event_then_the_heat_ends(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB))
        m.on_event_ended(100)
        self.assertEqual(m.state, HEAT)
        m.set_players({}, 105)
        self.assertEqual(m.state, HEAT, "B5: the running event is not cut short")
        self.assertTrue(m.abandoned)
        cmds = m.on_event_ended(150)
        self.assertNotEqual(m.state, HEAT)
        self.assertTrue(any("ended early" in c for c in cmds))

    def test_one_player_leaving_does_not_end_the_heat(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB))
        m.set_players(joined(ALICE), 100)
        self.assertFalse(m.abandoned)
        self.assertEqual(m.state, HEAT)


class TestBots(unittest.TestCase):
    def test_bots_fill_the_grid_by_default(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        self.assertEqual(m.effective_bot_fill(), 14)

    def test_bots_switch_off_from_six_humans(self):
        m = make_machine()
        m.set_players(joined(*range(1, 7)), 0)
        self.assertEqual(m.effective_bot_fill(), 0)

    def test_admin_change_only_applies_from_the_next_race(self):
        m = make_machine()
        start_heat(m)
        cmds = m.on_chat(ADMIN, "owner", "/bot 8", 100)
        self.assertTrue(any("from the next race" in c for c in cmds))
        self.assertNotIn("/set ai.aiFill 8", cmds, "C3: not mid-race")
        applied = m.on_event_ended(110)
        self.assertIn("/set ai.aiFill 8", applied)

    def test_grid_size_is_capped(self):
        m = make_machine()
        start_heat(m)
        cmds = m.on_chat(ADMIN, "owner", "/bot 99", 100)
        self.assertTrue(any("between 0 and 20" in c for c in cmds))

    def test_nonsense_argument_is_rejected(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        cmds = m.on_chat(ADMIN, "owner", "/bot lots", 10)
        self.assertTrue(any("Usage" in c for c in cmds))


class TestVoting(unittest.TestCase):
    def test_two_thirds_needed_for_a_race_restart(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        cmds = m.on_chat(BOB, "bob", "/restart", 100)      # 1 of 2 needed
        self.assertNotIn("/restartevent", cmds)
        cmds = m.on_chat(CARA, "cara", "/restart", 101)    # 2 of 2 -> passes
        self.assertIn("/restartevent", cmds)

    def test_voting_twice_does_not_count_twice(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        m.on_chat(BOB, "bob", "/restart", 100)
        cmds = m.on_chat(BOB, "bob", "/restart", 101)
        self.assertNotIn("/restartevent", cmds, "one player, one vote")

    def test_admin_forces_a_restart_alone(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        cmds = m.on_chat(ADMIN, "owner", "/restart", 100)
        self.assertIn("/restartevent", cmds)

    def test_vote_expires(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        m.on_chat(BOB, "bob", "/restart", 100)
        cmds = m.tick(200)
        self.assertTrue(any("failed" in c for c in cmds))
        self.assertIsNone(m.vote)

    def test_heat_reset_needs_everyone_who_started(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        first = m.heat_id
        m.on_chat(BOB, "bob", "/restart tdheat", 100)
        m.on_chat(CARA, "cara", "/restart tdheat", 101)
        self.assertEqual(m.heat_id, first, "B4: not unanimous yet")
        cmds = m.on_chat(ALICE, "alice", "/restart tdheat", 102)
        self.assertNotEqual(m.heat_id, first, "unanimous -> new heat")
        self.assertTrue(any("was restarted" in c for c in cmds))

    def test_late_joiner_does_not_block_a_heat_reset(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB))
        first = m.heat_id
        m.set_players(joined(ALICE, BOB, CARA), 95)   # B4: late arrival
        m.on_chat(ALICE, "alice", "/restart tdheat", 100)
        m.on_chat(BOB, "bob", "/restart tdheat", 101)
        self.assertNotEqual(m.heat_id, first, "only the starters get a say")

    def test_quorum_shrinks_when_a_voter_leaves(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB, CARA))
        m.on_chat(BOB, "bob", "/restart", 100)        # 1 of 2
        cmds = m.set_players(joined(ALICE, BOB), 105)  # now 2 present -> 2 needed
        self.assertNotIn("/restartevent", cmds)
        cmds = m.set_players(joined(BOB), 106)         # only the voter is left
        self.assertIn("/restartevent", cmds, "the remaining player already agreed")

    def test_unknown_player_cannot_vote(self):
        m = make_machine()
        start_heat(m, (ALICE, BOB))
        self.assertEqual(m.on_chat(None, "ghost", "/restart", 100), [])


class TestStatus(unittest.TestCase):
    def test_status_during_a_heat(self):
        m = make_machine()
        start_heat(m)
        m.on_event_ended(100)
        out = m.on_chat(ALICE, "alice", "!status", 101)[0]
        self.assertIn("Heat #", out)
        self.assertIn("race", out)

    def test_status_when_idle(self):
        m = make_machine()
        out = m.on_chat(ALICE, "alice", "!status", 0)[0]
        self.assertIn("No heat running", out)

    def test_plain_chat_is_not_a_command(self):
        m = make_machine()
        m.set_players(joined(ALICE), 0)
        self.assertEqual(m.on_chat(ALICE, "alice", "hi everyone", 10), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
