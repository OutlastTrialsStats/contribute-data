"""Self-installation into %LOCALAPPDATA%\\TOTStatsMonitor.

Running the downloaded executable copies it into the install directory and relaunches from
there, so the download can be deleted afterwards and autostart has a stable path to point at.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from totstats.shared import paths

_CREATE_NO_WINDOW = 0x08000000


def is_installed_copy() -> bool:
    if not paths.is_frozen():
        return False
    try:
        return Path(sys.executable).resolve() == paths.install_exe().resolve()
    except OSError:
        return False


def ensure_installed() -> bool:
    """Copy the executable into place and relaunch it. True if a relaunch was started."""
    if not paths.is_frozen() or is_installed_copy():
        return False

    target = paths.install_exe()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(sys.executable), target)
    subprocess.Popen([str(target), *sys.argv[1:]], creationflags=_CREATE_NO_WINDOW)
    return True


def schedule_uninstall() -> None:
    """Delete the install directory shortly after this process exits.

    A running executable cannot delete itself, so a detached shell waits and then removes the
    whole directory, taking settings.json and monitor.log with it.
    """
    if not paths.is_frozen():
        return
    install_dir = paths.install_dir()
    if not install_dir.exists():
        return
    command = f'ping -n 3 127.0.0.1 >nul && rmdir /s /q "{install_dir}"'
    subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
    )
