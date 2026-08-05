"""The connection to the local Discord client.

Every method is called from the presence worker thread and none of them raise: Discord may be
closed, restarting, or a version whose library disagrees with ours, and none of that is worth a
warning in the user's console — let alone taking a thread down in a windowed build.
"""

from __future__ import annotations

import time

from totstats.presence.render import Payload
from totstats.shared.applog import AppLog

# Reconnect attempts back off to five minutes; Discord is usually just not running.
BACKOFF = (5.0, 10.0, 20.0, 40.0, 60.0, 120.0, 300.0)
CONNECT_TIMEOUT = 5


class DiscordClient:
    def __init__(self, client_id: str, log: AppLog, dry_run: bool = False) -> None:
        self._client_id = client_id
        self._log = log
        self._dry_run = dry_run
        self._rpc: object | None = None
        self._attempt = 0
        self._next_attempt = 0.0
        self._announced = False

    @property
    def configured(self) -> bool:
        """A dry run has nothing to connect to, so it needs no application id either."""
        return self._dry_run or bool(self._client_id)

    @property
    def connected(self) -> bool:
        return self._dry_run or self._rpc is not None

    def next_attempt_in(self, now: float | None = None) -> float:
        """Seconds until reconnecting is worth trying again."""
        return max(0.0, self._next_attempt - (now if now is not None else time.monotonic()))

    def ensure_connected(self) -> bool:
        """Connect if it is due. Returns False without blocking when it is not."""
        if self.connected:
            return True
        if not self.configured:
            return False
        now = time.monotonic()
        if now < self._next_attempt:
            return False
        return self._connect(now)

    def update(self, payload: Payload) -> bool:
        if self._dry_run:
            self._log.info(f"🧪 Would show: {payload.summary()}")
            return True
        rpc = self._rpc
        if rpc is None:
            return False
        try:
            rpc.update(**payload.as_kwargs())  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - the library's failure modes are open-ended
            self._drop(f"Discord rejected the update ({exc})")
            return False
        self._log.debug(f"🔗 Discord shows: {payload.summary()}")
        return True

    def clear(self) -> bool:
        if self._dry_run:
            self._log.debug("🧪 Would clear the Discord status")
            return True
        rpc = self._rpc
        if rpc is None:
            return False
        try:
            rpc.clear()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self._drop(f"Could not clear the Discord status ({exc})")
            return False
        return True

    def close(self) -> None:
        rpc, self._rpc = self._rpc, None
        if rpc is None:
            return
        try:
            rpc.close()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - shutting down must not fail on a dead pipe
            pass

    def _connect(self, now: float) -> bool:
        assert not self._dry_run, "a dry run must never open a connection to Discord"
        try:
            from pypresence import Presence

            # Built here, on the worker thread: pypresence drives an asyncio loop and picks one up
            # from the thread it is constructed on. The short timeout keeps a missing Discord from
            # parking this thread for half a minute.
            rpc = Presence(self._client_id, connection_timeout=CONNECT_TIMEOUT)
            rpc.connect()
        except Exception as exc:  # noqa: BLE001
            self._schedule_retry(now)
            if not self._announced:
                self._announced = True
                self._log.info("ℹ️ Discord is not running — Rich Presence connects once it is")
            else:
                self._log.debug(f"🔗 Discord connection failed ({exc})")
            return False

        self._rpc = rpc
        self._attempt = 0
        self._announced = False
        self._log.info("🔗 Connected to Discord")
        return True

    def _schedule_retry(self, now: float) -> None:
        delay = BACKOFF[min(self._attempt, len(BACKOFF) - 1)]
        self._attempt += 1
        self._next_attempt = now + delay

    def _drop(self, message: str) -> None:
        self._log.debug(f"🔗 {message}")
        self.close()
        self._attempt = 0
        self._schedule_retry(time.monotonic())
