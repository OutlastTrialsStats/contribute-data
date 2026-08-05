"""Persistent user settings, stored as JSON next to the installation.

Reading never raises — the build runs with --noconsole, so an exception during startup is an
invisible crash. Writing is atomic: written beside itself and renamed into place.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from totstats.shared.applog import AppLog

# Bumped only when a change cannot be expressed by adding a field with a default.
SCHEMA_VERSION = 1


@dataclass
class Features:
    contribute: bool = True
    presence: bool = True


@dataclass
class Settings:
    # None = not resolved yet; a frozen build then defaults to on.
    autostart: bool | None = None
    features: Features = field(default_factory=Features)


def _as_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _parse(raw: object) -> Settings:
    """Build Settings from parsed JSON, ignoring anything unexpected."""
    settings = Settings()
    if not isinstance(raw, dict):
        return settings

    autostart = raw.get("autostart")
    if isinstance(autostart, bool):
        settings.autostart = autostart

    features = raw.get("features")
    if isinstance(features, dict):
        settings.features.contribute = _as_bool(features.get("contribute"), True)
        settings.features.presence = _as_bool(features.get("presence"), True)

    return settings


def _serialise(settings: Settings) -> dict:
    return {
        "version": SCHEMA_VERSION,
        "autostart": settings.autostart,
        "features": {
            "contribute": settings.features.contribute,
            "presence": settings.features.presence,
        },
    }


class SettingsStore:
    """Owns the settings file. Pass path=None for an in-memory store (used by --dry-run)."""

    def __init__(self, path: Path | None, log: AppLog | None = None) -> None:
        self._path = path
        self._log = log
        self._lock = threading.Lock()
        self.settings = Settings()

    @property
    def path(self) -> Path | None:
        return self._path

    def load(self) -> Settings:
        if self._path is None:
            return self.settings
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self.settings
        except OSError as exc:
            self._warn(f"could not read settings ({exc}); using defaults")
            return self.settings

        try:
            raw = json.loads(text)
        except ValueError as exc:
            self._warn(f"settings file is not valid JSON ({exc}); using defaults")
            self._preserve_broken()
            return self.settings

        self.settings = _parse(raw)
        return self.settings

    def _preserve_broken(self) -> None:
        """Keep a damaged file instead of silently overwriting it on the next save."""
        if self._path is None:
            return
        try:
            os.replace(self._path, self._path.with_suffix(".json.bad"))
            self._warn(f"kept the previous file as {self._path.with_suffix('.json.bad').name}")
        except OSError:
            pass

    def save(self) -> bool:
        """True when the settings reached disk. An in-memory store always reports True."""
        if self._path is None:
            return True
        payload = json.dumps(_serialise(self.settings), indent=2) + "\n"
        temp = self._path.with_suffix(".json.tmp")
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temp.write_text(payload, encoding="utf-8")
                os.replace(temp, self._path)
                return True
            except OSError as exc:
                self._warn(f"could not save settings ({exc})")
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                return False

    def _warn(self, message: str) -> None:
        if self._log is not None:
            self._log.warning(f"⚙️ {message}")
