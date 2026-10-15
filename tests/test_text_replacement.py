import importlib.util
import json
import tempfile
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "text_replacement", Path(__file__).resolve().parents[1] / "input-pilot-text-replacement.py")
replacement = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = replacement
spec.loader.exec_module(replacement)


class NumericReplacementTests(unittest.TestCase):
    def test_prefixed_invoice_number_keeps_direct_input(self):
        with patch.object(replacement, "run_ydotool") as send, \
             patch.object(replacement, "_clipboard_paste") as paste:
            replacement.type_text("R20261015", None)
        paste.assert_not_called()
        events = send.call_args.args[0][2:]
        self.assertEqual(events[:4], ["42:1", "19:1", "19:0", "42:0"])
        self.assertEqual("".join(replacement.CHAR_KEYS[int(event.split(":")[0])]
                                 for event in events[4::2]), "20261015")

    def test_invoice_number_is_typed_without_touching_clipboard(self):
        with patch.object(replacement, "run_ydotool") as send, \
             patch.object(replacement, "_clipboard_paste") as paste:
            replacement.type_text("20261015", "/tmp/test-socket")
        paste.assert_not_called()
        command, socket = send.call_args.args
        self.assertEqual(socket, "/tmp/test-socket")
        codes = [int(event.split(":")[0]) for event in command[2::2]]
        self.assertEqual("".join(replacement.CHAR_KEYS[code] for code in codes), "20261015")
        self.assertEqual(command[2:], [event for code in codes for event in (f"{code}:1", f"{code}:0")])

    def test_leading_zeroes_are_preserved(self):
        with patch.object(replacement, "run_ydotool") as send:
            replacement.type_text("00123", None)
        self.assertEqual(send.call_args.args[0][2:6], ["11:1", "11:0", "11:1", "11:0"])

    def test_unicode_and_multiline_text_keep_clipboard_transport(self):
        with patch.object(replacement, "run_ydotool") as send, \
             patch.object(replacement, "_clipboard_paste") as paste:
            replacement.type_text("Grüße{enter}20261015", None)
        self.assertEqual([call.args[0] for call in paste.call_args_list], ["Grüße", "20261015"])
        send.assert_called_once_with(["key", "42:1", "28:1", "28:0", "42:0"], None)


class DateFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "replacement_tray_test", Path(__file__).resolve().parents[1] / "wayland-automation-tray.py")
        cls.tray = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.tray
        spec.loader.exec_module(cls.tray)

    def test_prefixed_format_survives_save_load_and_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "replacements.json"
            with patch.object(self.tray, "TEXT_REPLACEMENTS_FILE", config), \
                 patch.object(replacement, "CONFIG_FILE", config):
                self.tray.save_text_replacements([
                    {"trigger": "rnr.", "replacement": "Ryyyymmdd", "enabled": True}])
                self.assertEqual(json.loads(config.read_text())[0]["date_format"], "Ryyyymmdd")
                self.assertEqual(self.tray.load_text_replacements()[-1]["date_format"], "Ryyyymmdd")
                entry = next(x for x in replacement.load_replacements() if x.trigger == "rnr.")
                with patch.object(replacement, "datetime") as clock:
                    clock.now.return_value = datetime(2026, 10, 15)
                    self.assertEqual(replacement.resolve_replacement(entry), "R20261015")

    def test_regular_text_is_not_misclassified_as_date(self):
        for text in ("Address", "Summary", "R", "Hello", "Send yyyy to me", "20261015"):
            with self.subTest(text=text):
                self.assertFalse(self.tray._is_date_format(text))
        for text in ("dd.mm.yyyy", "yyyy_mm_dd", "Ryyyymmdd", "INVyyyymmddEU", "yy"):
            with self.subTest(text=text):
                self.assertTrue(self.tray._is_date_format(text))


class CellNavigationTests(unittest.TestCase):
    def setUp(self):
        with patch.object(replacement, "load_replacements", return_value=[
                replacement.Replacement("rnr.", "", "%Y%m%d")]), \
             patch.object(replacement, "load_mouse_shortcuts", return_value=[]):
            self.engine = replacement.ReplacementEngine(None)

    def test_trigger_matches_after_moving_to_another_cell(self):
        for key in replacement.CURSOR_KEYS:
            with self.subTest(key=key):
                self.engine.buffer = "previouscell"
                self.engine.update_buffer(key)
                for code in (replacement.ecodes.KEY_R, replacement.ecodes.KEY_N,
                             replacement.ecodes.KEY_R, replacement.ecodes.KEY_DOT,
                             replacement.ecodes.KEY_SPACE):
                    self.engine.update_buffer(code)
                self.assertEqual(self.engine.matching_replacement().trigger, "rnr.")

    def test_trigger_inside_existing_word_still_does_not_match(self):
        self.engine.buffer = "otherrnr. "
        self.assertIsNone(self.engine.matching_replacement())


if __name__ == "__main__":
    unittest.main()
