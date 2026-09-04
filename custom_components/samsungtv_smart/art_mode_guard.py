"""Guard against re-issuing art-mode writes that did not take.

Every path that puts a Frame into (or out of) Art Mode used to trust a derived
``art_mode_status`` and then write — ``artModeOn`` over IP Control, or
``set_artmode`` / ``KEY_POWER`` over the WebSocket — with no check of what the
panel actually shows, no read-back afterwards, and no memory of having just
done the same thing. A wrong reading therefore turned every periodic
automation into a periodic write against the TV, indefinitely: one
``artModeOn`` per run at a panel already showing art, or a full
power-toggle-and-back when the fallback path ran instead.

This module is the memory part. The panel check (``getTVStates.pictureMode``,
which is ``Ambient`` exactly while art is displayed and is independent of the
``artModeControl`` flag that can wedge on some firmware) lives with the
callers; they consult this guard right before writing and report the outcome
right after.

Only writes that were NOT verified to take are remembered: a write that was
read back as applied clears the record, so a user toggling art on, off with
the remote, and on again within a minute is never blocked. What is blocked
is the second unverified write of the same intent inside the cooldown — the
exact shape of the loop above — and blocking it raises, so a retry loop that
would otherwise thrash exits with one warning instead of N writes.

Pure Python, no Home Assistant imports: shared between the media player and
the Art Mode switch through the entry's ``hass.data`` dict, and unit-tested
without either.
"""

from __future__ import annotations

from collections.abc import Callable
import time

# Seconds during which a second, unverified write of the same intent is
# refused. Long enough that an automation firing every 30-60 s cannot turn
# into a write loop; short enough that a genuine retry after a transient
# failure is not held for long.
ART_MODE_WRITE_COOLDOWN = 60.0

# Key under which the per-entry guard is stored in hass.data[DOMAIN][entry_id].
DATA_ART_MODE_GUARD = "art_mode_write_guard"


class ArtModeWriteSuppressed(Exception):
    """A same-intent art-mode write was refused inside the cooldown.

    Carries the seconds since the write it repeats, for the caller's warning.
    """

    def __init__(self, turn_on: bool, since: float) -> None:
        self.turn_on = turn_on
        self.since = since
        intent = "on" if turn_on else "off"
        super().__init__(
            f"art mode '{intent}' was already written {since:.0f}s ago and did not "
            f"take; not writing it again within {ART_MODE_WRITE_COOLDOWN:.0f}s"
        )


class ArtModeWriteGuard:
    """Remember unverified art-mode writes, per intent, for a cooldown."""

    def __init__(
        self,
        cooldown: float = ART_MODE_WRITE_COOLDOWN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cooldown = cooldown
        self._clock = clock
        # intent (True = art on, False = art off) -> monotonic time of the last
        # write of that intent that was not verified to have taken.
        self._unverified: dict[bool, float] = {}

    def check(self, turn_on: bool) -> None:
        """Raise ArtModeWriteSuppressed if this intent was just written in vain."""
        last = self._unverified.get(turn_on)
        if last is None:
            return
        since = self._clock() - last
        if since < self._cooldown:
            raise ArtModeWriteSuppressed(turn_on, since)
        # Cooldown elapsed: the earlier attempt is history, allow one more.
        del self._unverified[turn_on]

    def record_unverified(self, turn_on: bool) -> None:
        """A write was sent and either failed to take or could not be read back."""
        self._unverified[turn_on] = self._clock()

    def record_verified(self, turn_on: bool) -> None:
        """A write was read back as applied: nothing to hold against it."""
        self._unverified.pop(turn_on, None)

    def pending(self, turn_on: bool) -> float | None:
        """Seconds since the last unverified write of this intent, if any."""
        last = self._unverified.get(turn_on)
        return None if last is None else self._clock() - last


def guard_for(entry_store: dict) -> ArtModeWriteGuard:
    """Return the entry's shared guard, creating it on first use.

    ``entry_store`` is ``hass.data[DOMAIN][entry_id]`` — the same dict the
    shared art API lives in — so the switch and the media player, which both
    write art mode, share one memory of what was just written.
    """
    guard = entry_store.get(DATA_ART_MODE_GUARD)
    if guard is None:
        guard = ArtModeWriteGuard()
        entry_store[DATA_ART_MODE_GUARD] = guard
    return guard
