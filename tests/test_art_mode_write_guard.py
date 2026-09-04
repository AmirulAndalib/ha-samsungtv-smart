"""Art-mode writes: panel truth first, no repeat of a write that did not take.

Two layers. The pure guard is exercised directly with a fake clock; the
integration points are checked structurally, since media_player.py and
switch.py cannot be imported without Home Assistant.
"""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "samsungtv_smart"


def _load_guard_module():
    spec = importlib.util.spec_from_file_location(
        "art_mode_guard_under_test", ROOT / "art_mode_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard_mod = _load_guard_module()
ArtModeWriteGuard = guard_mod.ArtModeWriteGuard
ArtModeWriteSuppressed = guard_mod.ArtModeWriteSuppressed


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class GuardTest(unittest.TestCase):
    """The memory of unverified writes."""

    def setUp(self):
        self.clock = _Clock()
        self.guard = ArtModeWriteGuard(cooldown=60.0, clock=self.clock)

    def test_first_write_is_always_allowed(self):
        self.guard.check(True)
        self.guard.check(False)

    def test_a_verified_write_never_blocks_the_next_one(self):
        self.guard.record_verified(True)
        self.clock.now += 1
        self.guard.check(True)

    def test_an_unverified_write_blocks_the_same_intent_inside_the_cooldown(self):
        self.guard.record_unverified(True)
        self.clock.now += 30
        with self.assertRaises(ArtModeWriteSuppressed) as ctx:
            self.guard.check(True)
        self.assertEqual(ctx.exception.turn_on, True)
        self.assertAlmostEqual(ctx.exception.since, 30.0)

    def test_the_other_intent_is_not_blocked(self):
        # art on failed; the user asking for art OFF is a different request.
        self.guard.record_unverified(True)
        self.clock.now += 5
        self.guard.check(False)

    def test_the_block_lifts_when_the_cooldown_elapses(self):
        self.guard.record_unverified(True)
        self.clock.now += 61
        self.guard.check(True)
        # ...and the stale record is gone, not merely ignored.
        self.assertIsNone(self.guard.pending(True))

    def test_a_later_verified_write_clears_an_earlier_unverified_one(self):
        self.guard.record_unverified(True)
        self.guard.record_verified(True)
        self.guard.check(True)

    def test_pending_reports_age(self):
        self.assertIsNone(self.guard.pending(True))
        self.guard.record_unverified(True)
        self.clock.now += 12
        self.assertAlmostEqual(self.guard.pending(True), 12.0)

    def test_the_exception_message_names_intent_and_age(self):
        message = str(ArtModeWriteSuppressed(True, 42.0))
        self.assertIn("'on'", message)
        self.assertIn("42s", message)

    def test_guard_for_is_shared_per_entry_store(self):
        store: dict = {}
        first = guard_mod.guard_for(store)
        second = guard_mod.guard_for(store)
        self.assertIs(first, second)
        self.assertIsNot(first, guard_mod.guard_for({}))


SWITCH = (ROOT / "switch.py").read_text()
MEDIA_PLAYER = (ROOT / "media_player.py").read_text()
IPCONTROL = (ROOT / "api" / "ipcontrol.py").read_text()


def _block(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


class PanelTruthTest(unittest.TestCase):
    """Both writers ask the panel before writing, and read it back after."""

    def test_the_getter_reads_pictureMode_not_the_art_flag(self):
        block = _block(
            IPCONTROL,
            "    async def async_panel_shows_art",
            "    async def async_get_tv_states",
        )
        self.assertIn('self._async_request("getTVStates")', block)
        self.assertIn('== "Ambient"', block)
        self.assertNotIn('_async_request("artModeControl")', block)

    def test_switch_checks_the_panel_before_the_cooldown_and_the_write(self):
        block = _block(
            SWITCH, "    async def _set_artmode", "    async def _panel_shows_art"
        )
        panel = block.index("await self._panel_shows_art()")
        cooldown = block.index("guard.check(turn_on)")
        write = block.index("async_set_art_mode_on()")
        self.assertLess(panel, cooldown)
        self.assertLess(cooldown, write)

    def test_switch_reads_the_panel_back_after_an_ip_write(self):
        block = _block(
            SWITCH, "    async def _set_artmode", "    async def _panel_shows_art"
        )
        write = block.index("async_set_art_mode_on()")
        self.assertIn("after = await self._panel_shows_art()", block[write:])
        self.assertIn("guard.record_verified(turn_on)", block[write:])
        self.assertIn("guard.record_unverified(turn_on)", block[write:])

    def test_media_player_checks_the_panel_before_any_write_or_toggle(self):
        block = _block(
            MEDIA_PLAYER,
            "    async def _ensure_art_mode_ready",
            "    async def async_art_select_image",
        )
        panel = block.index("await self._panel_shows_art()")
        cooldown = block.index("guard.check(True)")
        ip_write = block.index("async_set_art_mode_on()")
        power = block.index("await self.async_turn_on()")
        self.assertLess(panel, cooldown)
        self.assertLess(cooldown, ip_write)
        self.assertLess(ip_write, power)

    def test_media_player_reads_back_after_both_write_paths(self):
        block = _block(
            MEDIA_PLAYER,
            "    async def _ensure_art_mode_ready",
            "    async def async_art_select_image",
        )
        self.assertIn("after = await self._panel_shows_art()", block)
        self.assertIn("confirmed = await self._art_api.get_artmode()", block)


class NoPowerKeyAtArtTest(unittest.TestCase):
    """The fallback must not toggle a Frame out of Art Mode with the power key."""

    def test_power_on_is_skipped_when_the_art_channel_says_art_is_on(self):
        block = _block(
            MEDIA_PLAYER,
            "    async def _ensure_art_mode_ready",
            "    async def async_art_select_image",
        )
        guard = block.index("self._ws.artmode_status == ArtModeStatus.On")
        power = block.index("await self.async_turn_on()")
        self.assertLess(guard, power)
        self.assertIn("raise _SkipPowerOn", block[guard:power])


class RetryLoopsStopTest(unittest.TestCase):
    """A suppressed write ends the switch's retry loops with one warning."""

    def test_both_loops_handle_the_suppression_before_the_generic_except(self):
        for name in ("async_turn_on", "async_turn_off"):
            block = _block(
                SWITCH,
                f"    async def {name}(self, **kwargs",
                "        # All retries failed",
            )
            suppressed = block.index("except ArtModeWriteSuppressed")
            generic = block.index("except Exception as ex")
            self.assertLess(suppressed, generic, name)
            self.assertIn("return", block[suppressed:generic])


if __name__ == "__main__":
    unittest.main()
