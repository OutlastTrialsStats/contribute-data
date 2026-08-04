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
from totstats.shared.ui_queue import UiQueue


@dataclass(frozen=True)
class TrayCallbacks:
    open_console: Callable[[], None]
    uninstall: Callable[[], None]
    quit: Callable[[], None]
    status_text: Callable[[], str]


def load_icon_image(icon_path: Path) -> Image.Image:
    if icon_path.exists():
        try:
            return Image.open(icon_path)
        except OSError:
            pass
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(180, 180, 180, 255))
    draw.text((size // 2 - 8, size // 2 - 10), "OT", fill=(255, 255, 255, 255))
    return image


class TrayIcon:
    def __init__(self, ui: UiQueue, callbacks: TrayCallbacks, icon_path: Path) -> None:
        self._ui = ui
        self._callbacks = callbacks
        self._icon = pystray.Icon(
            APP_NAME,
            load_icon_image(icon_path),
            f"{APP_NAME} - {callbacks.status_text()}",
            self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda _item: f"Status: {self._callbacks.status_text()}", None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Console", self._on_console),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Uninstall", self._on_uninstall),
            pystray.MenuItem("Exit", self._on_exit),
        )

    # -- menu actions (tray thread) ------------------------------------------

    def _on_console(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.open_console)

    def _on_uninstall(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.uninstall)

    def _on_exit(self, _icon: object, _item: object) -> None:
        self._ui.post(self._callbacks.quit)

    # -- lifecycle -----------------------------------------------------------

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
