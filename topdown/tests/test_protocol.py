"""Parser tests. The transcript lines are copied verbatim from a live capture."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from td import protocol as p  # noqa: E402


class TestLiveTranscript(unittest.TestCase):
    """Every line below was actually observed on 2026-07-31."""

    def test_first_line_with_bom(self):
        self.assertIsNone(p.parse_line("﻿Script client connected."))

    def test_join(self):
        ev = p.parse_line("Player connected: [VSR] Dremet (Rubber Knight)")
        self.assertEqual(ev["kind"], p.JOIN)
        self.assertEqual(ev["name"], "[VSR] Dremet")
        self.assertFalse(ev["spectator"])

    def test_join_from_log_file_has_colour_tags(self):
        ev = p.parse_line(
            "Player connected: [VSR] Dremet <color=#888844>(Track Tyrant)</color>"
        )
        self.assertEqual(ev["name"], "[VSR] Dremet")

    def test_spectator_join_is_flagged(self):
        ev = p.parse_line(
            "Spectator connected: [EXC] Shyguy1001 <color=#888844>(Gearshift Guru)</color>"
        )
        self.assertEqual(ev["kind"], p.JOIN)
        self.assertTrue(ev["spectator"])

    def test_chat_on_script_port_has_asterisks(self):
        ev = p.parse_line("**<[VSR] Dremet>** hi")
        self.assertEqual((ev["kind"], ev["name"], ev["text"]), (p.CHAT, "[VSR] Dremet", "hi"))

    def test_chat_in_log_file_has_none(self):
        ev = p.parse_line("<[JDR] Juanen> im testing all details")
        self.assertEqual((ev["name"], ev["text"]), ("[JDR] Juanen", "im testing all details"))

    def test_who_reply(self):
        self.assertEqual(p.parse_line("Players (1):")["count"], 1)
        ev = p.parse_line(" - [VSR] Dremet (76561197989276622)")
        self.assertEqual((ev["kind"], ev["name"], ev["steam_id"]),
                         (p.WHO_ENTRY, "[VSR] Dremet", 76561197989276622))

    def test_empty_who_reply(self):
        self.assertEqual(p.parse_line("Players (0):")["count"], 0)

    def test_leave(self):
        ev = p.parse_line("[VSR] Dremet disconnected.")
        self.assertEqual((ev["kind"], ev["name"]), (p.LEAVE, "[VSR] Dremet"))

    def test_event_upcoming(self):
        ev = p.parse_line("Event 1 / 4 is about to start in Misano World Circuit V2.00.")
        self.assertEqual((ev["index"], ev["total"], ev["track"]),
                         (1, 4, "Misano World Circuit V2.00"))

    def test_stamped_state_lines(self):
        self.assertEqual(p.parse_line("2026-07-31 14:04:57: Event started.")["kind"], p.EVENT_STARTED)
        self.assertEqual(p.parse_line("2026-07-31 14:12:05: Event ended.")["kind"], p.EVENT_ENDED)
        self.assertEqual(p.parse_line("2026-07-31 14:03:47: Session started.")["kind"], p.SESSION_STARTED)


    def test_state_lines_without_a_timestamp(self):
        """The script port sends these bare; only the log file stamps them.

        Missing this cost a whole live heat on 2026-07-31: the controller never
        counted a single finished event.
        """
        self.assertEqual(p.parse_line("Event ended.")["kind"], p.EVENT_ENDED)
        self.assertEqual(p.parse_line("Event started.")["kind"], p.EVENT_STARTED)
        self.assertEqual(p.parse_line("Session started.")["kind"], p.SESSION_STARTED)
        self.assertEqual(p.parse_line("Session ended.")["kind"], p.SESSION_ENDED)

    def test_chat_that_merely_mentions_an_event_end_is_still_chat(self):
        ev = p.parse_line("**<troll>** Event ended.")
        self.assertEqual(ev["kind"], p.CHAT)

    def test_noise_is_ignored(self):
        for line in [
            "New fastest lap: 1:38.274 by [JDR] Juanen",
            "Event starting with 1 player.",
            "Voting has started. Use /vote to see the voting options.",
            "Reloading levels and vehicles at session init.",
            "ai.aiFill = 6",
            "",
            "   ",
        ]:
            self.assertIsNone(p.parse_line(line), f"should ignore: {line!r}")


class TestAwkwardNames(unittest.TestCase):
    """Names are attacker-controlled in practice -- the parser must not fall over."""

    def test_player_literally_named_player_2(self):
        ev = p.parse_line("Player 2 disconnected.")
        self.assertEqual(ev["name"], "Player 2")

    def test_name_that_is_only_a_title(self):
        # Stripping the trailing "(...)" must not leave an empty name.
        ev = p.parse_line("Player connected: (Anonymous)")
        self.assertEqual(ev["name"], "(Anonymous)")

    def test_chat_containing_a_fake_join_line(self):
        ev = p.parse_line("**<troll>** Player connected: [VSR] Dremet (Rubber Knight)")
        self.assertEqual(ev["kind"], p.CHAT)
        self.assertEqual(ev["name"], "troll")

    def test_chat_containing_a_fake_leave_line(self):
        ev = p.parse_line("**<troll>** [VSR] Dremet disconnected.")
        self.assertEqual(ev["kind"], p.CHAT)

    def test_name_with_brackets_keeps_clan_tag(self):
        ev = p.parse_line("Player connected: [VSR] S ΣaⓁ hßD (Race Knight)")
        self.assertEqual(ev["name"], "[VSR] S ΣaⓁ hßD")


class TestCommands(unittest.TestCase):
    def test_both_prefixes_work(self):
        self.assertEqual(p.parse_command("/bot 14"), ("bot", ["14"]))
        self.assertEqual(p.parse_command("!bot 14"), ("bot", ["14"]))

    def test_case_insensitive(self):
        self.assertEqual(p.parse_command("/BOT 14"), ("bot", ["14"]))

    def test_multi_word(self):
        self.assertEqual(p.parse_command("/restart tdheat"), ("restart", ["tdheat"]))

    def test_no_args(self):
        self.assertEqual(p.parse_command("!bots"), ("bots", []))

    def test_plain_chat_is_not_a_command(self):
        for text in ["hello", "1/2 of us want a restart", "", "  ", "/", "//x"]:
            self.assertIsNone(p.parse_command(text), f"should not parse: {text!r}")


class TestQuoting(unittest.TestCase):
    def test_plain_name(self):
        self.assertEqual(p.quoted("Jonno Island v1"), "'Jonno Island v1'")

    def test_name_with_apostrophe_falls_back_to_double_quotes(self):
        self.assertEqual(p.quoted("Mazda MX-5 Cup '16"), '"Mazda MX-5 Cup \'16"')

    def test_name_with_both_quote_kinds_is_rejected(self):
        with self.assertRaises(ValueError):
            p.quoted("weird \"name\" with 'both'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
