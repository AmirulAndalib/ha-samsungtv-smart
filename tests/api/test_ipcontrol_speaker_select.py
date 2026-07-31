"""Tests for Samsung IP Control speaker output compatibility."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest


def _load_ipcontrol_module():
    """Load ipcontrol.py with a minimal Home Assistant type stub."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant_core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        """Type stub used only while importing the module."""

    homeassistant_core.HomeAssistant = HomeAssistant
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.core", homeassistant_core)

    module_path = (
        Path(__file__).parents[2]
        / "custom_components"
        / "samsungtv_smart"
        / "api"
        / "ipcontrol.py"
    )
    spec = importlib.util.spec_from_file_location("ipcontrol_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ipcontrol = _load_ipcontrol_module()


class SpeakerSelectFallbackTest(unittest.IsolatedAsyncioTestCase):
    """Verify the Q-Symphony fallback without network access."""

    async def test_dedicated_getter_value_is_used(self):
        """The normal dedicated getter remains the primary source."""
        client = object.__new__(ipcontrol.SamsungIPControl)

        async def fake_request(method, params=None):
            self.assertEqual(method, "speakerSelectControl")
            return {"speakerSelect": "Internal"}

        client._async_request = fake_request

        self.assertEqual(await client.async_get_speaker_select(), "Internal")

    async def test_null_dedicated_getter_falls_back_to_tv_states(self):
        """Q-Symphony's device ID is recovered from getTVStates."""
        client = object.__new__(ipcontrol.SamsungIPControl)

        async def fake_request(method, params=None):
            if method == "speakerSelectControl":
                return {"speakerSelect": None}
            if method == "getTVStates":
                return {"speakerSelect": "QSYM-RECEIVER"}
            self.fail(f"unexpected method: {method}")

        client._async_request = fake_request

        self.assertEqual(
            await client.async_get_speaker_select(),
            "QSYM-RECEIVER",
        )

    async def test_missing_value_in_both_responses_is_an_error(self):
        """A real missing capability still leaves the entity unavailable."""
        client = object.__new__(ipcontrol.SamsungIPControl)

        async def fake_request(method, params=None):
            return {}

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_get_speaker_select()


class SpeakerSelectOptionResolutionTest(unittest.TestCase):
    """Verify external IDs and standard values become valid select options."""

    def test_q_symphony_device_id_resolves_to_name(self):
        """The Q-Symphony ID maps to the option shown in Home Assistant."""
        devices = {
            "Q-Symphony": "QSYM-RECEIVER",
            "Q6C Series Soundbar(HDMI)": "RCV-1",
        }

        self.assertEqual(
            ipcontrol.resolve_speaker_select_option("QSYM-RECEIVER", devices),
            "Q-Symphony",
        )

    def test_standard_value_is_normalized(self):
        """The lowercase mirror value maps to the public option spelling."""
        self.assertEqual(
            ipcontrol.resolve_speaker_select_option("internal", {}),
            "Internal",
        )


if __name__ == "__main__":
    unittest.main()
