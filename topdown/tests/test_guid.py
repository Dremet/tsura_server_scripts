"""GUID tests.

The numbers are the real ones out of the session parts bin: getting this wrong
would put the wrong car or the wrong track into an archive, and the server would
just refuse to load it.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from td import guid  # noqa: E402

PARTS_DIR = os.path.join(HERE, "..", "session_parts")

# Printed form -> the pair stored in the session files.
KNOWN = {
    "139k2kmmzws3-33vswqr": (39744136657499971, 3352131353),   # Jonno Island
    "1d4pxkexwfv3-3dd3b8l": (50832573759143811, 3671174420),   # Distant Island
    "17xxzrmve5gb-3868ch8": (44999705608263179, 3496227368),   # VoZzer
}


class TestKnownGuids(unittest.TestCase):
    def test_decode(self):
        for text, pair in KNOWN.items():
            self.assertEqual(guid.decode(text), pair, text)

    def test_encode(self):
        for text, (a, b) in KNOWN.items():
            self.assertEqual(guid.encode(a, b), text)

    def test_doc_round_trip(self):
        for text in KNOWN:
            self.assertEqual(guid.from_doc(guid.to_doc(text)), text)


class TestAgainstThePartsBin(unittest.TestCase):
    def test_every_exported_level_round_trips(self):
        tracks = os.path.join(PARTS_DIR, "tracks")
        for name in sorted(os.listdir(tracks)):
            with open(os.path.join(tracks, name, "level.json"),
                      encoding="utf-8-sig") as fh:
                level = json.load(fh)
            text = guid.from_doc(level["guid"])
            self.assertEqual(guid.to_doc(text), level["guid"], level["name"])

    def test_the_exported_vehicle_round_trips(self):
        with open(os.path.join(PARTS_DIR, "vehicles.json"),
                  encoding="utf-8-sig") as fh:
            doc = json.load(fh)
        m_guid = doc["possibleVehicles"][0]["m_guid"]
        self.assertEqual(guid.to_doc(guid.from_doc(m_guid)), m_guid)


class TestRejects(unittest.TestCase):
    def test_the_alphabet_leaves_out_the_confusable_letters(self):
        for ch in "iouy":
            self.assertNotIn(ch, guid.ALPHABET)
            with self.assertRaises(ValueError):
                guid.decode_part(ch)

    def test_a_missing_half_is_not_a_guid(self):
        for text in ("139k2kmmzws3", "", "a-b-c"):
            with self.assertRaises(ValueError):
                guid.decode(text)

    def test_case_does_not_matter(self):
        self.assertEqual(guid.decode("139K2KMMZWS3-33VSWQR"),
                         guid.decode("139k2kmmzws3-33vswqr"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
