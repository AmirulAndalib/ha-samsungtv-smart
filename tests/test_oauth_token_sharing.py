"""Tests for OAuth token rotation across multiple TV entries."""

import asyncio
import sys
from types import ModuleType
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

# The repository test requirements do not install pysmartthings. This test
# exercises token coordination only, so provide the one symbol imported while
# loading the integration package without pulling in the cloud client.
if "pysmartthings" not in sys.modules:
    pysmartthings = ModuleType("pysmartthings")
    pysmartthings.SmartThings = object
    sys.modules["pysmartthings"] = pysmartthings

from custom_components.samsungtv_smart import (  # noqa: E402
    async_get_samsungtv_api_key,
    get_oauth_refresh_lock,
    is_oauth_token_invalid,
    set_oauth_token_invalid,
    update_shared_oauth_token,
)
from custom_components.samsungtv_smart.config_flow import (  # noqa: E402
    SamsungTVSmartOAuth2FlowHandler,
)
from custom_components.samsungtv_smart.const import (  # noqa: E402
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_OAUTH_TOKEN,
    DOMAIN,
)


def _entry(title, token, implementation=DOMAIN):
    """Create an OAuth TV config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=title,
        data={
            CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
            CONF_OAUTH_TOKEN: token,
            "auth_implementation": implementation,
        },
    )


def test_refresh_lock_is_shared_only_by_matching_oauth_group():
    """Entries sharing credentials and refresh token use the same lock."""
    shared_token = {"access_token": "old-access", "refresh_token": "old-refresh"}
    first = _entry("First", shared_token)
    sibling = _entry("Sibling", shared_token)
    other_token = _entry(
        "Other token",
        {"access_token": "other-access", "refresh_token": "other-refresh"},
    )
    other_implementation = _entry(
        "Other implementation", shared_token, implementation="other-credentials"
    )

    first_lock = get_oauth_refresh_lock(first)
    assert get_oauth_refresh_lock(sibling) is first_lock
    assert get_oauth_refresh_lock(other_token) is not first_lock
    assert get_oauth_refresh_lock(other_implementation) is not first_lock


def test_rotated_token_updates_only_entries_sharing_predecessor(hass):
    """A new token is copied only to entries that shared the previous one."""
    previous_token = {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "expires_at": 1,
    }
    new_token = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": 4_000_000_000,
    }
    source = _entry("Source", previous_token)
    sibling = _entry("Sibling", previous_token)
    unrelated = _entry(
        "Unrelated",
        {
            "access_token": "unrelated-access",
            "refresh_token": "unrelated-refresh",
            "expires_at": 1,
        },
    )
    other_implementation = _entry(
        "Other implementation", previous_token, implementation="other-credentials"
    )
    for entry in (source, sibling, unrelated, other_implementation):
        entry.add_to_hass(hass)

    set_oauth_token_invalid(source.entry_id, True)
    set_oauth_token_invalid(sibling.entry_id, True)

    with patch(
        "custom_components.samsungtv_smart.ir.async_delete_issue"
    ) as delete_issue:
        updated = update_shared_oauth_token(hass, source, previous_token, new_token)

    assert updated == 2
    assert source.data[CONF_OAUTH_TOKEN] == new_token
    assert sibling.data[CONF_OAUTH_TOKEN] == new_token
    assert source.data["api_key"] == "new-access"
    assert sibling.data["api_key"] == "new-access"
    assert unrelated.data[CONF_OAUTH_TOKEN]["refresh_token"] == "unrelated-refresh"
    assert other_implementation.data[CONF_OAUTH_TOKEN] == previous_token
    assert not is_oauth_token_invalid(source.entry_id)
    assert not is_oauth_token_invalid(sibling.entry_id)
    assert delete_issue.call_count == 2


async def test_manual_reauth_propagates_token_to_sibling_entries(hass):
    """Completing reauth updates every entry that held the old token."""
    previous_token = {
        "access_token": "old-reauth-access",
        "refresh_token": "old-reauth-refresh",
        "expires_at": 1,
    }
    new_token = {
        "access_token": "new-reauth-access",
        "refresh_token": "new-reauth-refresh",
        "expires_at": 4_000_000_000,
    }
    source = _entry("Reauth source", previous_token)
    sibling = _entry("Reauth sibling", previous_token)
    source.add_to_hass(hass)
    sibling.add_to_hass(hass)

    flow = SamsungTVSmartOAuth2FlowHandler()
    flow.hass = hass
    flow._reauth_entry = source
    flow._oauth_data = {"token": new_token}

    with (
        patch("custom_components.samsungtv_smart.ir.async_delete_issue"),
        patch.object(
            flow,
            "async_abort",
            return_value={"type": "abort", "reason": "reauth_successful"},
        ),
    ):
        result = await flow._async_finish_reauth()

    assert result["reason"] == "reauth_successful"
    assert source.data[CONF_OAUTH_TOKEN] == new_token
    assert sibling.data[CONF_OAUTH_TOKEN] == new_token
    assert source.data[CONF_AUTH_METHOD] == AUTH_METHOD_OAUTH


async def test_concurrent_refresh_rotates_shared_token_once(hass):
    """Concurrent TV refreshes submit the shared predecessor only once."""
    previous_token = {
        "access_token": "old-access",
        "refresh_token": "old-refresh-concurrent",
        "expires_at": 1,
    }
    new_token = {
        "access_token": "new-access",
        "refresh_token": "new-refresh-concurrent",
        "expires_at": 4_000_000_000,
    }
    first = _entry("First concurrent", previous_token)
    sibling = _entry("Sibling concurrent", previous_token)
    first.add_to_hass(hass)
    sibling.add_to_hass(hass)

    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()
    refresh_calls = 0

    class Implementation:
        """Controllable OAuth implementation used by the test."""

        async def async_refresh_token(self, token):
            nonlocal refresh_calls
            refresh_calls += 1
            assert token == previous_token
            refresh_started.set()
            await allow_refresh_to_finish.wait()
            return new_token

    implementation = Implementation()
    with (
        patch(
            "custom_components.samsungtv_smart.config_entry_oauth2_flow."
            "async_get_config_entry_implementation",
            return_value=implementation,
        ),
        patch("custom_components.samsungtv_smart.ir.async_delete_issue"),
    ):
        first_task = asyncio.create_task(async_get_samsungtv_api_key(hass, first))
        await refresh_started.wait()
        sibling_task = asyncio.create_task(async_get_samsungtv_api_key(hass, sibling))
        await asyncio.sleep(0)
        allow_refresh_to_finish.set()
        results = await asyncio.gather(first_task, sibling_task)

    assert results == ["new-access", "new-access"]
    assert refresh_calls == 1
    assert first.data[CONF_OAUTH_TOKEN] == new_token
    assert sibling.data[CONF_OAUTH_TOKEN] == new_token
