"""Tests for the slow-update warning and the power probe timeout (#248).

A TV in standby leaves the network entirely, so its power probe can only end
in a timeout. DEFAULT_TIMEOUT was longer than SCAN_INTERVAL, which made every
such poll overrun by construction.
"""

from pathlib import Path
import re
import unittest

SOURCE = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "media_player.py"
).read_text()
CONST_SOURCE = (
    Path(__file__).parents[1] / "custom_components" / "samsungtv_smart" / "const.py"
).read_text()


def _number(source: str, name: str) -> float:
    match = re.search(rf"^{name} = ([0-9.]+)$", source, re.MULTILINE)
    assert match, f"{name} not found"
    return float(match.group(1))


class ProbeTimeoutTest(unittest.TestCase):
    """The probe must be able to finish inside one scan interval."""

    def test_scan_interval_is_five_seconds(self):
        match = re.search(r"^SCAN_INTERVAL = timedelta\(seconds=(\d+)\)$", SOURCE, re.M)
        self.assertTrue(match)
        self.assertEqual(int(match.group(1)), 5)

    def test_the_default_rest_timeout_still_exceeds_the_interval(self):
        """The condition that caused #248 — kept as the reason for the fix."""
        self.assertGreater(_number(CONST_SOURCE, "DEFAULT_TIMEOUT"), 5)

    def test_off_probe_timeout_fits_inside_the_scan_interval(self):
        self.assertLess(_number(SOURCE, "POWER_PROBE_OFF_TIMEOUT"), 5)

    def test_probe_timeout_is_applied_only_when_the_tv_is_not_on(self):
        block = SOURCE[SOURCE.index("    async def _check_status") :]
        block = block[: block.index("    @callback")]
        self.assertIn("POWER_PROBE_OFF_TIMEOUT", block)
        self.assertIn("if self._state == MediaPlayerState.ON", block)

    def test_load_device_info_wraps_the_call_when_a_timeout_is_given(self):
        block = SOURCE[SOURCE.index("    async def _async_load_device_info") :]
        block = block[: block.index("    def _should_poll_st")]
        self.assertIn("asyncio.wait_for(request, timeout=timeout)", block)
        self.assertIn("if timeout is not None:", block)


class SlowUpdateWarningTest(unittest.TestCase):
    """An overrun explained by the TV being off must not warn."""

    def setUp(self):
        block = SOURCE[SOURCE.index("    def _note_slow_update") :]
        self.block = block[: block.index("\n    async def _async_update")]

    def test_an_off_tv_is_logged_at_debug(self):
        head = self.block[: self.block.index("now = time.monotonic()")]
        self.assertIn("if self._state != MediaPlayerState.ON:", head)
        self.assertIn("self._log.debug(", head)
        self.assertNotIn("self._log.warning(", head)

    def test_a_reachable_tv_still_warns(self):
        self.assertIn("self._log.warning(", self.block)

    def test_warnings_are_throttled_and_report_what_they_stand_for(self):
        self.assertIn("SLOW_UPDATE_WARN_INTERVAL", self.block)
        self.assertIn("self._slow_update_suppressed += 1", self.block)
        self.assertIn("further slow updates since the last warning", self.block)

    def test_the_counter_resets_after_a_warning(self):
        tail = self.block[self.block.rindex("self._slow_update_last_warn = now") :]
        self.assertIn("self._slow_update_suppressed = 0", tail)

    def test_throttle_interval_is_long_enough_to_matter(self):
        self.assertGreaterEqual(_number(SOURCE, "SLOW_UPDATE_WARN_INTERVAL"), 60)


if __name__ == "__main__":
    unittest.main()
