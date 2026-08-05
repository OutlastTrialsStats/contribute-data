"""In-memory application log with an optional file sink.

The console window renders this buffer, so entries carry a monotonic sequence number and the
window only ever asks for what it has not seen yet. Named applog rather than logging to avoid
any confusion with the standard library module.
"""

from __future__ import annotations

import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _make_stdout_unicode_safe() -> None:
    """Log messages carry emoji; on a cp1252 console every one would raise UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

DEBUG = "DEBUG"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"

_ORDER = {DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40}


@dataclass(frozen=True)
class LogRecord:
    seq: int
    ts: datetime
    level: str
    message: str

    def format(self) -> str:
        stamp = self.ts.strftime("%Y-%m-%d %H:%M:%S")
        if self.level in (WARNING, ERROR, DEBUG):
            return f"[{stamp}] {self.level} {self.message}"
        return f"[{stamp}] {self.message}"


class AppLog:
    """Thread-safe ring buffer plus an optional append-only file."""

    def __init__(
        self,
        buffer_size: int = 1000,
        file_path: Path | None = None,
        echo_stdout: bool = False,
        level: str = INFO,
    ) -> None:
        self._lock = threading.Lock()
        # Separate from _lock so that emitting a line never blocks the console window reading
        # the buffer, but still serialises writers: the watcher and the HTTP worker both log,
        # and two concurrent appends to the same file tear each other's lines apart.
        self._io_lock = threading.Lock()
        self._buffer: deque[LogRecord] = deque(maxlen=buffer_size)
        self._seq = 0
        self._file_path = file_path
        self._echo_stdout = echo_stdout
        self._level = _ORDER.get(level, _ORDER[INFO])
        self._file_broken = False
        if echo_stdout:
            _make_stdout_unicode_safe()

    def set_level(self, level: str) -> None:
        with self._lock:
            self._level = _ORDER.get(level, _ORDER[INFO])

    def debug(self, message: str) -> None:
        self._write(DEBUG, message)

    def info(self, message: str) -> None:
        self._write(INFO, message)

    def warning(self, message: str) -> None:
        self._write(WARNING, message)

    def error(self, message: str) -> None:
        self._write(ERROR, message)

    def _write(self, level: str, message: str) -> None:
        if _ORDER[level] < self._level:
            return
        with self._lock:
            self._seq += 1
            record = LogRecord(self._seq, datetime.now(), level, message)
            self._buffer.append(record)
            line = record.format()
            path = self._file_path
            echo = self._echo_stdout
            broken = self._file_broken

        with self._io_lock:
            if echo:
                try:
                    # One write per line, newline included: print() emits the text and the
                    # newline separately, so concurrent writers interleave mid-line.
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                except (OSError, ValueError, UnicodeEncodeError, AttributeError):
                    # No console attached, or a codepage that cannot render the message.
                    pass

            if path is not None and not broken:
                try:
                    with open(path, "a", encoding="utf-8") as handle:
                        handle.write(line + "\n")
                except OSError:
                    # Do not let a full or read-only disk take the app down; stop retrying so a
                    # broken sink cannot cost an I/O attempt on every single log line.
                    with self._lock:
                        self._file_broken = True

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def since(self, seq: int) -> list[LogRecord]:
        """Every record newer than seq, oldest first."""
        with self._lock:
            return [record for record in self._buffer if record.seq > seq]

    def rotate_if_large(self, max_bytes: int = 2 * 1024 * 1024) -> None:
        """Truncate the file sink once it grows past max_bytes. Called at startup only."""
        path = self._file_path
        if path is None:
            return
        try:
            if path.exists() and path.stat().st_size > max_bytes:
                path.unlink()
        except OSError:
            pass
