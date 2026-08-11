"""Session-archive builder tests.

The archive is the only way to give each track its own camera: the server reads
the container once at session start and ignores later changes (developer,
2026-08-01; confirmed live when two tracks in one heat shared a camera).
"""

import json
import os
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from td import camfile, session  # noqa: E402

PARTS_DIR = os.path.join(HERE, "..", "session_parts")

PLAN = {
    "quali_laps": 1,
    "quali_points": [1],
    "race_points": [10, 6, 4, 3, 2, 1],
    "rounds": [
        {"track": "Jonno Island v1.0", "laps": 8},
        {"track": "E.V.M.C. V1", "laps": 10},
        {"track": "Buffalo Hill - Rallycross v1.0", "laps": 12},
        {"track": "Maple Ridge v1.1", "laps": 14},
    ],
}


class BuilderHarness(unittest.TestCase):
    def setUp(self):
        self.parts = session.PartsBin(PARTS_DIR)
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "heat.zip")

    def build(self, plan=None, **kw):
        session.build_session(plan or PLAN, self.parts, self.out, **kw)
        return zipfile.ZipFile(self.out)

    def doc(self, zf, name):
        return json.loads(zf.read(name).decode("utf-8-sig"))


class TestArchiveShape(BuilderHarness):
    def test_four_tracks_become_eight_events(self):
        zf = self.build()
        names = set(zf.namelist())
        self.assertIn("levels.json", names)
        for i in range(1, 9):
            for suffix in ("level.json", "event.json", "vehicles.json",
                           "ai.json", "camera5.cam"):
                self.assertIn(f"{i:03d}-{suffix}", names)
        self.assertNotIn("009-event.json", names)

    def test_levels_index_lists_every_event(self):
        zf = self.build()
        index = self.doc(zf, "levels.json")
        self.assertEqual(len(index["levels"]), 8)
        self.assertEqual(index["heats"], 1)
        self.assertTrue(all("m_guid" in e for e in index["levels"]))

    def test_each_track_appears_twice_in_a_row(self):
        zf = self.build()
        names = [self.doc(zf, f"{i:03d}-level.json")["name"] for i in range(1, 9)]
        self.assertEqual(names, [
            "Jonno Island v1.0", "Jonno Island v1.0",
            "E.V.M.C. V1", "E.V.M.C. V1",
            "Buffalo Hill - Rallycross v1.0", "Buffalo Hill - Rallycross v1.0",
            "Maple Ridge v1.1", "Maple Ridge v1.1",
        ])


class TestCameras(BuilderHarness):
    """The whole reason for this builder."""

    def test_camera_files_are_copied_byte_for_byte(self):
        zf = self.build()
        for i, track in enumerate(PLAN["rounds"], 0):
            original = open(self.parts.tracks[track["track"]]["camera"], "rb").read()
            for event in (i * 2 + 1, i * 2 + 2):
                self.assertEqual(zf.read(f"{event:03d}-camera5.cam"), original,
                                 f"{track['track']} camera must be unmodified")

    def test_each_track_carries_its_own_camera(self):
        zf = self.build()
        # Jonno and E.V.M.C. have different headings in McVizn's files.
        jonno = camfile.decode(zf.read("001-camera5.cam"))
        evmc = camfile.decode(zf.read("003-camera5.cam"))
        self.assertNotAlmostEqual(jonno["horizontalAngle"], evmc["horizontalAngle"])
        self.assertAlmostEqual(jonno["horizontalAngle"], 229.47, places=1)
        self.assertAlmostEqual(evmc["horizontalAngle"], 90.06, places=1)

    def test_events_force_the_camera_preset(self):
        zf = self.build()
        for i in range(1, 9):
            ev = self.doc(zf, f"{i:03d}-event.json")
            self.assertEqual(ev["special"]["forcedCameraPreset"],
                             session.CAMERA_PRESET_JSON)


