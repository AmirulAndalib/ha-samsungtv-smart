"""Tests for Samsung IP Control tuner channel state."""

import importlib.util
import json
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
    spec = importlib.util.spec_from_file_location(
        "ipcontrol_channel_under_test", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ipcontrol = _load_ipcontrol_module()


class _FakeHass:
    """Minimal executor bridge used by the async client."""

    async def async_add_executor_job(self, func, *args):
        """Run executor work inline for the unit test."""
        return func(*args)


class ChannelControlTest(unittest.IsolatedAsyncioTestCase):
    """Verify local tuner channel state without network access."""

    def _client(self):
        """Return a paired client with a fake Home Assistant instance."""
        ipcontrol._HOST_LOCKS.clear()
        return ipcontrol.SamsungIPControl(
            _FakeHass(),
            "192.0.2.1",
            token="test-token",
        )

    async def test_get_channel_emits_expected_payload_and_returns_state(self):
        """directChannelControl returns tuner metadata unchanged."""
        client = self._client()
        sent = {}

        def fake_post(payload, timeout):
            sent.update(json.loads(payload))
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "atvDtv": "dtv",
                        "airCable": "air",
                        "channelNum": "5",
                    },
                }
            )

        client._sync_post = fake_post

        result = await client.async_get_channel()

        self.assertEqual(sent["method"], "directChannelControl")
        self.assertEqual(sent["params"], {"AccessToken": "test-token"})
        self.assertEqual(
            result,
            {
                "atvDtv": "dtv",
                "airCable": "air",
                "channelNum": "5",
            },
        )

    async def test_method_not_found_surfaces_as_unsupported(self):
        """A JSON-RPC -32601 remains an unsupported capability/state error."""
        client = self._client()

        def fake_post(payload, timeout):
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32601,
                        "message": "Method not found",
                    },
                }
            )

        client._sync_post = fake_post

        with self.assertRaises(ipcontrol.SamsungIPControlUnsupportedError):
            await client.async_get_channel()


if __name__ == "__main__":
    unittest.main()
