"""Persistent user settings, stored as JSON next to the installation.

Two rules govern everything here:

* **Reading never fails.** A missing, unreadable, truncated or hand-edited file yields defaults
  and a warning, never an exception. Settings are read during startup, before the tray icon
  exists, and the build runs with --noconsole — an exception at that point is an invisible
  crash, and the cost of it is a user whose app silently stopped working.
* **Writing is atomic.** The file is written beside itself and renamed into place, so a crash or
  a full disk mid-write leaves the previous settings intact rather than a half-written file that
  the next start would discard.

`autostart` is deliberately tri-state. None means "never asked", which is what triggers the
first-run consent prompt; True and False are the user's answer and are honoured from then on.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from totstats.shared.applog import AppLog

#: Bumped only when a change cannot be expressed by adding a field with a default.
SCHEMA_VERSION = 1


@dataclass
class Features:
    contribute: bool = True
    #: Reserved for the Discord Rich Presence feature, which is not implemented yet. It is
    #: written from the start so that enabling it later is a value change, not a format change.
    presence: bool = False


@dataclass
class Settings:
    #: None = the user has not been asked yet.
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
        settings.features.presence = _as_bool(features.get("presence"), False)

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

    # -- reading -------------------------------------------------------------

    def load(self) -> Settings:
        if self._path is None:
            return self.settings
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # First start. Not worth a warning.
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

    # -- writing -------------------------------------------------------------

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

    # -- logging -------------------------------------------------------------

    def _warn(self, message: str) -> None:
        if self._log is not None:
            self._log.warning(f"⚙️ {message}")
