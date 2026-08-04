"""Windows autostart via the HKCU Run key.

The value name and the command string are load-bearing: existing installations already carry
them, and changing either would orphan the old entry and start the app twice.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from totstats.shared import paths

RUN_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OutlastTrialsMonitor"

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - the app is Windows-only; this keeps imports working elsewhere
    winreg = None  # type: ignore[assignment]


def build_command() -> str:
    """The command line Windows should run at logon."""
    if paths.is_frozen():
        return f'"{paths.install_exe()}" --silent'

    script_path = Path(sys.argv[0]).resolve()
    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    return f'"{python_exe}" "{script_path}" --silent'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, build_command())
        return True
    except OSError:
        return False


def disable() -> bool:
    """True if an entry was removed, False if there was nothing to remove."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
