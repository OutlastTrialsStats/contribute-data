"""Wires the log tailer to the contribute API: on_line enqueues, a worker thread sends."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from totstats.contribute.api import ContributeApi
from totstats.contribute.parser import ContributeParser
from totstats.shared.applog import AppLog
from totstats.shared.log_tail import LogLine
from totstats.shared.profile_id import OwnProfileIdResolver

_SHUTDOWN = object()


@dataclass
class ContributeStats:
    sent: int = 0
    already_known: int = 0
    failed: int = 0
    dropped: int = 0


class ContributeService:
    INTERESTS = ContributeParser.INTERESTS + OwnProfileIdResolver.INTERESTS

    def __init__(
        self,
        api: ContributeApi,
        ids: OwnProfileIdResolver,
        log: AppLog,
        queue_size: int = 512,
    ) -> None:
        self._api = api
        self._ids = ids
        self._log = log
        self._parser = ContributeParser()

        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._worker: threading.Thread | None = None
        self._seen: set[str] = set()
        self._pending: list[str] = []
        self.stats = ContributeStats()

        # Checked per line rather than by unsubscribing, so the tray toggle takes effect at
        # once. Needs no lock: the watcher thread only ever reads it.
        self.enabled = True

    def start(self) -> None:
        if self._worker is not None:
            return
        self._worker = threading.Thread(
            target=self._run, name="contribute-http", daemon=True
        )
        self._worker.start()

    def stop(self, timeout: float = 3.0) -> None:
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        try:
            self._queue.put_nowait(_SHUTDOWN)
        except queue.Full:
            pass
        worker.join(timeout)
        if worker.is_alive():
            self._log.warning("contribute worker did not stop in time")

    def on_rotate(self) -> None:
        """A new log file means a new game session: everyone is worth reporting again."""
        self._seen.clear()
        self._pending.clear()
        self._ids.reset()

    def on_line(self, line: LogLine) -> None:
        if not self.enabled:
            return

        learned = self._ids.feed(line)
        if learned is not None:
            self._log.info(f"🆔 Player ID found: {learned[:8]}…")
            self._flush_pending()

        player = self._parser.parse(line)
        if player is None or player.is_local:
            return
        if player.profile_id in self._seen:
            return
        self._seen.add(player.profile_id)

        # Replayed players are pre-existing content, not news — announce them at debug level so
        # a --dry-run --verbose replay still shows who was found.
        message = f"🎮 New player: {player.name} (Slot {player.slot})"
        if line.replay:
            self._log.debug(message)
        else:
            self._log.info(message)

        if self._ids.profile_id is None:
            # Seen before we learned who we are; report once the id turns up.
            self._pending.append(player.profile_id)
            return
        self._enqueue(player.profile_id)

    def _flush_pending(self) -> None:
        pending, self._pending = self._pending, []
        for profile_id in pending:
            self._enqueue(profile_id)

    def _enqueue(self, profile_id: str) -> None:
        try:
            self._queue.put_nowait(profile_id)
        except queue.Full:
            self.stats.dropped += 1
            self._log.warning(f"contribute queue full, dropped {profile_id[:8]}…")

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SHUTDOWN:
                return
            contributor_id = self._ids.profile_id
            if contributor_id is None:
                continue
            self._report(contributor_id, item)

    def _report(self, contributor_id: str, profile_id: str) -> None:
        result = self._api.contribute(contributor_id, profile_id)
        short = f"{profile_id[:8]}…"
        if result.dry_run:
            self.stats.sent += 1
            self._log.info(f"🧪 Would contribute: {short}")
        elif result.already_known:
            self.stats.already_known += 1
            self._log.info(f"ℹ️ Player already known: {short}")
        elif result.ok:
            self.stats.sent += 1
            self._log.info(f"✅ Player data sent successfully: {short}")
        elif result.status is None:
            self.stats.failed += 1
            self._log.warning(f"❌ Network error for {short}: {result.error}")
        else:
            self.stats.failed += 1
            self._log.warning(f"⚠️ API error for {short} (status {result.status})")
