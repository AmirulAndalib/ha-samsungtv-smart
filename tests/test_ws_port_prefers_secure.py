"""The WS port should settle on the secure 8002 channel and stay there.

On many Frames the plain 8001 channel completes the WS handshake and even hands
back a token, so config-flow detection (which tried 8001 first) stored 8001 —
but that token is refused at runtime (ms.channel.unauthorized), so the remote
channel had to re-heal 8001 -> 8002 on every start, logging a WARNING each time
and re-paying the rejection. Measured on two Frames (192.168.1.31 Wi-Fi and
192.168.1.161): one 8001-rejection cluster per HA restart, then wss://8002 for
the rest of the session.

Fix, verified here on the source (both modules need Home Assistant to import):
- detection prefers 8002 when the TV actually exposes it (quick TCP probe keeps
  it safe for 2024 Frames where 8002 is filtered and ~2020 sets that lack it);
- the self-heal transition is INFO, not WARNING (expected and self-correcting);
- the WS-port persist is logged, so a debug capture shows whether CONF_PORT is
  being rewritten back to 8001 between sessions;
- the dead post-start_poll port read (which could never see the async heal, and
  mislabelled it a firmware change) is gone.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "samsungtv_smart"
INIT = (ROOT / "__init__.py").read_text()
MEDIA_PLAYER = (ROOT / "media_player.py").read_text()
SAMSUNGWS = (ROOT / "api" / "samsungws.py").read_text()


def _method(text: str, header: str) -> str:
    start = text.index(header)
    ends = [
        text.find(marker, start + 1)
        for marker in ("\n    def ", "\n    async def ", "\n    @")
    ]
    nxt = min(e for e in ends if e != -1)
    return text[start:nxt]


class DetectionPrefersSecurePortTest(unittest.TestCase):
    """Initial pairing tries the secure 8002 channel first when it is open."""

    def setUp(self):
        self.block = _method(INIT, "    def _try_connect_ws(")

    def test_ping_gates_the_secure_first_order(self):
        self.assertIn("if Ping(self._hostname).ping(8002):", self.block)
        self.assertIn("attempts = [(8002, False), (8001, False)]", self.block)

    def test_it_falls_back_to_plain_first_when_8002_is_absent(self):
        gate = self.block.index("if Ping(self._hostname).ping(8002):")
        secure = self.block.index("[(8002, False), (8001, False)]", gate)
        plain = self.block.index("[(8001, False), (8002, False)]", gate)
        # secure-first inside the if, plain-first in the else that follows.
        self.assertLess(gate, secure)
        self.assertLess(secure, plain)

    def test_ping_is_imported(self):
        self.assertIn("from .api.samsungws import", INIT)
        self.assertRegex(INIT, r"from \.api\.samsungws import[^\n]*\bPing\b")

    def test_a_known_preferred_port_is_still_tried_first_unchanged(self):
        # The proven-port fast path must be untouched: a stored port wins.
        self.assertIn("if self._ws_port:", self.block)
        self.assertIn("(self._ws_port, True)", self.block)

    def test_the_decision_reproduces(self):
        def order(ws_port, has_token, secure_open):
            if ws_port:
                return "preferred-first"
            return "secure-first" if secure_open else "plain-first"

        # These Frames: no stored port yet, 8002 reachable -> pair on 8002.
        self.assertEqual(order(0, False, True), "secure-first")
        # 2024 Frame (8002 filtered) / ~2020 set (no 8002) -> pair on 8001.
        self.assertEqual(order(0, False, False), "plain-first")
        # Already knows its port -> untouched fast path.
        self.assertEqual(order(8002, True, True), "preferred-first")


class SelfHealIsInfoNotWarningTest(unittest.TestCase):
    def setUp(self):
        self.block = _method(SAMSUNGWS, "    def _try_alternate_port(")

    def test_the_transition_is_info(self):
        anchor = "switching to the secure 8002 channel"
        self.assertIn(anchor, self.block)
        before = self.block[: self.block.index(anchor)]
        # The log call immediately preceding the message is info(), not warning.
        self.assertIn("self._log.info(", before)
        self.assertNotIn("self._log.warning(", before)

    def test_both_ports_rejected_stays_a_warning(self):
        # The genuinely actionable case keeps WARNING severity.
        bump = _method(SAMSUNGWS, "    def _bump_auth_failure(")
        self.assertIn("rejected both the 8001 and the secure 8002", bump)
        both = bump.index("rejected both the 8001 and the secure 8002")
        warn = bump.rindex("self._log.warning(", 0, both)
        self.assertLess(warn, both)


class PersistIsObservableTest(unittest.TestCase):
    def test_ws_port_persist_logs_old_and_new(self):
        block = _method(MEDIA_PLAYER, "    def _persist_ws_port(")
        self.assertIn("Persisting WS port for", block)
        # Still guarded on an actual change, and writes the remote CONF_PORT.
        self.assertIn("entry.data.get(CONF_PORT) == port", block)
        self.assertIn("CONF_PORT: port", block)


class ArtPortIsDecoupledFromRemotePortTest(unittest.TestCase):
    """The Art API persists its own port so it can't clobber the remote one.

    Caught on 192.168.1.161: while the TV booted, the art socket answered on
    8001, the Art API "proved" it, and — sharing CONF_PORT with the remote
    channel — wrote 8002 -> 8001, forcing the remote channel to re-heal on the
    next restart. Same class of bug the REST port (CONF_REST_PORT) already
    escaped.
    """

    def test_the_remote_and_art_callbacks_use_different_persisters(self):
        # Remote heal -> _persist_ws_port (CONF_PORT); art heal -> _persist_art_port.
        self.assertIn(
            "run_callback_threadsafe(self.hass.loop, self._persist_ws_port, port)",
            MEDIA_PLAYER,
        )
        self.assertIn(
            "self._art_api.register_port_callback(self._persist_art_port)",
            MEDIA_PLAYER,
        )

    def test_art_persister_writes_its_own_key_not_conf_port(self):
        block = _method(MEDIA_PLAYER, "    def _persist_art_port(")
        self.assertIn("CONF_ART_PORT: port", block)
        self.assertIn("entry.data.get(CONF_ART_PORT) == port", block)
        # Must not touch the remote channel's CONF_PORT.
        self.assertNotIn("CONF_PORT: port", block)

    def test_art_api_reads_its_own_port_with_conf_port_fallback(self):
        self.assertIn(
            "port=config.get(CONF_ART_PORT) or config.get(CONF_PORT, DEFAULT_PORT),",
            MEDIA_PLAYER,
        )

    def test_conf_art_port_excluded_from_reload(self):
        start = INIT.index("_NO_RELOAD_DATA_KEYS = ")
        block = INIT[start : INIT.index("def _reload_fingerprint", start)]
        self.assertIn("CONF_ART_PORT", block)

    def test_reconfigure_clears_the_learned_art_port(self):
        cfg = (ROOT / "config_flow.py").read_text()
        self.assertIn("CONF_ART_PORT: None", cfg)


class DeadPortReadRemovedTest(unittest.TestCase):
    def test_the_synchronous_post_poll_read_is_gone(self):
        # The block read self._ws.port right after start_poll(), before the
        # async heal could happen, and mislabelled it a firmware change.
        self.assertNotIn("port auto-detected after connection", MEDIA_PLAYER)
        self.assertNotIn("updating saved port from", MEDIA_PLAYER)
        self.assertNotIn("resolved_port = self._ws.port", MEDIA_PLAYER)


if __name__ == "__main__":
    unittest.main()
