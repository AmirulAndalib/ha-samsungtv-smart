"""Tests for Samsung IP Control absolute volume."""

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
        "ipcontrol_volume_under_test",
        module_path,
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


class AbsoluteVolumeControlTest(unittest.IsolatedAsyncioTestCase):
    """Verify directVolumeControl getter and setter."""

    def _client(self):
        """Return a paired client with a fake Home Assistant instance."""
        ipcontrol._HOST_LOCKS.clear()

        return ipcontrol.SamsungIPControl(
            _FakeHass(),
            "192.0.2.1",
            token="test-token",
        )

    async def test_get_volume_emits_expected_payload_and_returns_value(self):
        """Getter sends only AccessToken and returns the absolute volume."""
        client = self._client()
        sent = {}

        def fake_post(payload, timeout):
            sent.update(json.loads(payload))

            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "volume": 30,
                    },
                }
            )

        client._sync_post = fake_post

        result = await client.async_get_volume()

        self.assertEqual(sent["method"], "directVolumeControl")
        self.assertEqual(
            sent["params"],
            {
                "AccessToken": "test-token",
            },
        )
        self.assertEqual(result, 30)

    async def test_set_volume_emits_expected_payload_and_returns_value(self):
        """Setter includes volume and returns the TV-reported value."""
        client = self._client()
        sent = {}

        def fake_post(payload, timeout):
            sent.update(json.loads(payload))

            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "volume": 30,
                    },
                }
            )

        client._sync_post = fake_post

        result = await client.async_set_volume(30)

        self.assertEqual(sent["method"], "directVolumeControl")
        self.assertEqual(
            sent["params"],
            {
                "AccessToken": "test-token",
                "volume": 30,
            },
        )
        self.assertEqual(result, 30)

    async def test_set_volume_uses_requested_value_when_response_omits_volume(self):
        """Some TVs may acknowledge SET without echoing the volume."""
        client = self._client()

        async def fake_request(method, params=None):
            self.assertEqual(method, "directVolumeControl")
            self.assertEqual(params, {"volume": 30})
            return {}

        client._async_request = fake_request

        self.assertEqual(
            await client.async_set_volume(30),
            30,
        )

    async def test_get_volume_missing_value_is_error(self):
        """A getter response without volume is invalid."""
        client = self._client()

        async def fake_request(method, params=None):
            self.assertEqual(method, "directVolumeControl")
            return {}

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_get_volume()

    async def test_get_volume_non_numeric_value_is_error(self):
        """A non-numeric volume response is invalid."""
        client = self._client()

        async def fake_request(method, params=None):
            return {
                "volume": "not-a-number",
            }

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_get_volume()

    async def test_get_volume_out_of_range_is_error(self):
        """Getter rejects values outside the Home Assistant 0-100 range."""
        client = self._client()

        async def fake_request(method, params=None):
            return {
                "volume": 101,
            }

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_get_volume()

    async def test_set_volume_below_range_is_error(self):
        """Setter rejects values below zero without sending a request."""
        client = self._client()

        async def fake_request(method, params=None):
            self.fail("RPC request must not be sent for invalid volume")

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_set_volume(-1)

    async def test_set_volume_above_range_is_error(self):
        """Setter rejects values above 100 without sending a request."""
        client = self._client()

        async def fake_request(method, params=None):
            self.fail("RPC request must not be sent for invalid volume")

        client._async_request = fake_request

        with self.assertRaises(ipcontrol.SamsungIPControlError):
            await client.async_set_volume(101)

    async def test_method_not_found_surfaces_as_unsupported(self):
        """JSON-RPC -32601 identifies a TV without directVolumeControl."""
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

        with self.assertRaises(
            ipcontrol.SamsungIPControlUnsupportedError
        ):
            await client.async_get_volume()


if __name__ == "__main__":
    unittest.main()
