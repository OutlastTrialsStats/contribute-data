"""Detects whether The Outlast Trials is running."""

from __future__ import annotations

from dataclasses import dataclass

import psutil

PROCESS_MARKER = "TOTClient"


@dataclass(frozen=True)
class GameProcessEvent:
    running: bool
    pid: int | None
    started_at: float | None = None


class GameProcessWatcher:
    """Edge-triggered process detection.

    While the game is running we hold onto its psutil.Process, whose is_running() compares the
    creation time and so cannot be fooled by PID reuse. That turns the common case into a single
    cheap syscall instead of a full process table scan every few seconds.
    """

    def __init__(self, marker: str = PROCESS_MARKER) -> None:
        self._marker = marker
        self._process: psutil.Process | None = None

    @property
    def running(self) -> bool:
        return self._process is not None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def started_at(self) -> float | None:
        if self._process is None:
            return None
        try:
            return self._process.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def poll(self) -> GameProcessEvent | None:
        """Returns an event only when the running state changed since the last poll."""
        was_running = self._process is not None
        now_running = self._refresh()
        if was_running == now_running:
            return None
        return GameProcessEvent(running=now_running, pid=self.pid, started_at=self.started_at)

    def reset(self) -> None:
        self._process = None

    def _refresh(self) -> bool:
        if self._process is not None:
            try:
                if self._process.is_running() and self._process.status() != psutil.STATUS_ZOMBIE:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self._process = None

        self._process = self._find()
        return self._process is not None

    def _find(self) -> psutil.Process | None:
        for process in psutil.process_iter(["name", "exe"]):
            try:
                info = process.info
                name = info.get("name") or ""
                exe = info.get("exe") or ""
                if self._marker in name or self._marker in exe:
                    return process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
