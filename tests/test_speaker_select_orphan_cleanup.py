"""IP Control setup must remove the stale SmartThings speaker select (#261).

SamsungTVSTMediaOutputSelect (name "Speaker Select") is created only while IP
Control is NOT active. A user who starts SmartThings-only and later pairs IP
Control is left with that entity orphaned in the registry: a dead
select.<tv>_speaker_select with no live object — it never updates,
homeassistant.update_entity is a no-op on it, and it keeps the base entity_id so
the live IP speaker select is pushed to select.<tv>_speaker_select_2.

async_setup_entry now removes that stale entry (by its unique_id) whenever IP
Control is active. select.py can't be imported without Home Assistant, so the
cleanup is checked structurally on the source.
"""

from pathlib import Path
import unittest

SELECT = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "select.py"
).read_text()


def _setup_entry() -> str:
    start = SELECT.index("async def async_setup_entry")
    return SELECT[start : SELECT.index("\nclass ", start)]


class OrphanCleanupTest(unittest.TestCase):
    def setUp(self):
        self.block = _setup_entry()

    def test_the_stale_st_speaker_select_is_looked_up_by_unique_id(self):
        self.assertIn(
            'registry.async_get_entity_id(\n'
            '            "select", DOMAIN, f"{device_unique_id}_st_media_output"\n'
            "        )",
            self.block,
        )

    def test_it_is_removed_from_the_registry(self):
        self.assertIn("registry.async_remove(stale_id)", self.block)

    def test_cleanup_runs_only_when_ip_control_is_active(self):
        ip_gate = self.block.index("if _ip_control_active(entry):")
        remove = self.block.index("registry.async_remove(stale_id)")
        # The removal sits inside the IP-active branch, before the IP entities
        # are added (so the base entity_id is free for the live speaker select).
        add = self.block.index("SamsungTVIPControlSpeakerSelect(")
        self.assertLess(ip_gate, remove)
        self.assertLess(remove, add)


if __name__ == "__main__":
    unittest.main()
