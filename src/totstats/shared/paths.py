"""Filesystem locations, resolved identically in development and in a PyInstaller bundle."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from totstats import APP_NAME

#: Import name of the package; also the directory PyInstaller bundles package data under.
APP_PACKAGE = "totstats"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def _package_dir() -> Path:
    """src/totstats — the directory of the totstats package in a source checkout."""
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    """The repository root in a source checkout (src/totstats/shared -> up three)."""
    return Path(__file__).resolve().parents[3]


def local_appdata() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else Path.home() / "AppData" / "Local"


def install_dir() -> Path:
    """%LOCALAPPDATA%\\TOTStatsMonitor — where the app installs itself and keeps its state."""
    return local_appdata() / APP_NAME


def install_exe() -> Path:
    return install_dir() / f"{APP_NAME}.exe"


def app_log_path() -> Path:
    return install_dir() / "monitor.log"


def settings_path() -> Path:
    return install_dir() / "settings.json"


def default_game_logs_dir() -> Path:
    """%LOCALAPPDATA%\\OPP\\Saved\\Logs — OPP is the game's internal project name."""
    return local_appdata() / "OPP" / "Saved" / "Logs"


def bundled_path(*parts: str) -> Path:
    """A resource bundled at the root of the executable (repository root in development)."""
    root = _bundle_root()
    return (root or _repo_root()).joinpath(*parts)


def package_data_path(*parts: str) -> Path:
    """A data file that lives inside the totstats package, e.g. presence/data/trials.json."""
    root = _bundle_root()
    return (root / APP_PACKAGE if root else _package_dir()).joinpath(*parts)


def icon_path() -> Path:
    return bundled_path("icon.ico")
