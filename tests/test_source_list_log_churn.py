"""The SmartThings source-list diagnostics must only log when they change.

_update_source_list runs on every SmartThings poll and emitted three DEBUG
lines describing a list that essentially never moves: measured at ~2/min —
1,974 lines in 5.5 h on a single TV — which buries real events in a capture.
The device-info payload already got this treatment; this does the same for the
source list, keyed on a signature of what the lines actually report.

smartthings.py needs Home Assistant to import, so the wiring is checked on the
source and the dedup decision is reproduced.
"""

from pathlib import Path
import unittest

SMARTTHINGS = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
    / "smartthings.py"
).read_text()


def _update_source_list() -> str:
    start = SMARTTHINGS.index("    async def _update_source_list")
    return SMARTTHINGS[start : SMARTTHINGS.index("\n    def _log_source_list_state")]


class NoPerPollChurnTest(unittest.TestCase):
    """The per-poll path no longer emits the three unconditional lines."""

    def setUp(self):
        self.block = _update_source_list()

    def test_the_entry_and_supported_lines_are_gone_from_the_poll_path(self):
        self.assertNotIn("_update_source_list called", self.block)
        self.assertNotIn("supportedInputSources present=%s, value=%s", self.block)
        self.assertNotIn("sources loaded", self.block)

    def test_the_poll_path_delegates_to_the_change_gated_logger(self):
        self.assertIn(
            "self._log_source_list_state(has_media_input, has_supported, "
            "supported_val)",
            self.block,
        )

    def test_only_the_conditional_rest_line_remains(self):
        # The REST fallback line is guarded by a real condition (#230) and stays.
        self.assertEqual(self.block.count("self._log.debug"), 1)
        self.assertIn("reading input source via REST", self.block)


class ChangeGateTest(unittest.TestCase):
    """The logger returns early while the snapshot is unchanged."""

    def setUp(self):
        start = SMARTTHINGS.index("    def _log_source_list_state")
        self.block = SMARTTHINGS[start : SMARTTHINGS.index("\n    def ", start + 1)]

    def test_it_compares_against_the_stored_signature_and_returns(self):
        self.assertIn("if signature == self._source_list_log_state:", self.block)
        gate = self.block.index("if signature == self._source_list_log_state:")
        ret = self.block.index("return", gate)
        emit = self.block.index("self._log.debug", gate)
        self.assertLess(ret, emit)

    def test_the_signature_covers_the_reported_values(self):
        for part in (
            "has_media_input",
            "has_supported",
            "repr(supported_val)",
            "self._source_list_map",
        ):
            self.assertIn(part, self.block[: self.block.index("if signature ==")])

    def test_the_signature_is_stored_before_emitting(self):
        store = self.block.index("self._source_list_log_state = signature")
        emit = self.block.index("self._log.debug")
        self.assertLess(store, emit)

    def test_the_dedup_reproduces(self):
        def emits(signature, last):
            return signature != last

        sig = (True, True, "['dtv', 'HDMI3']", (("HDMI3", "CINEMA 60"),))
        self.assertTrue(emits(sig, None))  # first poll
        self.assertFalse(emits(sig, sig))  # steady state -> silent
        moved = (True, True, "['dtv']", (("dtv", "TV"),))
        self.assertTrue(emits(moved, sig))  # list actually changed -> logged

    def test_the_field_is_initialised(self):
        self.assertIn("self._source_list_log_state: tuple | None = None", SMARTTHINGS)


if __name__ == "__main__":
    unittest.main()
