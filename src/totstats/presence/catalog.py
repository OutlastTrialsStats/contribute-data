"""Trial names and banner artwork, loaded from assets/trials.json.

The bundled copy is the floor: it ships with the executable and always works offline. A newer copy
downloaded from the repository is cached beside the settings, so new trials show up with their real
names without waiting for an app release. Nothing here raises — a broken catalog costs the presence
its wording, not the app its startup.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from totstats.shared import paths
from totstats.shared.applog import AppLog

# The schema this build understands. A newer major schema is left alone rather than guessed at.
SCHEMA = 1

CACHE_NAME = "trials.json"
META_NAME = "trials.meta.json"

# Where the banner artwork lives. Fixed on purpose: the catalog carries the artwork *keys*, the
# build decides the URL they resolve to, so a downloaded catalog can never point Discord elsewhere.
ASSET_BASE = "https://outlasttrialsstats.com/game-assets/"
ASSET_EXT = ".webp"

DEFAULT_BANNER = "OutlastTrialLogo"

_FALLBACK_DIFFICULTIES = {1: "Introductory", 2: "Standard", 3: "Intensive", 4: "Psychosurgery"}
_FALLBACK_PROGRAMS = {
    "programCHAIN": "Escalation",
    "programINVASION": "Invasion",
    "programCREATOR": "Custom Trial",
}
_FALLBACK_PREFIXES = (("programCore", "Core Program"), ("programBloodDonations", "Blood Drive"))


@dataclass(frozen=True)
class TrialInfo:
    name: str
    banner: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class Catalog:
    revision: int = 0
    trials: dict[str, TrialInfo] = field(default_factory=dict)
    programs: dict[str, str] = field(default_factory=lambda: dict(_FALLBACK_PROGRAMS))
    program_prefixes: tuple[tuple[str, str], ...] = _FALLBACK_PREFIXES
    difficulties: dict[int, str] = field(default_factory=lambda: dict(_FALLBACK_DIFFICULTIES))
    invasion_banners: dict[str, str] = field(default_factory=dict)
    default_banner: str = DEFAULT_BANNER
    profile_url: str = "https://outlasttrialsstats.com/profile/{profile_id}"

    def trial(self, trial_id: str | None) -> TrialInfo | None:
        if not trial_id:
            return None
        return self.trials.get(trial_id) or self.trials.get(trial_id.upper())

    def program_name(self, program_id: str | None) -> str | None:
        if not program_id:
            return None
        known = self.programs.get(program_id)
        if known is not None:
            return known
        for prefix, name in self.program_prefixes:
            if program_id.startswith(prefix):
                return name
        return None

    def difficulty_name(self, level: int | None) -> str | None:
        return self.difficulties.get(level) if level is not None else None

    def image(self, banner: str | None) -> str:
        return f"{ASSET_BASE}{banner or self.default_banner}{ASSET_EXT}"

    def profile_link(self, profile_id: str | None) -> str | None:
        if not profile_id or "{profile_id}" not in self.profile_url:
            return None
        return self.profile_url.replace("{profile_id}", profile_id)


def _string(raw: object, key: str, default: str) -> str:
    value = raw.get(key) if isinstance(raw, dict) else None
    return value if isinstance(value, str) and value else default


def _mapping(raw: object, key: str) -> dict:
    value = raw.get(key) if isinstance(raw, dict) else None
    return value if isinstance(value, dict) else {}


def parse_catalog(raw: object) -> Catalog | None:
    """Build a Catalog from parsed JSON, or None when it is not a catalog we understand."""
    if not isinstance(raw, dict):
        return None
    schema = raw.get("schema")
    if not isinstance(schema, int) or schema != SCHEMA:
        return None

    trials: dict[str, TrialInfo] = {}
    for trial_id, entry in _mapping(raw, "trials").items():
        if not isinstance(trial_id, str) or not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        banner = entry.get("banner")
        location = entry.get("location")
        trials[trial_id] = TrialInfo(
            name=name,
            banner=banner if isinstance(banner, str) and banner else None,
            location=location if isinstance(location, str) and location else None,
        )

    difficulties = dict(_FALLBACK_DIFFICULTIES)
    for level, name in _mapping(raw, "difficulties").items():
        try:
            difficulties[int(level)] = str(name)
        except (TypeError, ValueError):
            continue

    programs = {
        key: str(value)
        for key, value in _mapping(raw, "programs").items()
        if isinstance(key, str) and isinstance(value, str)
    }
    prefixes = tuple(
        (key, str(value))
        for key, value in _mapping(raw, "program_prefixes").items()
        if isinstance(key, str) and isinstance(value, str)
    )
    invasion = {
        key: value
        for key, value in _mapping(raw, "invasion_banners").items()
        if isinstance(key, str) and isinstance(value, str)
    }
    revision = raw.get("revision")

    return Catalog(
        revision=revision if isinstance(revision, int) else 0,
        trials=trials,
        programs=programs or dict(_FALLBACK_PROGRAMS),
        program_prefixes=prefixes or _FALLBACK_PREFIXES,
        difficulties=difficulties,
        invasion_banners=invasion,
        default_banner=_string(raw, "default_banner", DEFAULT_BANNER),
        profile_url=_string(raw, "profile_url", Catalog.profile_url),
    )


def bundled_path() -> Path:
    return paths.asset_path(CACHE_NAME)


def cache_path(cache_dir: Path) -> Path:
    return cache_dir / CACHE_NAME


def meta_path(cache_dir: Path) -> Path:
    return cache_dir / META_NAME


def read_catalog(path: Path) -> Catalog | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parse_catalog(raw)


def load_catalog(log: AppLog, cache_dir: Path | None) -> Catalog:
    """The best catalog available locally. Never touches the network, never raises."""
    bundled = read_catalog(bundled_path())
    if bundled is None:
        log.warning("⚠️ The bundled trial catalog could not be read")

    cached = None
    if cache_dir is not None:
        path = cache_path(cache_dir)
        if path.exists():
            cached = read_catalog(path)
            if cached is None:
                _set_aside(path, log)

    if cached is not None and (bundled is None or cached.revision >= bundled.revision):
        log.debug(f"📦 Using the downloaded trial catalog (revision {cached.revision})")
        return cached
    if bundled is not None:
        log.debug(f"📦 Using the bundled trial catalog (revision {bundled.revision})")
        return bundled
    return Catalog()


def store_cache(cache_dir: Path, body: bytes, etag: str | None, log: AppLog) -> bool:
    """Write the downloaded catalog byte for byte, so its ETag keeps matching."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temp = cache_path(cache_dir).with_suffix(".json.tmp")
        temp.write_bytes(body)
        os.replace(temp, cache_path(cache_dir))
        meta_path(cache_dir).write_text(
            json.dumps({"etag": etag or ""}, indent=2) + "\n", encoding="utf-8"
        )
        return True
    except OSError as exc:
        log.debug(f"📦 Could not cache the trial catalog ({exc})")
        return False


def read_etag(cache_dir: Path) -> str | None:
    try:
        raw = json.loads(meta_path(cache_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    etag = raw.get("etag") if isinstance(raw, dict) else None
    return etag if isinstance(etag, str) and etag else None


def _set_aside(path: Path, log: AppLog) -> None:
    """Keep a damaged download instead of silently overwriting it on the next refresh."""
    try:
        os.replace(path, path.with_suffix(".json.bad"))
        log.warning("⚠️ The downloaded trial catalog was unreadable and has been set aside")
    except OSError:
        pass
