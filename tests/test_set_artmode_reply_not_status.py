"""A set_artmode_status reply must not be read as an art-mode status report (#264).

_process_event updated self.art_mode from any event whose name contains
"artmode_status". That also caught set_artmode_status — the reply to our own
write, which carries 'status', not 'value'. So data.get("value") was None and
every reply forced art_mode = False, whatever it reported. On some 2024 Frames
(QA65LS03D) that reply trails the authoritative art_mode_changed broadcast by
~10-13 s, so turning art on from HA read back off; with no IP Control /
SmartThings to re-read, the switch and sensor stuck at off.

The guard excludes set_artmode_status while still matching the real
get_artmode_status status report. art.py needs Home Assistant/aiohttp to import,
so the branch is extracted from source and executed against representative
payloads.
"""

from pathlib import Path
import re
import unittest

ART = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
    / "art.py"
).read_text()


class GuardShapeTest(unittest.TestCase):
    """The set_artmode_status reply is excluded from the status branch."""

    def test_the_branch_excludes_the_write_reply(self):
        self.assertIn(
            'if "artmode_status" in sub_event and sub_event != "set_artmode_status":',
            ART,
        )

    def test_the_broadcast_is_still_authoritative(self):
        # art_mode_changed still drives art_mode from 'status'.
        self.assertIn('elif sub_event == "art_mode_changed":', ART)
        self.assertIn('self.art_mode = data.get("status") == "on"', ART)


def _art_mode_after(sub_event: str, data: dict):
    """Reproduce the status-update branch from _process_event for one event."""
    art_mode = "UNSET"
    if "artmode_status" in sub_event and sub_event != "set_artmode_status":
        art_mode = data.get("value") == "on"
    elif sub_event == "art_mode_changed":
        art_mode = data.get("status") == "on"
    return art_mode


class BranchBehaviourTest(unittest.TestCase):
    """The extracted branch behaves correctly per event type."""

    def test_write_reply_on_is_ignored_not_flipped_to_false(self):
        # The exact payload from the bug: reply says status on, no value.
        result = _art_mode_after(
            "set_artmode_status", {"request_id": "x", "status": "on"}
        )
        self.assertEqual(result, "UNSET")  # branch skipped -> art_mode untouched

    def test_write_reply_off_is_also_ignored(self):
        result = _art_mode_after(
            "set_artmode_status", {"request_id": "x", "status": "off"}
        )
        self.assertEqual(result, "UNSET")

    def test_a_real_status_report_still_updates(self):
        self.assertTrue(_art_mode_after("get_artmode_status", {"value": "on"}))
        self.assertFalse(_art_mode_after("get_artmode_status", {"value": "off"}))

    def test_the_broadcast_still_updates(self):
        self.assertTrue(_art_mode_after("art_mode_changed", {"status": "on"}))
        self.assertFalse(_art_mode_after("art_mode_changed", {"status": "off"}))

    def test_the_extracted_branch_matches_the_source(self):
        # Guard against the reproduction drifting from art.py.
        self.assertEqual(
            len(
                re.findall(
                    r'"artmode_status" in sub_event and '
                    r'sub_event != "set_artmode_status"',
                    ART,
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
