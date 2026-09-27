"""The thumbnail batch pauses for the art channel's recovery, then resumes.

Measured on 192.168.1.31 (Wi-Fi Frame, just woken): the batch fetched 3 of 16
personal thumbnails, the channel wedged, and during the recovery cooldown every
request is refused at once, so the remaining 13 failed in ~3 s each. The batch
now waits for the cooldown (a few times, bounded), retries the image that was
cut off, resumes, and reports anything it could not reach as not processed.
Checked on the source (HA needed to import) plus a model of the loop.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "samsungtv_smart"
ART = (ROOT / "api" / "art.py").read_text()
MP = (ROOT / "media_player.py").read_text()


def _batch():
    start = MP.index("    async def async_art_get_thumbnails_batch(")
    return MP[start : MP.index("\n    async def ", start + 10)]


class RecoveryRemainingTest(unittest.TestCase):
    def test_property_exposes_the_cooldown(self):
        start = ART.index("    def recovery_remaining(self) -> float:")
        block = ART[start : start + 600]
        self.assertIn("self._request_cooldown_until - time.monotonic()", block)
        self.assertIn("max(0.0,", block)


class BatchPausesTest(unittest.TestCase):
    def setUp(self):
        self.block = _batch()

    def test_waits_before_requesting_during_recovery(self):
        pause = self.block.index("pause = self._art_api.recovery_remaining")
        sleep = self.block.index("await asyncio.sleep(wait)", pause)
        fetch = self.block.index("await self.async_art_get_thumbnail(", pause)
        self.assertLess(sleep, fetch)

    def test_bounded_and_reports_not_processed(self):
        self.assertIn("max_pauses = 3", self.block)
        self.assertIn("max_total_wait = 300.0", self.block)
        self.assertIn('"not_processed": len(not_processed)', self.block)
        self.assertIn('"success": not not_processed', self.block)

    def test_cut_off_image_is_retried_once(self):
        self.assertIn("content_id not in retried_after_pause", self.block)

    def test_the_loop_reproduces(self):
        # Model: channel wedges after 3 fetches, recovers after one pause.
        def run(recover_after_pause=True):
            items = [f"MY_F{i:04d}" for i in range(16)]
            cooldown = {"on": False}
            fetched, failed, not_processed, pauses = [], [], [], 0
            retried, idx = set(), 0
            while idx < len(items):
                if cooldown["on"]:
                    if pauses >= 3:
                        not_processed = items[idx:]
                        break
                    pauses += 1
                    if recover_after_pause:
                        cooldown["on"] = False
                cid = items[idx]
                if cooldown["on"] or (len(fetched) == 3 and pauses == 0):
                    cooldown["on"] = True
                    if cid not in retried:
                        retried.add(cid)
                        continue
                    failed.append(cid)
                else:
                    fetched.append(cid)
                idx += 1
            return len(fetched), len(failed), len(not_processed)

        self.assertEqual(run(True), (16, 0, 0))
        self.assertEqual(run(False)[0], 3)
        self.assertEqual(sum(run(False)), 16)


if __name__ == "__main__":
    unittest.main()
