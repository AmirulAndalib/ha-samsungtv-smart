"""async_panel_shows_art must not trust a stale pictureMode from a dark panel.

A Frame in standby still answers getTVStates with a stale pictureMode (usually
"Ambient"). async_panel_shows_art is the signal the art-mode write guards
consult before writing: if it reads "art on" for a powered-off panel, the guard
concludes the TV is already in Art Mode and refuses to wake it — so selecting
art or turning the switch on silently does nothing. The sibling getter
async_get_art_mode already checks PowerState first for exactly this reason; this
pins the same guard on async_panel_shows_art.

ipcontrol.py imports cleanly on its own, but pulling it through the package
needs Home Assistant, so the guard is checked structurally on the source.
"""

from pathlib import Path
import unittest

IPCONTROL = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
    / "ipcontrol.py"
).read_text()


def _method(name: str) -> str:
    start = IPCONTROL.index(f"    async def {name}(")
    nxt = IPCONTROL.index("\n    async def ", start + 1)
    return IPCONTROL[start:nxt]


class PanelShowsArtPowerGuardTest(unittest.TestCase):
    def setUp(self):
        self.block = _method("async_panel_shows_art")

    def test_power_state_is_checked_before_reading_picture_mode(self):
        power = self.block.index('async_get_power_state() == "powerOff"')
        read = self.block.index('_async_request("getTVStates")')
        self.assertLess(power, read)

    def test_a_powered_off_panel_returns_without_trusting_ambient(self):
        head = self.block[: self.block.index('_async_request("getTVStates")')]
        self.assertIn('if await self.async_get_power_state() == "powerOff":', head)
        self.assertIn("return None", head)

    def test_it_still_reports_ambient_when_powered(self):
        self.assertIn('return mode == "Ambient"', self.block)


if __name__ == "__main__":
    unittest.main()
