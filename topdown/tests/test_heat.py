"""Heat composition and scoring tests.

Track names, GUIDs and AI-line filenames are the real ones from the topdown
server (resolved live on 2026-07-31).
"""

import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from td import heat  # noqa: E402

VOZZER = "17xxzrmve5gb-3868ch8"
MCTOPPER = "128pn7m9fecb-32z2vmh"

TRACKS = [
    {"name": "Buffalo Hill - Rallycross v1.0", "guid": "z1s768q5723-2z9rhj7",
     "laps": 10, "type": "Rallycross", "pit": True},
    {"name": "CSup - Lost Lagoons v1", "guid": "xvf09b5nq83-2xw55w3", "laps": 10},
    {"name": "CSup Sugar Hill V1.0", "guid": "z316kaggp23-2zcdqea", "laps": 10},
    {"name": "Maple Ridge v1.1", "guid": "13ng23pntnl3-3472zvj", "laps": 10, "pit": False},
    {"name": "Jonno Island v1.0", "guid": "139k2kmmzws3-33vswqr", "laps": 10},
    {"name": "E.V.M.C. V1", "guid": "11kcwn867t23-329n370", "laps": 10},
]

REAL_AI_FILES = [
    "ai-11kcwn867t23-329n370-17xxzrmve5gb-3868ch8.aid",
    "ai-139k2kmmzws3-33vswqr-17xxzrmve5gb-3868ch8.aid",
    "ai-13ng23pntnl3-3472zvj-17xxzrmve5gb-3868ch8.aid",
    "ai-xvf09b5nq83-2xw55w3-17xxzrmve5gb-3868ch8.aid",
    "ai-z1s768q5723-2z9rhj7-17xxzrmve5gb-3868ch8.aid",
    "ai-z316kaggp23-2zcdqea-17xxzrmve5gb-3868ch8.aid",
]


