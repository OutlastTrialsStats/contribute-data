"""Wires the log tailer to Discord: on_line reduces state, a worker thread publishes it.

The watcher thread must never wait on a socket, so it only ever drops the newest state into a
mailbox. The worker decides when that state is worth sending — Discord rate-limits status updates,
and most log lines do not change anything the user can see.
"""

from __future__ import annotations

import threading
import time

from totstats.presence.catalog import Catalog
from totstats.presence.client import DiscordClient
from totstats.presence.parser import PresenceParser
from totstats.presence.render import Payload, render
from totstats.presence.state import GameState, StateMachine
from totstats.shared.applog import AppLog
from totstats.shared.log_tail import LogLine
from totstats.shared.profile_id import OwnProfileIdResolver

# Discord drops updates that arrive faster than roughly one per fifteen seconds. Two tokens let a
# pair of quick transitions through — trial selected, trial started — without stalling either.
RATE_CAPACITY = 2
RATE_REFILL = 15.0
RATE_FLOOR = 5.0

# GameStageInfo and the presence the game posts describe the same transition about a second and a
# half apart. Waiting for quiet turns them into one update.
SETTLE = 2.0

# A replay that never reports being finished must not keep the status blank forever.
REPLAY_GUARD = 30.0

# How long the worker sleeps when it has nothing scheduled.
IDLE_WAIT = 5.0

WARN_INTERVAL = 60.0


class RateLimiter:
    """Token bucket with a floor between sends, so bursts coalesce instead of being dropped."""

    def __init__(
        self, capacity: int = RATE_CAPACITY, refill: float = RATE_REFILL, floor: float = RATE_FLOOR
    ) -> None:
        self._capacity = capacity
        self._refill = refill
        self._floor = floor
        self._tokens = float(capacity)
        self._last = 0.0
        self._sent = 0.0

    def _replenish(self, now: float) -> None:
        if self._last:
            self._tokens = min(self._capacity, self._tokens + (now - self._last) / self._refill)
        self._last = now

    def allow(self, now: float) -> bool:
        self._replenish(now)
        return self._tokens >= 1.0 and (not self._sent or now - self._sent >= self._floor)

    def consume(self, now: float) -> None:
        self._replenish(now)
        self._tokens = max(0.0, self._tokens - 1.0)
        self._sent = now

    def wait_for(self, now: float) -> float:
        self._replenish(now)
        waits = []
        if self._tokens < 1.0:
            waits.append((1.0 - self._tokens) * self._refill)
        if self._sent and now - self._sent < self._floor:
            waits.append(self._floor - (now - self._sent))
        return max(waits) if waits else 0.0


