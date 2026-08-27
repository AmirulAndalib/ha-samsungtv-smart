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


def _snapshot(input_source):
    """Return a coordinator holding one IP Control snapshot."""
    return SimpleNamespace(
        data={
            "tv": {"inputSource": input_source},
            "channel": {"atvDtv": "dtv", "airCable": "air", "channelNum": "5"},
            "powered_off": False,
        }
    )


def test_channel_is_read_while_the_snapshot_says_tuner():
    """The channel of the current snapshot is exposed on a tuner input."""
    device = _device()

    with (
        patch.object(SamsungTVDevice, "_get_ip_control_client", return_value=object()),
        patch.object(
            SamsungTVDevice,
            "_get_ip_control_state_coordinator",
            return_value=_snapshot("TV"),
        ),
    ):
        assert device._get_ip_control_channel() == "5"


def test_stale_channel_is_dropped_once_the_input_left_the_tuner():
    """A channel left over from the previous poll is not reported on HDMI.

    The snapshot is only refreshed every IP_CONTROL_STATE_SCAN_INTERVAL, so
    right after switching to HDMI it still carries the tuner channel.
    """
    device = _device()

    with (
        patch.object(SamsungTVDevice, "_get_ip_control_client", return_value=object()),
        patch.object(
            SamsungTVDevice,
            "_get_ip_control_state_coordinator",
            return_value=_snapshot("HDMI1"),
        ),
    ):
        assert device._get_ip_control_channel() is None
