"""Windows autostart via the HKCU Run key.

The value name is load-bearing: an installation out in the wild already carries one, and simply
writing a differently named value would leave the old entry behind and start the app twice. The
name is being unified on APP_NAME, so anything written under an older name has to be migrated
rather than ignored — see migrate_legacy().
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from totstats import APP_NAME
from totstats.shared import paths

RUN_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = APP_NAME

#: Names used by earlier releases, newest first. Read and cleaned up, never written.
LEGACY_VALUE_NAMES = ("OutlastTrialsMonitor",)

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


def _has_value(name: str) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, name)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _delete_value(name: str) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def is_enabled() -> bool:
    return _has_value(VALUE_NAME)


def legacy_names_present() -> tuple[str, ...]:
    """Value names from earlier releases that are still in the Run key."""
    return tuple(name for name in LEGACY_VALUE_NAMES if _has_value(name))


def migrate_legacy() -> bool:
    """Adopt an entry written by an earlier release under its old name.

    True when one was found. The user already consented to autostart back then, so the entry is
    rewritten under the current name and the old one removed — asking again would be rude, and
    leaving it would launch two copies at logon.
    """
    found = legacy_names_present()
    if not found:
        return False
    enable()
    for name in found:
        _delete_value(name)
    return True


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
    """Remove every entry we may have written, current or legacy.

    True if at least one was removed. Uninstall and the tray toggle both rely on this leaving
    nothing behind, so it must not stop at the current name.
    """
    removed = _delete_value(VALUE_NAME)
    for name in LEGACY_VALUE_NAMES:
        removed = _delete_value(name) or removed
    return removed