class TestEventSettings(BuilderHarness):
    def test_odd_events_are_qualifying_even_ones_races(self):
        zf = self.build()
        for i in range(1, 9):
            ev = self.doc(zf, f"{i:03d}-event.json")["race"]
            expected = session.RACE_MODE_HOTLAPPING if i % 2 else session.RACE_MODE_RACE
            self.assertEqual(ev["raceMode"], expected, f"event {i}")

    def test_lap_counts(self):
        zf = self.build()
        self.assertEqual(self.doc(zf, "001-event.json")["race"]["maxLaps"], 1)
        self.assertEqual(self.doc(zf, "002-event.json")["race"]["maxLaps"], 8)
        self.assertEqual(self.doc(zf, "004-event.json")["race"]["maxLaps"], 10)
        self.assertEqual(self.doc(zf, "008-event.json")["race"]["maxLaps"], 14)

    def test_point_tables(self):
        zf = self.build()
        quali = self.doc(zf, "001-event.json")["race"]["points"]
        race = self.doc(zf, "002-event.json")["race"]["points"]
        self.assertEqual(quali["position1"], 1)
        self.assertEqual(quali["position2"], 0)
        self.assertEqual([race[f"position{i}"] for i in range(1, 8)],
                         [10, 6, 4, 3, 2, 1, 0])

    def test_no_fastest_lap_bonus(self):
        zf = self.build()
        for i in (1, 2):
            self.assertEqual(
                self.doc(zf, f"{i:03d}-event.json")["race"]["points"]["pointsForFastestLap"], 0)

    def test_race_grid_comes_from_the_qualifying(self):
        """Regression: startingOrder 1 is ReverseStandings, not LastEvent.

        Getting this wrong sent the quali winner to the back of the grid
        (reported from a live heat on 2026-08-02).
        """
        zf = self.build()
        race = self.doc(zf, "002-event.json")["race"]
        self.assertEqual(race["startingOrder"], session.STARTING_ORDER_LAST_EVENT)
        self.assertEqual(race["startingOrder"], 3)
        self.assertNotEqual(race["startingOrder"],
                            session.STARTING_ORDER_REVERSE_STANDINGS)

    def test_qualifying_is_ghosted(self):
        """No collisions in qualifying -- everyone drives their lap alone."""
        zf = self.build()
        self.assertEqual(self.doc(zf, "001-event.json")["race"]["contactRules"],
                         session.CONTACT_RULES_EQUAL_GHOSTS)

    def test_races_have_normal_contact(self):
        zf = self.build()
        self.assertEqual(self.doc(zf, "002-event.json")["race"]["contactRules"],
                         session.CONTACT_RULES_NORMAL)

    def test_every_quali_and_race_across_the_heat(self):
        zf = self.build()
        for i in range(1, 9):
            race = self.doc(zf, f"{i:03d}-event.json")["race"]
            if i % 2:
                self.assertEqual(race["contactRules"],
                                 session.CONTACT_RULES_EQUAL_GHOSTS, f"event {i}")
            else:
                self.assertEqual(race["startingOrder"],
                                 session.STARTING_ORDER_LAST_EVENT, f"event {i}")
                self.assertEqual(race["contactRules"],
                                 session.CONTACT_RULES_NORMAL, f"event {i}")

    def test_solo_race_does_not_turn_into_a_hotlap(self):
        zf = self.build()
        self.assertFalse(self.doc(zf, "002-event.json")["race"]["alwaysHotlapWhenAlone"])


