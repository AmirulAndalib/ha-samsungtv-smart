"""Tests for Samsung IP Control browser launch."""

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
        "ipcontrol_browser_under_test", module_path
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


class BrowserControlTest(unittest.IsolatedAsyncioTestCase):
    """Verify browser launch without network access."""

    def _client(self):
        """Return a paired client with a fake Home Assistant instance."""
        ipcontrol._HOST_LOCKS.clear()
        return ipcontrol.SamsungIPControl(
            _FakeHass(),
            "192.0.2.1",
            token="test-token",
        )

    async def test_open_browser_emits_expected_payload(self):
        """directAccessControl sends the expected browser launch payload."""
        client = self._client()
        sent = {}

        def fake_post(payload, timeout):
            sent.update(json.loads(payload))
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "applicationName": "webBrowser",
                        "url": "https://example.com/",
                    },
                }
            )

        client._sync_post = fake_post

        result = await client.async_open_browser("https://example.com/")

        self.assertIsNone(result)
        self.assertEqual(sent["method"], "directAccessControl")
        self.assertEqual(
            sent["params"],
            {
                "AccessToken": "test-token",
                "applicationName": "webBrowser",
                "url": "https://example.com/",
            },
        )


if __name__ == "__main__":
    unittest.main()
