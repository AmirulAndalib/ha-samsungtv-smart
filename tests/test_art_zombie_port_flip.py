"""A wedged Art port that never answered must flip to the alternate one (#12).

Some 2020 Frames accept a bare ms.channel.connect on the plain-ws port (8001)
while the art app never becomes ready, so every request times out. Because
_connect_once "succeeded" there, each reconnect kept choosing the same dead
port and never retried the secure port (8002) that actually works — an endless
wedge/reconnect loop (excprocess's QE32LS03T, two hours in the log).

The fix tracks whether any request was answered since the current connection
was established; when a wedge trips with that still False, the port is a zombie
and _note_request_timeout flips to the alternate port before the reconnect. A
port that HAS answered is left alone. art.py needs Home Assistant/aiohttp to
import, so this is checked structurally on the source.
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


def _method(name: str) -> str:
    start = ART.index(f"    def {name}(")
    nxt = ART.index("\n    def ", start + 1)
    return ART[start:nxt]


class ResponseFlagTest(unittest.TestCase):
    """The flag tracks 'this port has actually answered'."""

    def test_a_matched_response_sets_the_flag(self):
        block = ART[ART.index("async def _wait_for_response") :]
        block = block[: block.index("\n    def _note_request_timeout")]
        # Set right where the breaker is reset on a real answer.
        answer = block.index("self._timeout_streak = 0")
        flag = block.index("self._got_response_since_connect = True")
        self.assertLess(answer, flag)

    def test_each_new_connection_resets_the_flag(self):
        block = ART[ART.index("async def _connect_once") :]
        block = block[: block.index("\n    async def close")]
        self.assertIn("self._got_response_since_connect = False", block)


class PortFlipTest(unittest.TestCase):
    """A zombie port (wedged, never answered) is swapped before reconnect."""

    def setUp(self):
        self.block = _method("_note_request_timeout")

    def test_flip_is_gated_on_no_response_since_connect(self):
        self.assertIn("if not self._got_response_since_connect:", self.block)

    def test_it_selects_the_other_port(self):
        self.assertIn(
            "alternate_port = 8001 if self._port == 8002 else 8002", self.block
        )
        self.assertIn("self._port = alternate_port", self.block)

    def test_the_flip_happens_before_the_force_close(self):
        flip = self.block.index("self._port = alternate_port")
        close = self.block.index("_force_close_ws()")
        self.assertLess(flip, close)

    def test_a_port_that_answered_is_not_flipped(self):
        # The whole flip lives under the "no response" guard, so a working port
        # that suffers a transient wedge keeps its port.
        guard = self.block.index("if not self._got_response_since_connect:")
        flip = self.block.index("self._port = alternate_port")
        self.assertLess(guard, flip)


if __name__ == "__main__":
    unittest.main()
