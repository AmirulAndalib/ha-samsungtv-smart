"""The Art port is settled once proven, and never swapped on a transient loss.

Originally (#12) a wedge with no answer always switched port, to rescue a 2020
Frame stuck on a plain-ws 8001 that accepts a bare ms.channel.connect but never
serves the art app. That rule is right only while the port is unproven: on a
Wi-Fi Frame that briefly drops off, BOTH ports look "wedged without answering",
so the switch ping-ponged — 55 flips each way in one window — and each flip also
persisted the new port, rewriting the stored value on every transient loss
(#273 follow-up).

Now: the port is discovered at connect time (open() falls back to the alternate
port when the connection itself fails), a port is *proven* the first time it
answers a request, only a proven port is persisted, and a proven port is kept
across a wedge — the exponential backoff spaces the retries instead.

art.py needs Home Assistant/aiohttp to import, so this is checked on the source.
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
    nxt = ART.index("\n    async def ", start + 1)
    return ART[start:nxt]


class UnprovenPortIsRetriedTest(unittest.TestCase):
    """A port that has never answered may still be swapped once (#12)."""

    def setUp(self):
        self.block = _method("_note_request_timeout")

    def test_the_switch_is_gated_on_the_port_being_unproven(self):
        self.assertIn(
            "if not self._got_response_since_connect "
            "and self._proven_port != self._port:",
            self.block,
        )

    def test_it_selects_the_other_port(self):
        self.assertIn(
            "alternate_port = 8001 if self._port == 8002 else 8002", self.block
        )
        self.assertIn("self._port = alternate_port", self.block)

    def test_a_speculative_switch_is_not_persisted(self):
        # _learn_port must not be reachable from the switch branch: only an
        # answered request may rewrite the stored port.
        switch = self.block[
            self.block.index("self._proven_port != self._port:") : self.block.index(
                "elif not self._got_response_since_connect:"
            )
        ]
        self.assertNotIn("_learn_port", switch)


class ProvenPortIsKeptTest(unittest.TestCase):
    """A port that has served this TV is never swapped on a transient loss."""

    def setUp(self):
        self.block = _method("_note_request_timeout")

    def test_a_proven_port_takes_the_keep_branch(self):
        self.assertIn("elif not self._got_response_since_connect:", self.block)
        keep = self.block[
            self.block.index("elif not self._got_response_since_connect:") :
        ]
        self.assertIn("keeping the port", keep)
        self.assertNotIn("self._port = alternate_port", keep)

    def test_the_decision_reproduces(self):
        def switches(got_response: bool, proven_port, port) -> bool:
            return not got_response and proven_port != port

        # 2020 Frame stuck on an unproven 8001 -> still rescued.
        self.assertTrue(switches(False, None, 8001))
        # Wi-Fi Frame whose 8002 has served it -> kept, no ping-pong.
        self.assertFalse(switches(False, 8002, 8002))
        # A channel that answered is never a port problem.
        self.assertFalse(switches(True, 8002, 8002))


class PersistOnlyWhenProvenTest(unittest.TestCase):
    def test_the_port_is_learned_on_the_first_real_answer(self):
        block = ART[ART.index("    async def _wait_for_response") :]
        block = block[: block.index("\n    def ")]
        self.assertIn("if self._proven_port != self._port:", block)
        self.assertIn("self._proven_port = self._port", block)
        self.assertIn("self._learn_port(self._port)", block)

    def test_connect_time_discovery_still_exists(self):
        # open()'s fallback to the alternate port when the CONNECTION fails is
        # the legitimate discovery path and stays.
        self.assertIn("Art API: Port %d failed, trying alternate port %d", ART)

    def test_connect_time_discovery_does_not_persist_the_port(self):
        # Connecting is not evidence the art app will serve anything: on a Wi-Fi
        # Frame one failed connect to the good port at start-up would otherwise
        # rewrite the stored port for good. open() switches in memory only.
        start = ART.index("            previous_port = self._port")
        block = ART[start : ART.index("self._port = alternate_port", start)]
        self.assertNotIn("_learn_port", block)

    def test_only_the_proven_path_writes_the_port(self):
        # One definition plus exactly one call site, in _wait_for_response.
        self.assertEqual(ART.count("self._learn_port("), 1)
        answered = ART[ART.index("    async def _wait_for_response") :]
        answered = answered[: answered.index("\n    def ")]
        self.assertIn("self._learn_port(self._port)", answered)


if __name__ == "__main__":
    unittest.main()