class TestAILines(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for fn in REAL_AI_FILES:
            open(os.path.join(self.dir, fn), "w").close()

    def test_parses_the_real_filenames(self):
        pairs = heat.available_ai_lines(self.dir)
        self.assertEqual(len(pairs), 6)
        for t in TRACKS:
            self.assertTrue(heat.has_ai_line(pairs, t["guid"], VOZZER),
                            f"{t['name']} should have a VoZzer line")

    def test_other_car_has_no_lines(self):
        pairs = heat.available_ai_lines(self.dir)
        for t in TRACKS:
            self.assertFalse(heat.has_ai_line(pairs, t["guid"], MCTOPPER))

    def test_missing_directory_is_not_fatal(self):
        self.assertEqual(heat.available_ai_lines("/nonexistent/xyz"), set())

    def test_unrelated_files_are_ignored(self):
        open(os.path.join(self.dir, "notes.txt"), "w").close()
        open(os.path.join(self.dir, "ai-broken.aid"), "w").close()
        self.assertEqual(len(heat.available_ai_lines(self.dir)), 6)


class TestTrackPicking(unittest.TestCase):
    def test_picks_four_distinct_tracks(self):
        rng = random.Random(7)
        for _ in range(200):
            picked = heat.pick_tracks(TRACKS, 4, rng)
            self.assertEqual(len(picked), 4)
            names = [t["name"] for t in picked]
            self.assertEqual(len(set(names)), 4, "tracks within a heat must differ")

    def test_zero_weight_disables_a_track(self):
        rng = random.Random(1)
        tracks = [dict(t) for t in TRACKS]
        tracks[0]["weight"] = 0
        for _ in range(100):
            names = [t["name"] for t in heat.pick_tracks(tracks, 4, rng)]
            self.assertNotIn("Buffalo Hill - Rallycross v1.0", names)

    def test_fewer_tracks_than_requested_still_yields_a_heat(self):
        rng = random.Random(1)
        picked = heat.pick_tracks(TRACKS[:2], 4, rng)
        self.assertEqual(len(picked), 2)

    def test_empty_pool(self):
        self.assertEqual(heat.pick_tracks([], 4, random.Random(1)), [])


class TestLaps(unittest.TestCase):
    def test_bonus_never_reduces_lap_count(self):
        rng = random.Random(3)
        track = {"laps": 10}
        seen = set()
        for _ in range(500):
            n = heat.laps_for(track, rng, 20)
            self.assertGreaterEqual(n, 10, "must never run fewer laps than configured")
            self.assertLessEqual(n, 12, "20% of 10 laps is at most 2 extra")
            seen.add(n)
        self.assertGreater(len(seen), 1, "the bonus should actually vary")

    def test_zero_bonus_is_exact(self):
        rng = random.Random(3)
        self.assertEqual(heat.laps_for({"laps": 8}, rng, 0), 8)

    def test_missing_lap_count_falls_back_to_one(self):
        self.assertGreaterEqual(heat.laps_for({}, random.Random(1), 20), 1)

    def test_a_track_may_set_its_own_variance(self):
        rng = random.Random(3)
        # A long lap wants a smaller swing than the global 20% would give.
        track = {"laps": 10, "lap_bonus_pct": 10}
        for _ in range(200):
            self.assertLessEqual(heat.laps_for(track, rng, 20), 11)

    def test_a_track_can_switch_the_variance_off(self):
        rng = random.Random(3)
        track = {"laps": 10, "lap_bonus_pct": 0}
        self.assertEqual({heat.laps_for(track, rng, 20) for _ in range(50)}, {10})

    def test_nonsense_variance_falls_back_to_the_global_one(self):
        self.assertEqual(heat.lap_bonus_pct({"lap_bonus_pct": "später"}, 20), 20)
        self.assertEqual(heat.lap_bonus_pct({"lap_bonus_pct": None}, 20), 20)
        self.assertEqual(heat.lap_bonus_pct({}, 20), 20)


class TestVehiclePool(unittest.TestCase):
    POOL = [{"name": "VoZzer", "guid": VOZZER},
            {"name": "McTopper v1", "guid": MCTOPPER}]

    def test_an_old_single_car_config_still_works(self):
        pool = heat.vehicle_pool({"vehicle": "VoZzer", "vehicle_guid": VOZZER})
        self.assertEqual([v["name"] for v in pool], ["VoZzer"])

    def test_the_pool_wins_over_the_single_car(self):
        cfg = {"vehicle": "VoZzer", "vehicle_guid": VOZZER, "vehicles": self.POOL}
        self.assertEqual(len(heat.vehicle_pool(cfg)), 2)

    def test_both_cars_are_used_across_a_heat(self):
        picks = heat.pick_vehicles(self.POOL, 4, random.Random(1))
        self.assertEqual(len(picks), 4)
        self.assertEqual(sorted(p["name"] for p in picks).count("VoZzer"), 2,
                         "the bag is refilled, so four races use each car twice")

    def test_zero_weight_disables_a_car(self):
        pool = [dict(self.POOL[0], weight=0), dict(self.POOL[1], weight=1)]
        picks = heat.pick_vehicles(pool, 4, random.Random(1))
        self.assertTrue(all(p["name"] == "McTopper v1" for p in picks))

    def test_a_single_car_is_simply_used_every_race(self):
        picks = heat.pick_vehicles(self.POOL[:1], 3, random.Random(1))
        self.assertEqual([p["name"] for p in picks], ["VoZzer"] * 3)

    def test_no_cars_at_all(self):
        self.assertEqual(heat.pick_vehicles([], 4, random.Random(1)), [])
        self.assertEqual(heat.vehicle_pool({}), [])


class TestHeatPlan(unittest.TestCase):
    def _config(self, **over):
        cfg = {"tracks": TRACKS, "vehicle": "VoZzer", "vehicle_guid": VOZZER,
               "tracks_per_heat": 4, "lap_bonus_max_pct": 20, "quali": {"laps": 1}}
        cfg.update(over)
        return cfg

    def test_plan_shape(self):
        ai = heat.available_ai_lines_from_pairs = {(t["guid"].lower(), VOZZER.lower()) for t in TRACKS}
        plan = heat.build_heat_plan(self._config(), random.Random(5), ai)
        self.assertEqual(len(plan["rounds"]), 4)
        self.assertEqual(plan["vehicle"], "VoZzer")
        self.assertEqual(plan["quali_laps"], 1)
        for rnd in plan["rounds"]:
            self.assertTrue(rnd["ai_lines"], "all six tracks have VoZzer lines")
            self.assertGreaterEqual(rnd["laps"], 10)

    def test_plan_flags_missing_ai_lines(self):
        plan = heat.build_heat_plan(self._config(vehicle_guid=MCTOPPER),
                                    random.Random(5), set())
        self.assertTrue(all(not r["ai_lines"] for r in plan["rounds"]),
                        "McTopper has no lines yet -- races run without bots")

    def test_every_round_carries_its_own_car(self):
        cfg = self._config(vehicles=[{"name": "VoZzer", "guid": VOZZER},
                                     {"name": "McTopper v1", "guid": MCTOPPER}])
        plan = heat.build_heat_plan(cfg, random.Random(5), set())
        cars = [r["vehicle"] for r in plan["rounds"]]
        self.assertEqual(len(cars), 4)
        self.assertEqual(set(cars), {"VoZzer", "McTopper v1"})
        # The heat-wide value is the first round's car, for the fallback path.
        self.assertEqual(plan["vehicle"], cars[0])
        for rnd in plan["rounds"]:
            self.assertTrue(rnd["vehicle_guid"])

    def test_ai_lines_are_checked_against_the_round_s_own_car(self):
        cfg = self._config(vehicles=[{"name": "VoZzer", "guid": VOZZER},
                                     {"name": "McTopper v1", "guid": MCTOPPER}])
        # Only the VoZzer has lines here.
        pairs = {(t["guid"].lower(), VOZZER.lower()) for t in TRACKS}
        plan = heat.build_heat_plan(cfg, random.Random(5), pairs)
        for rnd in plan["rounds"]:
            self.assertEqual(rnd["ai_lines"], rnd["vehicle"] == "VoZzer",
                             rnd["track"])

    def test_same_seed_reproduces_the_same_heat(self):
        a = heat.build_heat_plan(self._config(), random.Random(42), set())
        b = heat.build_heat_plan(self._config(), random.Random(42), set())
        self.assertEqual(a, b)


class TestScoring(unittest.TestCase):
    def test_mcvizn_point_tables(self):
        self.assertEqual([heat.points_for(p, heat.DEFAULT_RACE_POINTS) for p in range(1, 9)],
                         [10, 6, 4, 3, 2, 1, 0, 0])
        self.assertEqual([heat.points_for(p, heat.DEFAULT_QUALI_POINTS) for p in range(1, 4)],
                         [1, 0, 0])

    def test_full_heat(self):
        # Two drivers over four tracks: A wins every race, B wins every quali.
        rounds = []
        for _ in range(4):
            rounds.append({"kind": "quali", "positions": {"A": 2, "B": 1}})
            rounds.append({"kind": "race", "positions": {"A": 1, "B": 2}})
        table = heat.score_results(rounds)
        self.assertEqual(table[0]["driver"], "A")
        self.assertEqual(table[0]["points"], 40)          # 4 x 10
        self.assertEqual(table[1]["points"], 4 * 6 + 4)   # 4 x P2 + 4 quali poles

    def test_tie_is_broken_by_better_positions(self):
        # Both score 10: one win (10) versus a second and a third (6 + 4).
        rounds = [
            {"kind": "race", "positions": {"winner": 1, "steady": 2}},
            {"kind": "race", "positions": {"winner": 7, "steady": 3}},
            {"kind": "race", "positions": {"winner": 7, "steady": 7}},
            {"kind": "race", "positions": {"winner": 7, "steady": 7}},
        ]
        table = heat.score_results(rounds)
        self.assertEqual(table[0]["points"], table[1]["points"], "precondition: a real tie")
        self.assertEqual(table[0]["driver"], "winner", "more wins takes it")

    def test_bots_are_scored_like_anyone_else(self):
        rounds = [{"kind": "race", "positions": {"76561197989276622": 2, "AI Rookie": 1}}]
        table = heat.score_results(rounds)
        self.assertEqual(table[0]["driver"], "AI Rookie")

    def test_driver_who_joined_late_only_scores_what_they_drove(self):
        rounds = [
            {"kind": "race", "positions": {"early": 1}},
            {"kind": "race", "positions": {"early": 1, "late": 2}},
        ]
        table = heat.score_results(rounds)
        by_driver = {e["driver"]: e for e in table}
        self.assertEqual(by_driver["late"]["points"], 6)
        self.assertEqual(by_driver["late"]["starts"], 1)
        self.assertEqual(by_driver["early"]["starts"], 2)

    def test_empty_heat(self):
        self.assertEqual(heat.score_results([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