class TestBots(BuilderHarness):
    def test_ai_fill_is_applied_to_every_event(self):
        zf = self.build(ai_fill=6)
        for i in range(1, 9):
            self.assertEqual(self.doc(zf, f"{i:03d}-ai.json")["aiFill"], 6)

    def test_bots_can_be_switched_off(self):
        zf = self.build(ai_fill=0)
        self.assertEqual(self.doc(zf, "001-ai.json")["aiFill"], 0)

    def test_parts_bin_ai_settings_survive(self):
        zf = self.build(ai_fill=8)
        ai = self.doc(zf, "001-ai.json")
        # The parts bin was moved off McVizn's Custom1 group on 2026-08-11:
        # bots run at Medium and humans start on a normal grid slot.
        self.assertEqual(ai["aiSkill"], 3)
        self.assertEqual(ai["aiClanTag"], "BOT")
        self.assertEqual(ai["humanStartPosition"], 0)

    def test_config_wins_over_the_parts_bin(self):
        plan = dict(PLAN, ai={"aiSkill": 5, "aiSkillLevel1": 4})
        zf = self.build(plan, ai_fill=8)
        ai = self.doc(zf, "001-ai.json")
        self.assertEqual(ai["aiSkill"], 5)
        self.assertEqual(ai["aiSkillLevel1"], 4)
        # Everything the config stays silent about keeps the export's value.
        self.assertEqual(ai["aiClanTag"], "BOT")
        self.assertTrue(ai["shuffleOrder"])


class TestCarPool(BuilderHarness):
    """One car per race (André, 2026-08-11), so vehicles.json is per event."""

    VOZZER = "17xxzrmve5gb-3868ch8"
    MCTOPPER = "128pn7m9fecb-32z2vmh"

    def plan_with_cars(self):
        rounds = [dict(r) for r in PLAN["rounds"]]
        rounds[0].update(vehicle="VoZzer", vehicle_guid=self.VOZZER)
        rounds[1].update(vehicle="McTopper v1", vehicle_guid=self.MCTOPPER)
        rounds[2].update(vehicle="VoZzer", vehicle_guid=self.VOZZER)
        rounds[3].update(vehicle="McTopper v1", vehicle_guid=self.MCTOPPER)
        return dict(PLAN, rounds=rounds)

    def test_each_race_gets_its_own_car(self):
        zf = self.build(self.plan_with_cars())
        from td import guid
        seen = [guid.from_doc(self.doc(zf, f"{i:03d}-vehicles.json")
                              ["possibleVehicles"][0]["m_guid"])
                for i in range(1, 9)]
        # Qualifying and race of one round share the car; the rounds alternate.
        self.assertEqual(seen, [self.VOZZER, self.VOZZER,
                                self.MCTOPPER, self.MCTOPPER,
                                self.VOZZER, self.VOZZER,
                                self.MCTOPPER, self.MCTOPPER])

    def test_the_rest_of_the_vehicle_template_is_kept(self):
        zf = self.build(self.plan_with_cars())
        doc = self.doc(zf, "001-vehicles.json")
        self.assertEqual(doc["selectionType"], self.parts.vehicles["selectionType"])
        self.assertEqual(len(doc["possibleVehicles"]), 1)

    def test_without_a_car_the_template_is_used_unchanged(self):
        zf = self.build()
        self.assertEqual(self.doc(zf, "001-vehicles.json"), self.parts.vehicles)

    def test_drafting_follows_the_car_not_the_heat(self):
        plan = self.plan_with_cars()
        plan["drafting"] = {"draftingSpeedEffect": 18}
        plan["rounds"][1]["drafting"] = {"draftingSpeedEffect": 14}
        zf = self.build(plan)
        self.assertEqual(self.doc(zf, "001-event.json")["drafting"]
                         ["draftingSpeedEffect"], 18)
        self.assertEqual(self.doc(zf, "003-event.json")["drafting"]
                         ["draftingSpeedEffect"], 14)


