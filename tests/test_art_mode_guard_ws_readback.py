"""A confirmed WebSocket art-mode write must not count as "did not take".

#290 (QE55LS03B, no IP Control): turning Art Mode on, off, then on again
within 60 s was refused with "art mode 'on' was already written 31s ago and
did not take", although the first ON had been confirmed by the TV's own
art_mode_changed broadcast and logged as "Art Mode turned ON".

Cause: the WebSocket branch of _set_artmode recorded every successful write as
UNverified, and the caller never called record_verified on its success path,
so the record stood for the full cooldown. Only TVs with IP Control escaped it,
because their panel read-back cleared the record.

The branch now reads the art channel's own art_mode back — what the TV's
broadcast sets — and records verified or unverified accordingly. Checked on the
source (switch.py needs Home Assistant to import) plus the guard itself, which
is pure Python.
"""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "samsungtv_smart"
SWITCH = (ROOT / "switch.py").read_text()
sys.path.insert(0, str(ROOT))
from art_mode_guard import ArtModeWriteGuard, ArtModeWriteSuppressed  # noqa: E402


class WsBranchReadsBackTest(unittest.TestCase):
    def setUp(self):
        start = SWITCH.index(
            "        result = await self._art_api.set_artmode(turn_on)"
        )
        self.block = SWITCH[start : start + 1400]

    def test_it_records_verified_when_the_tv_confirms(self):
        self.assertIn("if self._art_api.art_mode is turn_on:", self.block)
        gate = self.block.index("if self._art_api.art_mode is turn_on:")
        verified = self.block.index("guard.record_verified(turn_on)", gate)
        unverified = self.block.index("guard.record_unverified(turn_on)", gate)
        self.assertLess(gate, verified)
        self.assertLess(verified, unverified)

    def test_the_unconditional_unverified_record_is_gone(self):
        # The old shape recorded unverified with no read-back at all.
        self.assertNotIn(
            "            # The WebSocket path has no panel read-back here",
            SWITCH,
        )


class GuardSemanticsTest(unittest.TestCase):
    """The reported sequence, against the real guard."""

    def setUp(self):
        self.t = 0.0
        self.guard = ArtModeWriteGuard(clock=lambda: self.t)

    def _write(self, turn_on, confirmed):
        self.guard.check(turn_on)
        if confirmed:
            self.guard.record_verified(turn_on)
        else:
            self.guard.record_unverified(turn_on)

    def test_on_off_on_within_the_cooldown_is_allowed_when_confirmed(self):
        self._write(True, confirmed=True)
        self.t += 15
        self._write(False, confirmed=True)
        self.t += 16  # 31 s after the first ON — the reported failure point
        self._write(True, confirmed=True)  # must not raise

    def test_an_unconfirmed_repeat_is_still_refused(self):
        # The loop the guard exists to stop is untouched.
        self._write(True, confirmed=False)
        self.t += 31
        with self.assertRaises(ArtModeWriteSuppressed):
            self._write(True, confirmed=False)

    def test_the_cooldown_still_lapses(self):
        self._write(True, confirmed=False)
        self.t += 61
        self._write(True, confirmed=False)  # must not raise


if __name__ == "__main__":
    unittest.main()