class _Mailbox:
    """A single slot: only the newest state matters, so a burst collapses into one send."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._value: GameState | None = None
        self._closed = False

    def put(self, value: GameState) -> None:
        with self._lock:
            self._value = value
        self._event.set()

    def nudge(self) -> None:
        self._event.set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._event.set()

    def take(self, timeout: float) -> tuple[GameState | None, bool]:
        """Waits up to timeout and returns (new state or None, closed)."""
        self._event.wait(timeout)
        self._event.clear()
        with self._lock:
            value, self._value = self._value, None
            return value, self._closed


class PresenceService:
    INTERESTS = PresenceParser.INTERESTS + OwnProfileIdResolver.INTERESTS

    def __init__(
        self,
        client: DiscordClient,
        catalog: Catalog,
        ids: OwnProfileIdResolver,
        log: AppLog,
    ) -> None:
        self._client = client
        self._catalog = catalog
        self._ids = ids
        self._log = log

        self._parser = PresenceParser()
        self._machine = StateMachine()
        self._mailbox = _Mailbox()
        self._limiter = RateLimiter()
        self._worker: threading.Thread | None = None

        self._state = GameState()
        self._last_sent: Payload | None = None
        self._changed_at = 0.0
        self._replaying = True
        self._live_since = 0.0
        self._unknown_trials: set[str] = set()
        self._warned_at = 0.0
        self._retired = False

        # Read by the worker, written by the tray. Parsing continues either way: switching the
        # feature on mid-session has to show the trial you are in right now, and by then there is
        # no replay left to rebuild it from.
        self.enabled = True
        self.game_running = True

    def start(self) -> None:
        if self._worker is not None:
            return
        if not self._client.configured:
            self._log.warning("⚠️ Discord Rich Presence is not configured and stays off")
            return
        self._worker = threading.Thread(target=self._run, name="presence-rpc", daemon=True)
        self._worker.start()

    def stop(self, timeout: float = 3.0) -> None:
        worker = self._worker
        self._mailbox.close()
        if worker is None:
            return
        self._worker = None
        worker.join(timeout)
        if worker.is_alive():
            self._log.warning("presence worker did not stop in time")

    # --- watcher thread -------------------------------------------------------------------

    def on_line(self, line: LogLine) -> None:
        try:
            self._feed(line)
        except Exception as exc:  # noqa: BLE001 - the watcher thread must survive a bad line
            now = time.monotonic()
            if now - self._warned_at > WARN_INTERVAL:
                self._warned_at = now
                self._log.warning(f"⚠️ Rich Presence could not read a log line: {exc}")

    def on_rotate(self) -> None:
        self._machine.reset()
        self._unknown_trials.clear()
        self._replaying = True
        self._live_since = 0.0
        self._publish()

    def on_replay_complete(self) -> None:
        """Nothing is published during a replay, so a mid-session start shows one state, not ten."""
        if not self._replaying:
            return
        self._replaying = False
        self._publish()

    def _feed(self, line: LogLine) -> None:
        self._ids.feed(line)
        event = self._parser.parse(line)
        if event is None:
            return
        if self._machine.apply(event, line.ts, live=not line.replay):
            self._note_unknown_trial()
            self._publish()

    def _note_unknown_trial(self) -> None:
        trial_id = self._machine.snapshot.trial_id
        if not trial_id or trial_id in self._unknown_trials:
            return
        if self._catalog.trial(trial_id) is None:
            self._unknown_trials.add(trial_id)
            self._log.debug(f"❓ No catalog entry for trial {trial_id}")

    def _publish(self) -> None:
        if self._replaying:
            if not self._live_since:
                self._live_since = time.monotonic()
            return
        self._mailbox.put(self._machine.snapshot)

    # --- main thread ----------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._mailbox.nudge()

    def set_catalog(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._mailbox.nudge()

    def on_game_started(self) -> None:
        self.game_running = True
        self._machine.reset()
        self._replaying = True
        self._live_since = 0.0
        self._mailbox.nudge()

    def on_game_stopped(self) -> None:
        self.game_running = False
        self._machine.reset()
        self._replaying = True
        self._live_since = 0.0
        self._mailbox.put(self._machine.snapshot)

    # --- worker thread --------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # noqa: BLE001 - one dead feature must not take the app with it
            self._log.error(f"❌ Discord Rich Presence stopped: {exc}")
        finally:
            self._client.clear()
            self._client.close()

    def _loop(self) -> None:
        wait = IDLE_WAIT
        while True:
            state, closed = self._mailbox.take(wait)
            if closed:
                return
            if state is not None and state != self._state:
                self._state = state
                self._changed_at = time.monotonic()
            wait = self._tick()

    def _tick(self) -> float:
        """Publishes what is due and returns how long to sleep before looking again."""
        self._escape_stuck_replay()

        if not self.enabled or not self.game_running:
            self._retire()
            return IDLE_WAIT
        self._retired = False

        payload = render(self._state, self._catalog, self._ids.profile_id)
        if payload == self._last_sent:
            return IDLE_WAIT

        now = time.monotonic()
        settling = self._changed_at and now - self._changed_at < SETTLE
        if settling:
            return SETTLE - (now - self._changed_at)
        if not self._limiter.allow(now):
            return self._limiter.wait_for(now)
        if not self._client.ensure_connected():
            return max(self._client.next_attempt_in(now), 1.0)

        sent = self._client.clear() if payload is None else self._client.update(payload)
        if not sent:
            return max(self._client.next_attempt_in(now), 1.0)
        self._limiter.consume(now)
        self._last_sent = payload
        return IDLE_WAIT

    def _escape_stuck_replay(self) -> None:
        """The tailer always reports the end of a replay; publish anyway if it somehow does not."""
        if not self._replaying or not self._live_since:
            return
        if time.monotonic() - self._live_since > REPLAY_GUARD:
            self._replaying = False
            self._mailbox.put(self._machine.snapshot)

    def _retire(self) -> None:
        """Nothing to show: take the status down and let go of the connection."""
        if self._retired:
            return
        self._retired = True
        self._client.clear()
        self._client.close()
        self._last_sent = None