class TestTracksWithoutParts(BuilderHarness):
    """A track McVizn never exported can still be raced."""

    NEW_TRACK = {"track": "Nordschleife", "track_guid": "kmhb9dgbac3-2m6dead",
                 "laps": 3}

    def test_level_entry_is_built_from_the_guid(self):
        zf = self.build(dict(PLAN, rounds=[self.NEW_TRACK]))
        level = self.doc(zf, "001-level.json")
        self.assertEqual(level["name"], "Nordschleife")
        from td import guid
        self.assertEqual(guid.from_doc(level["guid"]), self.NEW_TRACK["track_guid"])

    def test_camera_falls_back_to_the_default(self):
        zf = self.build(dict(PLAN, rounds=[self.NEW_TRACK]))
        cam = camfile.decode(zf.read("001-camera5.cam"))
        self.assertAlmostEqual(cam["distance"], session.DEFAULT_CAMERA["distance"])
        self.assertEqual(cam["cameraPosition"], 0)

    def test_the_configured_default_camera_wins(self):
        plan = dict(PLAN, rounds=[self.NEW_TRACK],
                    default_camera_settings={"distance": 200.0, "fov": 30.0})
        zf = self.build(plan)
        cam = camfile.decode(zf.read("001-camera5.cam"))
        self.assertAlmostEqual(cam["distance"], 200.0)
        self.assertAlmostEqual(cam["fov"], 30.0, places=4)

    def test_a_camera_can_be_borrowed_from_another_track(self):
        rnd = dict(self.NEW_TRACK, camera_from="Jonno Island v1.0")
        zf = self.build(dict(PLAN, rounds=[rnd]))
        borrowed = camfile.decode(zf.read("001-camera5.cam"))
        jonno = self.parts.camera_props("Jonno Island v1.0")
        self.assertEqual(borrowed, jonno)

    def test_a_track_without_parts_and_without_guid_is_rejected_loudly(self):
        plan = dict(PLAN, rounds=[{"track": "Nürburgring", "laps": 5}])
        with self.assertRaises(ValueError) as ctx:
            self.build(plan)
        self.assertIn("Nürburgring", str(ctx.exception))


class TestCameraOverrides(BuilderHarness):
    """What the admin panel writes into the config wins over the export."""

    def test_config_values_override_the_exported_camera(self):
        rounds = [dict(PLAN["rounds"][0], camera_settings={"distance": 140.0})]
        zf = self.build(dict(PLAN, rounds=rounds))
        cam = camfile.decode(zf.read("001-camera5.cam"))
        self.assertAlmostEqual(cam["distance"], 140.0)
        # Everything else still comes from McVizn's file.
        jonno = self.parts.camera_props("Jonno Island v1.0")
        self.assertAlmostEqual(cam["horizontalAngle"], jonno["horizontalAngle"])
        self.assertAlmostEqual(cam["fov"], jonno["fov"])

    def test_a_full_readback_of_the_export_changes_nothing(self):
        """Encoding the decoded values must reproduce the file byte for byte.

        This is what makes it safe for the panel to store complete camera
        settings: a save that changes nothing may not change the camera.
        """
        for name in self.parts.tracks:
            rnd = {"track": name, "laps": 5,
                   "camera_settings": self.parts.camera_props(name)}
            data, source = session.resolve_camera(rnd, self.parts)
            self.assertEqual(data, self.parts.camera_bytes(name), name)
            self.assertIn("config", source)


class TestGuards(BuilderHarness):

    def test_empty_plan_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build({"rounds": []})

    def test_archive_is_written_atomically(self):
        self.build()
        self.assertTrue(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.out + ".tmp"))

    def test_every_exported_track_is_available(self):
        # Distant Island and Kemora joined the parts bin on 2026-08-11.
        self.assertEqual(len(self.parts.tracks), 8)
        for name in ("Jonno Island v1.0", "E.V.M.C. V1", "Maple Ridge v1.1",
                     "CSup Sugar Hill V1.0", "CSup - Lost Lagoons v1",
                     "Buffalo Hill - Rallycross v1.0", "Distant Island",
                     "Kemora 1983 v1.0"):
            self.assertTrue(self.parts.has(name), name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
