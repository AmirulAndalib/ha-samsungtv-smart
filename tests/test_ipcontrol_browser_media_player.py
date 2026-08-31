"""Tests for IP Control browser integration in the media player."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

# The repository test requirements do not install pysmartthings.
# Provide the symbols needed while importing media_player.py.
if "pysmartthings" not in sys.modules:
    pysmartthings = ModuleType("pysmartthings")

    class _Names:
        """Return arbitrary SmartThings enum-like attributes."""

        def __getattr__(self, name):
            return name

    pysmartthings.Attribute = _Names()
    pysmartthings.Capability = _Names()
    pysmartthings.SmartThings = object
    sys.modules["pysmartthings"] = pysmartthings


from custom_components.samsungtv_smart.api.ipcontrol import (  # noqa: E402
    SamsungIPControlError,
)
from custom_components.samsungtv_smart.media_player import (  # noqa: E402
    CMD_OPEN_BROWSER,
    SamsungTVDevice,
)


async def test_browser_falls_back_to_websocket_when_ip_control_fails():
    """A failed IP Control browser launch falls back to WebSocket."""
    device = object.__new__(SamsungTVDevice)

    client = AsyncMock()
    client.async_open_browser.side_effect = SamsungIPControlError("test failure")

    device._get_ip_control_client = MagicMock(return_value=client)
    device._log = MagicMock()
    device.async_send_command = AsyncMock(return_value=True)

    url = "https://example.com/"

    result = await device._async_open_browser(url)

    client.async_open_browser.assert_awaited_once_with(url)
    device.async_send_command.assert_awaited_once_with(url, CMD_OPEN_BROWSER)

    assert result is True
