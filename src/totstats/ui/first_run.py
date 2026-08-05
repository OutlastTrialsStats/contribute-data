"""The one question the app asks its user.

Until now autostart was written to the registry on every single start without ever asking. That
is the kind of thing a user discovers months later in Task Manager, and it is the reason this
prompt exists: the answer is recorded once and honoured from then on, in both directions.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from totstats import APP_NAME

_TITLE = f"{APP_NAME} — start automatically?"

_MESSAGE = (
    f"Should {APP_NAME} start automatically when you sign in to Windows?\n\n"
    "It runs quietly in the system tray and only does anything while "
    "The Outlast Trials is running.\n\n"
    "You can change this at any time from the tray icon."
)


def ask_autostart(root: tk.Tk) -> bool:
    """Ask once whether to enable autostart. Returns the user's answer; defaults to No.

    The root window is withdrawn, so without the topmost flag the dialog can open behind
    whatever the user is currently looking at — with no taskbar button to find it by, that
    reads as a frozen app.
    """
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        return bool(messagebox.askyesno(_TITLE, _MESSAGE, parent=root, default=messagebox.NO))
    except tk.TclError:
        # No usable display. Choosing "no" keeps us from writing to the registry unasked.
        return False
    finally:
        try:
            root.attributes("-topmost", False)
        except tk.TclError:
            pass
