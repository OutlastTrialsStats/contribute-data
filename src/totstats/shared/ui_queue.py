"""Marshals work onto the tkinter main thread.

Tk is not thread-safe and pystray runs its own Win32 message loop on another thread, so tray
callbacks must not touch widgets directly. They post a callable here; App._main_loop drains it.
"""

from __future__ import annotations

import queue
from collections.abc import Callable

from totstats.shared.applog import AppLog


class UiQueue:
    def __init__(self, log: AppLog | None = None) -> None:
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._log = log

    def post(self, fn: Callable[[], None]) -> None:
        self._queue.put(fn)

    def drain(self, timeout: float = 0.05) -> None:
        """Run every pending callable. Blocks up to timeout waiting for the first one."""
        try:
            fn = self._queue.get(timeout=timeout)
        except queue.Empty:
            return
        while True:
            self._run(fn)
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                return

    def _run(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a broken menu action must not kill the UI loop
            if self._log is not None:
                self._log.error(f"UI action failed: {exc}")
