"""Incremental tailing of the game's Unreal Engine log, shared by every feature.

One tailer serves all subscribers so the log is read once, not once per feature. Why it reads
the way it does — binary reads split on newlines, no handle kept open between polls, OPP.log
preferred over newest-by-mtime — is in doc/architecture.md.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from totstats.shared.applog import AppLog

# [2026.08.02-15.35.43:756][138]RB:  GamePhase changed to ...
LINE_PREFIX_RE = re.compile(
    r"^\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2}):(\d{3})\]\[\s*(\d+)\](.*)$"
)

_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class LogLine:
    raw: str

    body: str
    """The line with the [timestamp][frame] prefix stripped; equals raw when there is none."""

    ts: datetime | None
    """Naive local time from the prefix, or None for header/footer lines."""

    frame: int | None

    replay: bool
    """True while replaying content that existed before the tailer opened the file."""


def parse_line(raw: str, replay: bool = False) -> LogLine:
    match = LINE_PREFIX_RE.match(raw)
    if match is None:
        return LogLine(raw=raw, body=raw, ts=None, frame=None, replay=replay)

    year, month, day, hour, minute, second, milli, frame, body = match.groups()
    try:
        ts: datetime | None = datetime(
            int(year), int(month), int(day), int(hour), int(minute), int(second), int(milli) * 1000
        )
    except ValueError:
        ts = None
    return LogLine(raw=raw, body=body, ts=ts, frame=int(frame), replay=replay)


LineSink = Callable[[LogLine], None]
EventSink = Callable[[], None]


@dataclass(frozen=True)
class _Subscription:
    name: str
    sink: LineSink
    needles: tuple[str, ...]
    on_rotate: EventSink | None
    on_replay_complete: EventSink | None


class LogTailer:
    """Polls one log file and dispatches new lines to its subscribers.

    Subscriber sinks run on the caller's thread and must not block — they are expected to hand
    work off to a queue or mailbox. poll() never raises.
    """

    def __init__(
        self,
        logs_dir: Path,
        primary_name: str = "OPP.log",
        max_replay_bytes: int = 16 * 1024 * 1024,
        max_bytes_per_poll: int = 4 * 1024 * 1024,
        log: AppLog | None = None,
    ) -> None:
        self._logs_dir = logs_dir
        self._primary_name = primary_name
        self._max_replay_bytes = max_replay_bytes
        self._max_bytes_per_poll = max_bytes_per_poll
        self._log = log

        self._subs: list[_Subscription] = []
        self._union_needles: tuple[str, ...] | None = ()

        self._path: Path | None = None
        self._identity: tuple[int, int] | None = None
        self._offset = 0
        self._pending = b""
        self._discard_partial = False
        self._replay_until = 0
        self._replaying = False
        self._missing_logged = False

    def subscribe(
        self,
        sink: LineSink,
        needles: Sequence[str] = (),
        on_rotate: EventSink | None = None,
        on_replay_complete: EventSink | None = None,
        name: str = "subscriber",
    ) -> None:
        """Register a sink. needles are literal substrings; an empty sequence means every line."""
        self._subs.append(
            _Subscription(
                name=name,
                sink=sink,
                needles=tuple(needles),
                on_rotate=on_rotate,
                on_replay_complete=on_replay_complete,
            )
        )
        self._recompute_union()

    def _recompute_union(self) -> None:
        # A subscriber that wants everything disables the cheap global pre-filter.
        if any(not sub.needles for sub in self._subs):
            self._union_needles = None
            return
        merged: list[str] = []
        for sub in self._subs:
            merged.extend(sub.needles)
        self._union_needles = tuple(dict.fromkeys(merged))

    @property
    def current_file(self) -> Path | None:
        return self._path

    @property
    def replaying(self) -> bool:
        return self._replaying

    def reset(self) -> None:
        self._path = None
        self._identity = None
        self._offset = 0
        self._pending = b""
        self._discard_partial = False
        self._replay_until = 0
        self._replaying = False
        self._missing_logged = False

    close = reset

    def poll(self) -> int:
        """Read whatever is new and dispatch it. Returns the number of lines dispatched."""
        try:
            return self._poll()
        except OSError:
            # The game may rotate, lock or delete the file at any moment. Nothing here is worth
            # taking the watcher thread down for.
            return 0
        except Exception as exc:  # noqa: BLE001 - the watcher thread must survive anything
            self._warn(f"log tailer error: {exc}")
            return 0

    def _poll(self) -> int:
        path = self._select_file()
        if path is None:
            if not self._missing_logged:
                self._info(f"waiting for a game log in {self._logs_dir}")
                self._missing_logged = True
            return 0
        self._missing_logged = False

        stat = os.stat(path)
        identity = (stat.st_ino, stat.st_ctime_ns)

        if self._path != path or self._identity != identity:
            self._begin_file(path, identity, stat.st_size, rotated=self._path is not None)
        elif stat.st_size < self._offset:
            # Same file, fewer bytes: the game truncated it.
            self._begin_file(path, identity, stat.st_size, rotated=True)

        return self._read_and_dispatch(path)

    def _select_file(self) -> Path | None:
        """OPP.log is always the live file; fall back to newest-by-mtime only if it is absent."""
        primary = self._logs_dir / self._primary_name
        try:
            if primary.is_file():
                return primary
            candidates = [p for p in self._logs_dir.glob("*.log") if p.is_file()]
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _begin_file(self, path: Path, identity: tuple[int, int], size: int, rotated: bool) -> None:
        previous = self._path
        self._path = path
        self._identity = identity
        self._pending = b""

        if size > self._max_replay_bytes:
            self._offset = size - self._max_replay_bytes
            self._discard_partial = True
        else:
            self._offset = 0
            self._discard_partial = False

        self._replay_until = size
        self._replaying = True

        if rotated and previous is not None:
            self._info(f"log file rotated, now following {path.name}")
        else:
            self._info(f"following log file {path.name}")

        if rotated:
            for sub in self._subs:
                self._fire(sub, sub.on_rotate, "on_rotate")

    def _read_and_dispatch(self, path: Path) -> int:
        with open(path, "rb") as handle:
            handle.seek(self._offset)
            chunk = handle.read(self._max_bytes_per_poll)

        if not chunk:
            if self._replaying:
                self._finish_replay()
            return 0

        if self._offset == 0 and chunk.startswith(_BOM):
            chunk = chunk[len(_BOM):]
            self._offset += len(_BOM)

        self._offset += len(chunk)
        buffer = self._pending + chunk

        if self._discard_partial:
            # We seeked into the middle of a line; everything up to the first newline is the
            # tail of a line we never saw the start of. Stay in discard mode until one turns up,
            # otherwise a chunk without any newline would let the fragment through.
            _, found, buffer = buffer.partition(b"\n")
            if not found:
                self._pending = b""
                return 0
            self._discard_partial = False

        complete, newline, self._pending = buffer.rpartition(b"\n")

        dispatched = 0
        if newline and complete:
            replay = self._replaying
            for raw in complete.split(b"\n"):
                line = raw.rstrip(b"\r")
                if not line:
                    continue
                self._dispatch(line.decode("utf-8", "replace"), replay)
                dispatched += 1

        if self._replaying and self._offset >= self._replay_until:
            self._finish_replay()

        return dispatched

    def _finish_replay(self) -> None:
        self._replaying = False
        for sub in self._subs:
            self._fire(sub, sub.on_replay_complete, "on_replay_complete")

    def _dispatch(self, raw: str, replay: bool) -> None:
        union = self._union_needles
        if union is not None and not any(needle in raw for needle in union):
            return

        line = parse_line(raw, replay)
        for sub in self._subs:
            if sub.needles and not any(needle in raw for needle in sub.needles):
                continue
            try:
                sub.sink(line)
            except Exception as exc:  # noqa: BLE001 - one bad sink must not stop the others
                self._warn(f"subscriber {sub.name} failed: {exc}")

    def _fire(self, sub: _Subscription, hook: EventSink | None, what: str) -> None:
        if hook is None:
            return
        try:
            hook()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"subscriber {sub.name} {what} failed: {exc}")

    def _info(self, message: str) -> None:
        if self._log is not None:
            self._log.info(f"📄 {message}")

    def _warn(self, message: str) -> None:
        if self._log is not None:
            self._log.warning(message)
