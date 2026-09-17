"""The recovery cooldown must lift as soon as the channel is healthy again (#12).

#268 added a 30 s cooldown after the timeout breaker trips, anchored to the
wedge-detection moment. On a 2020 Frame that drops the client on a fixed
~200-240 s schedule, the reconnect + ms.channel.ready land ~7 s after the wedge,
but the fixed cooldown then kept skipping requests for the rest of the 30 s —
~23 s of an already-working socket sitting idle (measured by excprocess).

Getting ms.channel.ready during (re)connect now clears _request_cooldown_until,
so recovery costs a couple of seconds, not the full window. art.py needs Home
Assistant/aiohttp to import, so the reset is pinned structurally on the source.
"""

from pathlib import Path
import unittest

ART = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
    / "art.py"
).read_text()


class CooldownClearedOnReadyTest(unittest.TestCase):
    def _connect_once(self) -> str:
        start = ART.index("    async def _connect_once(")
        return ART[start : ART.index("\n    async def ", start + 1)]

    def test_ready_branch_clears_the_cooldown(self):
        block = self._connect_once()
        ready = block.index("if event == MS_CHANNEL_READY_EVENT:")
        # Where the ready branch ends (the elif for the bare connect event).
        connect = block.index("elif event == MS_CHANNEL_CONNECT_EVENT:")
        ready_body = block[ready:connect]
        self.assertIn("self._request_cooldown_until = 0.0", ready_body)

    def test_the_bare_connect_branch_does_not_clear_it(self):
        # A bare ms.channel.connect (no ready) can be a zombie port, so it must
        # NOT lift the cooldown — only a real ready proves health.
        block = self._connect_once()
        connect = block.index("elif event == MS_CHANNEL_CONNECT_EVENT:")
        connect_body = block[connect : block.index("break", connect)]
        self.assertNotIn("_request_cooldown_until", connect_body)

    def test_the_cooldown_is_still_armed_on_a_wedge(self):
        # The lift only makes sense if the breaker still arms it in the first
        # place (regression guard for #268's behaviour).
        self.assertIn("self._request_cooldown_until = max(", ART)


if __name__ == "__main__":
    unittest.main()
