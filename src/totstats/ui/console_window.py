"""Live log window.

Driven by App._main_loop rather than tkinter's own mainloop, because the main thread also has to
drain the UI queue. pump() is called on every iteration and appends whatever is new.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from totstats import APP_NAME
from totstats.shared.applog import AppLog

_BACKGROUND = "#1e1e1e"
_FOREGROUND = "#cccccc"


class ConsoleWindow:
    def __init__(self, root: tk.Tk, log: AppLog, icon_path: Path) -> None:
        self._root = root
        self._log = log
        self._icon_path = icon_path
        self._window: tk.Toplevel | None = None
        self._text: tk.Text | None = None
        self._last_seq = 0

    @property
    def is_open(self) -> bool:
        return self._window is not None

    def open(self) -> None:
        if self._window is not None:
            try:
                self._window.deiconify()
                self._window.lift()
                self._window.focus_force()
            except tk.TclError:
                self._window = None
            else:
                return

        window = tk.Toplevel(self._root)
        window.title(f"{APP_NAME} - Console")
        window.geometry("700x400")
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.configure(bg=_BACKGROUND)

        if self._icon_path.exists():
            try:
                window.iconbitmap(str(self._icon_path))
            except tk.TclError:
                pass

        text = tk.Text(
            window,
            bg=_BACKGROUND,
            fg=_FOREGROUND,
            insertbackground=_FOREGROUND,
            font=("Consolas", 10),
            state=tk.DISABLED,
            wrap=tk.WORD,
            borderwidth=0,
        )
        scrollbar = tk.Scrollbar(window, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(fill=tk.BOTH, expand=True)

        self._window = window
        self._text = text
        self._last_seq = 0
        self.pump()

    def close(self) -> None:
        window, self._window, self._text = self._window, None, None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def pump(self) -> None:
        """Append log records written since the last call."""
        if self._window is None or self._text is None:
            return
        records = self._log.since(self._last_seq)
        if not records:
            return
        try:
            self._text.configure(state=tk.NORMAL)
            for record in records:
                self._text.insert(tk.END, record.format() + "\n")
                self._last_seq = record.seq
            self._text.see(tk.END)
            self._text.configure(state=tk.DISABLED)
        except tk.TclError:
            # The window was destroyed from outside our control.
            self._window = None
            self._text = None
