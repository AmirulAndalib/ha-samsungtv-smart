"""Power-on must skip a doomed WS KEY_POWER and use the wake fallback (#12/.31).

On some ~2020 Frames the remote-control WebSocket can never authorize (the TV
rejects the token on both 8001 and the secure 8002 channel), tripping
samsungws.auth_blocked. KEY_POWER then still reports "sent" while the TV ignores
it with ms.channel.unauthorized, so _async_power_on never reached the configured
WOL/SmartThings/IPControl wake method and the Frame stayed off ("TV is not
reachable" every automation cycle on 192.168.1.31).

_async_power_on now skips KEY_POWER when the channel is auth_blocked and falls
straight through to the wake method. media_player.py needs Home Assistant to
import, so the gate is pinned structurally on the source.
"""

from pathlib import Path
import unittest

MEDIA_PLAYER = (
    Path(__file__).parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "media_player.py"
).read_text()


def _power_on_block() -> str:
    start = MEDIA_PLAYER.index("    async def _async_power_on(")
    return MEDIA_PLAYER[start : MEDIA_PLAYER.index("\n    async def ", start + 1)]


class PowerOnAuthBlockedFallbackTest(unittest.TestCase):
    def setUp(self):
        self.block = _power_on_block()

    def test_key_power_is_gated_on_the_channel_not_being_auth_blocked(self):
        self.assertIn("if not self._ws.auth_blocked:", self.block)
        gate = self.block.index("if not self._ws.auth_blocked:")
        send = self.block.index(
            "key_power_sent = await self.async_send_command(cmd_power_on)"
        )
        self.assertLess(gate, send)

    def test_the_fallback_runs_when_key_power_was_not_sent(self):
        # The configured wake method must key off key_power_sent, so an
        # auth-blocked channel (KEY_POWER skipped) still reaches WOL/ST/IP.
        self.assertIn("if not key_power_sent:", self.block)
        gate = self.block.index("if not key_power_sent:")
        for wake in (
            "self._st.async_turn_on()",
            "ip_client.async_power_on()",
            "self._send_wol_packet",
        ):
            self.assertLess(gate, self.block.index(wake), wake)

    def test_the_old_unconditional_key_power_guard_is_gone(self):
        # The previous `if not await self.async_send_command(cmd_power_on):`
        # trusted a KEY_POWER that returns "sent" even on ms.channel.unauthorized.
        self.assertNotIn(
            "if not await self.async_send_command(cmd_power_on):", self.block
        )


if __name__ == "__main__":
    unittest.main()
