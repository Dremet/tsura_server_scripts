"""Session-init tests.

This hook runs in the one window where TSU accepts track, car and AI changes.
Getting it wrong is what broke the first live heat, so the commands it emits are
pinned down here.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "server", "config", "Scripts")

PLAN = {
    "heat_id": 7,
    "vehicle": "VoZzer",
    "vehicle_guid": "17xxzrmve5gb-3868ch8",
    "ai_fill": 14,
    "ai": {"aiSkill": 10, "aiSkillLevel1": 3, "humanStartPosition": 2,
           "aiClanTag": "BOT"},
    "admins": [["76561197989276622", "Dremet"], ["76561198131829686", "McVizn"]],
    "rounds": [
        {"track": "Buffalo Hill - Rallycross v1.0", "laps": 12, "ai_lines": True},
        {"track": "CSup - Lost Lagoons v1", "laps": 6, "ai_lines": True},
        {"track": "Jonno Island v1.0", "laps": 8, "ai_lines": True},
        {"track": "E.V.M.C. V1", "laps": 10, "ai_lines": False},
    ],
}


class SessionInitHarness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        shutil.copy(os.path.join(SCRIPTS, "run_session_init.py"), self.dir)
        self.plan = json.loads(json.dumps(PLAN))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_init(self):
        with open(os.path.join(self.dir, "heat_plan.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(self.plan, fh)
        r = subprocess.run([sys.executable, "run_session_init.py"], cwd=self.dir,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.dir, "session_init_generated.src"),
                  encoding="utf-8-sig") as fh:
            return fh.read().splitlines()


class TestTrackQueue(SessionInitHarness):
    def test_each_track_is_queued_twice(self):
        cmds = self.run_init()
        adds = [c for c in cmds if c.startswith("/level /add")]
        self.assertEqual(len(adds), 8, "4 tracks x (quali + race)")
        for track in (r["track"] for r in PLAN["rounds"]):
            self.assertEqual(adds.count(f"/level /add '{track}'"), 2)

    def test_list_is_cleared_before_filling(self):
        cmds = self.run_init()
        self.assertLess(cmds.index("/levels /clear"),
                        min(i for i, c in enumerate(cmds)
                            if c.startswith("/level /add")))

    def test_tracks_keep_their_planned_order(self):
        cmds = self.run_init()
        adds = [c for c in cmds if c.startswith("/level /add")]
        order = [a for i, a in enumerate(adds) if i % 2 == 0]
        self.assertEqual(order,
                         [f"/level /add '{r['track']}'" for r in PLAN["rounds"]])


class TestSessionSettings(SessionInitHarness):
    def test_timer_is_switched_on(self):
        # game.json ships with timerOn=false, which leaves the lobby waiting for
        # every player to press ready (hit live on 2026-07-31).
        self.assertIn("/timerOn = true", self.run_init())

    def test_timer_can_be_switched_off_for_hand_driven_tests(self):
        self.plan["timer_on"] = False
        self.assertIn("/timerOn = false", self.run_init())

    def test_car_is_forced(self):
        cmds = self.run_init()
        self.assertIn("/vehicles /clear", cmds)
        self.assertIn("/vehicle /add 'VoZzer'", cmds)

    def test_admins_are_synced(self):
        cmds = self.run_init()
        self.assertIn("/admins /clear", cmds)
        self.assertIn("/admins /add 76561197989276622", cmds)
        self.assertIn("/admins /add 76561198131829686", cmds)

    def test_no_fastest_lap_bonus(self):
        # McVizn's scheme is quali pole + 10-6-4-3-2-1; the server defaults to
        # handing out an extra point for the fastest lap.
        self.assertIn("/points.pointsForFastestLap = 0", self.run_init())


class TestBots(SessionInitHarness):
    def test_grid_fill_comes_from_the_plan(self):
        self.assertIn("/set ai.aiFill 14", self.run_init())

    def test_bots_off_is_passed_through(self):
        self.plan["ai_fill"] = 0
        self.assertIn("/set ai.aiFill 0", self.run_init())

    def test_mcvizns_ai_settings_are_applied(self):
        cmds = self.run_init()
        self.assertIn("/set ai.aiSkill 10", cmds)
        self.assertIn("/set ai.humanStartPosition 2", cmds)
        self.assertIn("/set ai.forceAIClanTag true", cmds)
        self.assertIn("/set ai.aiClanTag BOT", cmds)

    def test_missing_ai_block_is_survivable(self):
        self.plan.pop("ai")
        cmds = self.run_init()
        self.assertIn("/set ai.aiFill 14", cmds)
        self.assertFalse(any("aiSkill" in c for c in cmds))

    def test_tracks_without_lines_are_announced(self):
        cmds = self.run_init()
        self.assertTrue(any("E.V.M.C. V1" in c and "without bots" in c
                            for c in cmds))


class TestCursorReset(SessionInitHarness):
    def test_a_new_session_rewinds_to_round_one_qualifying(self):
        with open(os.path.join(self.dir, "heat_progress.json"), "w") as fh:
            json.dump({"round": 3, "phase": "race"}, fh)
        open(os.path.join(self.dir, "topdown_event_done"), "w").close()
        self.run_init()
        with open(os.path.join(self.dir, "heat_progress.json"),
                  encoding="utf-8-sig") as fh:
            progress = json.load(fh)
        self.assertEqual((progress["round"], progress["phase"]), (0, "quali"))
        self.assertEqual(progress["heat_id"], 7)
        self.assertFalse(os.path.exists(os.path.join(self.dir,
                                                     "topdown_event_done")),
                         "a stale marker would skip the first qualifying")


class TestDegraded(SessionInitHarness):
    def test_empty_plan_does_not_produce_a_broken_script(self):
        self.plan["rounds"] = []
        cmds = self.run_init()
        self.assertTrue(cmds)
        self.assertFalse(any(c.startswith("/level /add") for c in cmds))

    def test_missing_plan_file(self):
        r = subprocess.run([sys.executable, "run_session_init.py"], cwd=self.dir,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(self.dir, "session_init_generated.src")))

    def test_track_name_with_apostrophe_uses_double_quotes(self):
        self.plan["rounds"] = [{"track": "Mac's Ridge v1", "laps": 5,
                                "ai_lines": True}]
        self.assertIn('/level /add "Mac\'s Ridge v1"', self.run_init())


if __name__ == "__main__":
    unittest.main(verbosity=2)
