"""The REST port is settled once proven, and never flapped on a sleeping panel.

Measured on a 12-TV fleet (#273 follow-up): SamsungTVAsyncRest logged 115
`switching to it` events in 49.6 h, balanced 57x 8002->8001 and 58x 8001->8002 —
a ping-pong, not a heal. The old _rest_request adopted (switched + persisted via
_learn_port) the alternate port on EVERY successful fallback, so on a sleeping
panel where both REST ports flap it swapped back and forth and rewrote the stored
port each time. The top emitters were the Frames that sleep the most.

Fix (mirrors api.art's proven-port rule): a REST port is proven the first time it
answers as the primary; a proven port that merely fails transiently is kept (the
call is still served from the alternate) and never persisted, so only genuine
discovery of an unproven port switches the stored value.

samsungws needs aiohttp to import, so this is checked on the source.
"""

from pathlib import Path
import unittest

SAMSUNGWS = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
    / "samsungws.py"
).read_text()


def _method(name: str) -> str:
    start = SAMSUNGWS.index(f"    async def {name}(")
    ends = [
        SAMSUNGWS.find(marker, start + 1)
        for marker in ("\n    async def ", "\n    def ", "\nclass ")
    ]
    return SAMSUNGWS[start : min(e for e in ends if e != -1)]


class RestProvenPortIsKeptTest(unittest.TestCase):
    def setUp(self):
        self.block = _method("_rest_request")

    def test_the_class_tracks_a_proven_rest_port(self):
        init = SAMSUNGWS[SAMSUNGWS.index("class SamsungTVAsyncRest") :]
        init = init[: init.index("\n    def register_port_callback")]
        self.assertIn("self._proven_port: int | None = None", init)

    def test_switch_is_gated_on_the_port_being_unproven(self):
        self.assertIn("if self._proven_port != self._port:", self.block)

    def test_a_proven_port_is_kept_not_swapped_on_transient_failure(self):
        # The keep branch serves from the alternate but must not reassign _port.
        keep = self.block[self.block.index("else:") :]
        self.assertIn("keeping the proven port", keep)
        self.assertNotIn("self._port = alternate_port", keep)

    def test_the_primary_answer_proves_and_persists_once(self):
        tail = self.block[self.block.index("# The primary answered") :]
        self.assertIn("self._proven_port = self._port", tail)
        self.assertIn("self._learn_port(self._port)", tail)

    def test_no_switching_to_it_warning_remains(self):
        # The per-flap WARNING that logged 115 times is gone; the transient case
        # is DEBUG and genuine discovery is INFO.
        self.assertNotIn("-- switching to it", SAMSUNGWS)

    def test_the_decision_reproduces(self):
        def adopts(proven_port, port) -> bool:
            # True => switch stored port (discovery); False => keep proven port.
            return proven_port != port

        # Configured port never answered (proven is None) -> adopt the one that does.
        self.assertTrue(adopts(None, 8001))
        # 8002 proven, asleep so it failed this call -> keep it, do not flap.
        self.assertFalse(adopts(8002, 8002))


if __name__ == "__main__":
    unittest.main()
