"""Tests for local tuner channel exposure on the media player."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

# The repository test requirements do not install pysmartthings.
# This is the same minimal import stub used by existing tests.
if "pysmartthings" not in sys.modules:
    pysmartthings = ModuleType("pysmartthings")
    pysmartthings.SmartThings = object
    sys.modules["pysmartthings"] = pysmartthings


from custom_components.samsungtv_smart.const import DEFAULT_APP  # noqa: E402
from custom_components.samsungtv_smart.media_player import SamsungTVDevice  # noqa: E402
from homeassistant.components.media_player import (  # noqa: E402
    MediaPlayerState,
    MediaType,
)


def _device(*, st=None):
    """Create only the state needed by the media properties."""
    device = object.__new__(SamsungTVDevice)
    device._state = MediaPlayerState.ON
    device._st = st
    device._running_app = DEFAULT_APP
    return device


def test_local_channel_is_preferred_over_smartthings():
    """Local IP Control channel wins when both sources have data."""
    device = _device(
        st=SimpleNamespace(
            source="TV",
            channel="42",
        )
    )

    with patch.object(
        SamsungTVDevice,
        "_get_ip_control_channel",
        return_value="7",
    ):
        assert device.media_channel == "7"


def test_smartthings_channel_remains_fallback():
    """Existing SmartThings channel behavior remains available."""
    device = _device(
        st=SimpleNamespace(
            source="digitalTv",
            channel="42",
        )
    )

    with patch.object(
        SamsungTVDevice,
        "_get_ip_control_channel",
        return_value=None,
    ):
        assert device.media_channel == "42"


def test_local_channel_sets_channel_media_type():
    """A local tuner channel is exposed as channel media."""
    device = _device()

    with patch.object(
        SamsungTVDevice,
        "_get_ip_control_channel",
        return_value="7",
    ):
        assert device.media_channel == "7"
        assert device.media_content_type == MediaType.CHANNEL
