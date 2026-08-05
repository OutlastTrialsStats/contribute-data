"""System tray icon.

pystray runs its own Win32 message loop on a dedicated thread, so menu callbacks must not touch
Tk. Every callback here posts onto the UI queue instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from totstats import APP_NAME
from totstats.shared import windows
from totstats.shared.ui_queue import UiQueue

#: Sampled from the monogram in icon.ico.
_BRAND = (203, 202, 153, 255)


@dataclass(frozen=True)
class TrayCallbacks:
    open_console: Callable[[], None]
    uninstall: Callable[[], None]
    quit: Callable[[], None]
    status_text: Callable[[], str]
    #: Checkbox state readers. pystray calls these on the tray thread every time the menu is
    #: opened, so they must only read — never touch Tk, never write settings.
    autostart_enabled: Callable[[], bool]
    contribute_enabled: Callable[[], bool]
    toggle_autostart: Callable[[], None]
    toggle_contribute: Callable[[], None]


def load_icon_image(icon_path: Path) -> Image.Image:
    if icon_path.exists():
        try:
            return Image.open(icon_path)
        except OSError:
            pass
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle([4, 4, 60, 60], radius=12, fill=_BRAND)
    return image


class _SizedIcon(pystray.Icon):
    """Loads the tray icon at the size the notification area actually draws.

    pystray asks LoadImage for LR_DEFAULTSIZE, which resolves to SM_CXICON — the 32px desktop
    icon, not the 16px SM_CXSMICON the tray uses — and the shell squeezes the result down itself.
    Handing pystray a smaller image does not help: LR_DEFAULTSIZE scales a 16px source up to 32
    first. Reading the .ico at the size we want skips both resamples.

    Resolved per call, not once, so WM_DISPLAYCHANGE picks up a new size: pystray re-runs
    _show(), and with it this method.
    """

    #: Assigned after construction. None falls back to pystray's own loading.
    _icon_file: Path | None = None

    def _assert_icon_handle(self) -> None:
        if self._icon_handle:
            return
        if self._icon_file is not None:
            handle = windows.load_icon(self._icon_file, windows.small_icon_size())
            if handle is not None:
                self._icon_handle = handle
                return
        super()._assert_icon_handle()


class TrayIcon:
    def __init__(self, ui: UiQueue, callbacks: TrayCallbacks, icon_path: Path) -> None:
        self._ui = ui
        self._callbacks = callbacks
        self._icon = _SizedIcon(
            APP_NAME,
            load_icon_image(icon_path),
            f"{APP_NAME} - {callbacks.status_text()}",
            self._build_menu(),
        )
        self._icon._icon_file = icon_path if icon_path.exists() else None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda _item: f"Status: {self._callbacks.status_text()}", None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Contribute player data",
                self._on_toggle_contribute,
                checked=lambda _item: self._callbacks.contribute_enabled(),
            ),
            pystray.MenuItem(
                "Start with Windows",
                self._on_toggle_autostart,
                checked=lambda _item: self._callbacks.autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Console", self._on_console),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Uninstall", self._on_uninstall),
            pystray.MenuItem("Exit", self._on_exit),
        )

    def _on_console(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.open_console)

    def _on_toggle_autostart(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.toggle_autostart)

    def _on_toggle_contribute(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.toggle_contribute)

    def _on_uninstall(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.uninstall)

    def _on_exit(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.quit)

    def run(self) -> None:
        """Blocking; call on a dedicated thread."""
        self._icon.run()

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:  # noqa: BLE001 - shutdown must not fail on a dead message loop
            pass

    def set_status(self, status: str) -> None:
        try:
            self._icon.title = f"{APP_NAME} - {status}"
        except Exception:  # noqa: BLE001
            pass

    def notify(self, message: str, title: str | None = None) -> None:
        try:
            self._icon.notify(message, title or APP_NAME)
        except Exception:  # noqa: BLE001 - balloon tips are best-effort
            pass
