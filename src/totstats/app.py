"""Application wiring and lifecycle.

Threads:

============  ==========================================================================
main          Tk (hidden root, console window), draining the UI queue
tray          pystray's Win32 message loop
watcher       game process detection and log tailing; dispatches lines to services
contribute    the HTTP worker owned by ContributeService
============  ==========================================================================

Only the main thread touches Tk, and only the watcher thread touches parser state.
"""

from __future__ import annotations

import argparse
import threading
import time
import tkinter as tk
from pathlib import Path

from totstats import APP_NAME, __version__
from totstats.contribute.api import ContributeApi
from totstats.contribute.service import ContributeService
from totstats.shared import autostart, installer, paths
from totstats.shared.applog import AppLog
from totstats.shared.game_process import GameProcessEvent, GameProcessWatcher
from totstats.shared.log_tail import LogTailer
from totstats.shared.profile_id import OwnProfileIdResolver
from totstats.shared.ui_queue import UiQueue
from totstats.ui.console_window import ConsoleWindow
from totstats.ui.tray import TrayCallbacks, TrayIcon

#: How often to poll the log while the game is running. Fast enough that state is fresh,
#: cheap enough to be free: the game writes roughly 700 bytes per second.
TAIL_INTERVAL = 0.25
#: How often to look for the game process, in seconds. Measured in wall time, not loop
#: iterations, so a busy log cannot turn this into a hot loop.
PROCESS_INTERVAL = 3.0
IDLE_INTERVAL = 1.0


class App:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self._stop = threading.Event()
        self._uninstalling = False

        # A dry run must not touch the real installation: no monitor.log entries mixed into a
        # user's diagnostics, no directory created on a machine that never installed the app.
        # It writes beside the working directory instead, which is also the only way to see
        # anything at all from the --noconsole build.
        log_file: Path | None = None
        if args.dry_run:
            log_file = Path.cwd() / "totstats-dryrun.log"
        else:
            try:
                paths.install_dir().mkdir(parents=True, exist_ok=True)
                log_file = paths.app_log_path()
            except OSError:
                pass

        self.log = AppLog(
            file_path=log_file,
            echo_stdout=not args.silent,
            level="DEBUG" if args.verbose else "INFO",
        )
        self.log.rotate_if_large()

        self.ui = UiQueue(self.log)
        self._root: tk.Tk | None = None
        self._console: ConsoleWindow | None = None
        self._tray: TrayIcon | None = None

        logs_dir = Path(args.logs_dir) if args.logs_dir else paths.default_game_logs_dir()
        self._ids = OwnProfileIdResolver()
        self._game = GameProcessWatcher()
        self._tailer = LogTailer(logs_dir, log=self.log)
        self._api = ContributeApi(dry_run=args.dry_run)
        self.contribute = ContributeService(self._api, self._ids, self.log)

        self._tailer.subscribe(
            self.contribute.on_line,
            needles=ContributeService.INTERESTS,
            on_rotate=self.contribute.on_rotate,
            name="contribute",
        )

    # -- status --------------------------------------------------------------

    def status_text(self) -> str:
        if self.args.dry_run:
            return "Dry run"
        return "Monitoring" if self._game.running else "Waiting for game"

    # -- lifecycle -----------------------------------------------------------

    def run(self) -> int:
        self.log.info(f"🚀 {APP_NAME} v{__version__} started")
        if self.args.dry_run:
            self.log.info("🧪 Dry run: reading logs without the game, nothing is sent")
        else:
            autostart.enable()

        self._root = tk.Tk()
        self._root.withdraw()
        self._console = ConsoleWindow(self._root, self.log, paths.icon_path())

        self.contribute.start()

        watcher = threading.Thread(target=self._watch_loop, name="watcher", daemon=True)
        watcher.start()

        self._tray = TrayIcon(
            self.ui,
            TrayCallbacks(
                open_console=self._open_console,
                uninstall=self._uninstall,
                quit=self.request_quit,
                status_text=self.status_text,
            ),
            paths.icon_path(),
        )
        tray_thread = threading.Thread(target=self._tray.run, name="tray", daemon=True)
        tray_thread.start()

        try:
            self._main_loop()
        except KeyboardInterrupt:
            pass
        self._shutdown(watcher)
        return 0

    def request_quit(self) -> None:
        self.log.info("🛑 Shutting down…")
        self._stop.set()

    def _open_console(self) -> None:
        if self._console is not None:
            self._console.open()

    def _uninstall(self) -> None:
        self._uninstalling = True
        if autostart.disable():
            self.log.info("✅ Autostart removed")
        self.log.info("🗑️ Uninstalling…")
        self._stop.set()

    # -- main thread ---------------------------------------------------------

    def _main_loop(self) -> None:
        assert self._root is not None
        while not self._stop.is_set():
            self.ui.drain(timeout=0.05)
            if self._console is not None and self._console.is_open:
                self._console.pump()
            try:
                self._root.update()
            except tk.TclError:
                return

    # -- watcher thread ------------------------------------------------------

    def _watch_loop(self) -> None:
        next_process_check = 0.0
        while not self._stop.is_set():
            if not self.args.dry_run:
                now = time.monotonic()
                if now >= next_process_check:
                    next_process_check = now + PROCESS_INTERVAL
                    event = self._game.poll()
                    if event is not None:
                        self._on_game_event(event)

                if not self._game.running:
                    self._stop.wait(IDLE_INTERVAL)
                    continue

            self._tailer.poll()
            if self._tailer.replaying:
                continue
            self._stop.wait(TAIL_INTERVAL if self._tailer.current_file else IDLE_INTERVAL)

    def _on_game_event(self, event: GameProcessEvent) -> None:
        if event.running:
            self.log.info("🎮 The Outlast Trials detected, monitoring started")
            self._ids.reset()
            self._tailer.reset()
            self.contribute.on_rotate()
        else:
            self.log.info("🛑 The Outlast Trials closed, monitoring stopped")
            self._tailer.reset()
        self._update_tray()

    def _update_tray(self) -> None:
        if self._tray is not None:
            self._tray.set_status(self.status_text())

    # -- shutdown ------------------------------------------------------------

    def _shutdown(self, watcher: threading.Thread) -> None:
        self._stop.set()
        self.contribute.stop()
        self._api.close()
        watcher.join(2.0)
        self._tailer.close()

        if self._tray is not None:
            self._tray.stop()
        if self._console is not None:
            self._console.close()
        if self._root is not None:
            try:
                self._root.destroy()
            except tk.TclError:
                pass

        # Deleting the install directory has to be the very last thing: it takes monitor.log
        # with it, and on a frozen build the running executable lives inside it.
        if self._uninstalling:
            installer.schedule_uninstall()
