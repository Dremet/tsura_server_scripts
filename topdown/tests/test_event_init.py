"""Event-init tests: walk a whole heat, then survive a restart mid-heat."""

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
    "heat_id": 42,
    "heat_uid": "20260825T210000-42",
    "vehicle": "VoZzer",
    "quali_laps": 1,
    "quali_points": [1],
    "race_points": [10, 6, 4, 3, 2, 1],
    "drafting": {"draftingSpeedEffect": 5},
    "rounds": [
        {"track": "Jonno Island v1.0", "track_guid": "139k2kmmzws3-33vswqr",
         "laps": 11, "ai_lines": True},
        {"track": "Maple Ridge v1.1", "track_guid": "13ng23pntnl3-3472zvj",
         "laps": 12, "ai_lines": True},
        {"track": "E.V.M.C. V1", "track_guid": "11kcwn867t23-329n370",
         "laps": 10, "ai_lines": False},
        {"track": "CSup Sugar Hill V1.0", "track_guid": "z316kaggp23-2zcdqea",
         "laps": 10, "ai_lines": True},
    ],
}


class HeatHarness(unittest.TestCase):
    """Runs the real scripts in a scratch directory, like the server would."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # webconfig.py sits next to them on the real server; run_event_init
        # reads the panel's collision settings through it.
        for name in ("run_event_init.py", "run_event_end.py", "webconfig.py"):
            shutil.copy(os.path.join(SCRIPTS, name), self.dir)
        self.write("heat_plan.json", PLAN)
        self.write("heat_progress.json",
                   {"heat_id": 42, "round": 0, "phase": "quali", "done": False})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8-sig") as fh:
            return json.load(fh)

    def run_script(self, name):
        result = subprocess.run([sys.executable, name], cwd=self.dir,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def event_init(self):
        self.run_script("run_event_init.py")
        with open(os.path.join(self.dir, "event_init_generated.src"),
                  encoding="utf-8-sig") as fh:
            return fh.read().splitlines()

    def event_end(self):
        self.run_script("run_event_end.py")


class TestSequence(HeatHarness):
    def test_full_heat_alternates_quali_and_race(self):
        seen = []
        for _ in range(8):
            cmds = self.event_init()
            mode = [c for c in cmds if c.startswith("/race.raceMode")][0]
            track = [c for c in cmds if "/broadcast" in c and
                     ("Qualifying at" in c or "Race at" in c)][0]
            seen.append((mode.split("=")[1].strip(), track))
            self.event_end()

        modes = [m for m, _ in seen]
        self.assertEqual(modes, ["Hotlapping", "Race"] * 4)

        # Each track is used for exactly one quali and one race, in plan order.
        for i, rnd in enumerate(PLAN["rounds"]):
            self.assertIn(rnd["track"], seen[i * 2][1])
            self.assertIn(rnd["track"], seen[i * 2 + 1][1])

    def test_race_uses_the_planned_lap_count(self):
        self.event_init()          # quali
        self.event_end()
        cmds = self.event_init()   # race on Jonno Island, 11 laps
        self.assertIn("/race.maxLaps = 11", cmds)

    def test_quali_is_one_lap_and_scores_only_the_pole(self):
        cmds = self.event_init()
        self.assertIn("/race.maxLaps = 1", cmds)
        self.assertIn("/points.position1 = 1", cmds)
        self.assertIn("/points.position2 = 0", cmds)

    def test_race_uses_mcvizns_point_table(self):
        self.event_init()
        self.event_end()
        cmds = self.event_init()
        for pos, pts in enumerate([10, 6, 4, 3, 2, 1], 1):
            self.assertIn(f"/points.position{pos} = {pts}", cmds)
        self.assertIn("/points.position7 = 0", cmds)
        self.assertIn("/points.position20 = 0", cmds)

    def test_grid_comes_from_qualifying_and_is_not_reversed(self):
        self.event_init()
        self.event_end()
        cmds = self.event_init()
        self.assertIn("/race.startingOrder = LastEvent", cmds)
        self.assertFalse(any("Reverse" in c for c in cmds))

    def test_track_without_ai_lines_is_announced(self):
        for _ in range(4):          # skip to the third track's quali
            self.event_init()
            self.event_end()
        cmds = self.event_init()
        self.event_end()
        cmds = self.event_init()    # its race
        self.assertTrue(any("without bots" in c for c in cmds))

    def test_drafting_settings_are_applied_to_races_only(self):
        quali = self.event_init()
        self.assertFalse(any("drafting" in c for c in quali))
        self.event_end()
        race = self.event_init()
        self.assertIn("/drafting.draftingSpeedEffect = 5", race)


class TestRestartRobustness(HeatHarness):
    """A restart re-fires the event init without an event end."""

    def test_phase_is_kept_when_no_event_finished(self):
        first = self.event_init()
        again = self.event_init()          # simulated restart, no event_end
        self.assertEqual(first, again, "the phase must not flip on a restart")
        self.assertEqual(self.read("heat_progress.json")["phase"], "quali")

    def test_restart_between_quali_and_race_keeps_the_race_pending(self):
        self.event_init()
        self.event_end()                   # quali finished
        race = self.event_init()
        self.assertIn("/race.raceMode = Race", race)
        again = self.event_init()          # restart before the race ran
        self.assertIn("/race.raceMode = Race", again)
        self.assertEqual(self.read("heat_progress.json")["round"], 0)

    def test_cursor_advances_only_on_a_real_event_end(self):
        for _ in range(3):
            self.event_init()
        self.assertEqual(self.read("heat_progress.json")["round"], 0)
        self.event_end()
        self.event_init()
        self.assertEqual(self.read("heat_progress.json")["phase"], "race")


class TestDegradedInput(HeatHarness):
    def test_missing_plan_still_produces_a_valid_script(self):
        os.remove(os.path.join(self.dir, "heat_plan.json"))
        cmds = self.event_init()
        self.assertTrue(cmds, "must never write an empty init script")
        self.assertTrue(any("No heat plan" in c for c in cmds))

    def test_running_past_the_end_of_the_plan_is_survivable(self):
        for _ in range(8):
            self.event_init()
            self.event_end()
        cmds = self.event_init()           # a ninth event the plan knows nothing of
        self.assertTrue(any("No heat plan" in c for c in cmds))

    def test_corrupt_progress_file_falls_back_to_the_first_event(self):
        with open(os.path.join(self.dir, "heat_progress.json"), "w") as fh:
            fh.write("{ not json")
        cmds = self.event_init()
        self.assertIn("/race.raceMode = Hotlapping", cmds)


class TestHeatStamp(HeatHarness):
    def test_stamp_identifies_the_heat_and_round(self):
        self.event_init()
        self.event_end()
        stamp = self.read("topdown_heat.json")
        self.assertEqual(stamp["heat_id"], 42)
        self.assertEqual(stamp["round"], 1)
        self.assertEqual(stamp["phase"], "quali")
        self.assertEqual(stamp["track"], "Jonno Island v1.0")

    def test_stamp_follows_the_heat(self):
        for _ in range(3):
            self.event_init()
            self.event_end()
        stamp = self.read("topdown_heat.json")
        self.assertEqual(stamp["round"], 2)
        self.assertEqual(stamp["phase"], "quali")
        self.assertEqual(stamp["track"], "Maple Ridge v1.1")

    def test_stamp_carries_the_key_the_status_journal_is_filed_under(self):
        """Without this the results and the journal cannot be joined at all."""
        self.event_init()
        self.event_end()
        self.assertEqual(self.read("topdown_heat.json")["heat_uid"],
                         PLAN["heat_uid"])

    def test_stamp_survives_a_plan_from_before_the_journal_existed(self):
        """An in-flight heat planned by the old controller must not break."""
        plan = {k: v for k, v in PLAN.items() if k != "heat_uid"}
        self.write("heat_plan.json", plan)
        self.event_init()
        self.event_end()
        self.assertIsNone(self.read("topdown_heat.json")["heat_uid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCamera(unittest.TestCase):
    """Each track gets its own overhead camera written into camera.json.

    The server only reads camera.json while loading an event -- changing it from
    the lobby or mid-race does nothing (confirmed in-game 2026-07-31), so the
    event-init hook is the one place this can happen.
    """

    CAM = {"cameraPosition": 7, "distance": 109.2385,
           "verticalAngle": 49.6452, "horizontalAngle": 229.47}

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dir = os.path.join(self.root, "Scripts")
        os.makedirs(self.dir)
        for name in ("run_event_init.py", "webconfig.py"):
            shutil.copy(os.path.join(SCRIPTS, name), self.dir)
        # camera.json sits one level above Scripts/, as on the real server.
        self.camera_path = os.path.join(self.root, "camera.json")
        with open(self.camera_path, "w", encoding="utf-8-sig") as fh:
            json.dump({"preset4": {"distance": 1.0, "horizontalAngle": 0.0,
                                   "fov": 42.0}}, fh)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _init_with(self, cam):
        plan = json.loads(json.dumps(PLAN))
        for rnd in plan["rounds"]:
            rnd["camera_settings"] = cam
        with open(os.path.join(self.dir, "heat_plan.json"), "w") as fh:
            json.dump(plan, fh)
        with open(os.path.join(self.dir, "heat_progress.json"), "w") as fh:
            json.dump({"round": 0, "phase": "quali"}, fh)
        subprocess.run([sys.executable, "run_event_init.py"], cwd=self.dir,
                       check=True)
        with open(os.path.join(self.dir, "event_init_generated.src"),
                  encoding="utf-8-sig") as fh:
            return fh.read().splitlines()

    def _camera(self):
        with open(self.camera_path, encoding="utf-8-sig") as fh:
            return json.load(fh)

    def test_topview_is_forced(self):
        # 4 == "TopView"; McVizn overrode that built-in camera rather than
        # adding a custom preset.
        self.assertIn("/special.forcedCameraPreset = 9", self._init_with(self.CAM))

    def test_values_are_written_into_camera_json(self):
        self._init_with(self.CAM)
        preset = self._camera()["preset4"]
        self.assertAlmostEqual(preset["horizontalAngle"], 229.47)
        self.assertAlmostEqual(preset["distance"], 109.2385)
        self.assertAlmostEqual(preset["verticalAngle"], 49.6452)

    def test_untouched_keys_survive(self):
        self._init_with(self.CAM)
        self.assertAlmostEqual(self._camera()["preset4"]["fov"], 42.0,
                               msg="only the given keys may be overwritten")

    def test_other_presets_are_left_alone(self):
        with open(self.camera_path, "w", encoding="utf-8-sig") as fh:
            json.dump({"preset4": {}, "preset5": {"distance": 55.0}}, fh)
        self._init_with(self.CAM)
        self.assertAlmostEqual(self._camera()["preset5"]["distance"], 55.0)

    def test_camera_is_forced_even_without_per_track_values(self):
        # The overhead view must be enforced regardless; only the fine-tuning
        # is optional.
        self.assertIn("/special.forcedCameraPreset = 9", self._init_with(None))

    def test_unwritable_camera_file_does_not_break_the_event(self):
        os.remove(self.camera_path)
        cmds = self._init_with(self.CAM)
        self.assertIn("/race.raceMode = Hotlapping", cmds)
        self.assertIn("/special.forcedCameraPreset = 9", cmds,
                      "a failed tune must not cost us the overhead view")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestSessionMode(HeatHarness):
    """With a session archive loaded, the archive owns the event settings."""

    def setUp(self):
        super().setUp()
        plan = json.loads(json.dumps(PLAN))
        plan["session_name"] = "topdown_heat"
        self.write("heat_plan.json", plan)

    def test_no_settings_are_pushed(self):
        cmds = self.event_init()
        for forbidden in ("/race.", "/points.", "/fuel.", "/tireWear.",
                          "/special.", "/refreshfiles"):
            self.assertFalse(any(c.startswith(forbidden) for c in cmds),
                             f"{forbidden} would fight the loaded session")

    def test_the_round_is_still_announced(self):
        cmds = self.event_init()
        self.assertTrue(any("Qualifying at Jonno Island" in c for c in cmds))

    def test_cursor_still_advances_for_the_results_stamp(self):
        self.event_init()
        self.event_end()
        self.event_init()
        self.assertEqual(self.read("heat_progress.json")["phase"], "race")
        cmds = self.event_init()
        self.assertTrue(any("Race at Jonno Island" in c for c in cmds))
