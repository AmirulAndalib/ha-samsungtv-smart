"""A Frame that wakes straight into Art Mode is not a stale reading.

On 192.168.1.31 an automation asks for Art Mode every 20 min. The Frame is in
standby (motion timer), so the switch powers it on. Frames resume Art Mode on
wake, so the panel already shows art when the switch checks it. That used to
log "the art-mode reading was stale" at WARNING on every wake (~72/day). After
our own power-on it is now INFO; the stale WARNING stays for a TV that was
already on.
"""

from pathlib import Path
import unittest

SWITCH = (
    Path(__file__).parents[1] / "custom_components" / "samsungtv_smart" / "switch.py"
).read_text()


class ArtOnAfterWakeTest(unittest.TestCase):
    def setUp(self):
        start = SWITCH.index("    async def _set_artmode(")
        self.block = SWITCH[start : SWITCH.index("\n    async def ", start + 10)]

    def test_signature_takes_after_power_on(self):
        self.assertIn("after_power_on: bool = False", self.block)

    def test_info_after_our_power_on_warning_otherwise(self):
        info = self.block.index("if after_power_on and turn_on:")
        self.assertIn("woke directly into Art Mode", self.block[info:])
        self.assertIn("the art-mode reading was stale", self.block[info:])

    def test_turn_on_passes_tv_was_off(self):
        self.assertIn("True, after_power_on=tv_was_off", SWITCH)


if __name__ == "__main__":
    unittest.main()
