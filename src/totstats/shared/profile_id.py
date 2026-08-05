"""Resolves the local player's profile UUID from the game log.

Five independent sources carry it, because the authentication line alone is missing whenever the
app starts after login — the normal case for a mid-session launch, and guaranteed once replay is
capped. _PATTERNS below is their search order.
"""

from __future__ import annotations

import re

from totstats.shared.log_tail import LogLine

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

ENCRYPTION_TOKEN_RE = re.compile(rf"[?&]EncryptionToken=({_UUID})")
AUTH_RE = re.compile(rf"Client authentication succeeded\. Profile ID: ({_UUID})")
PRESENCE_URL_RE = re.compile(rf"/presence/public/profiles/({_UUID})/presence")
DATA_ITEM_RE = re.compile(
    rf'"dataItemId"\s*:\s*"(?:parties|matchmaking-tickets)\|[^|"]*\|({_UUID})"'
)
LOCAL_PLAYER_RE = re.compile(
    rf"\[({_UUID})\],\s+Player Slot = \d+, IsLocallyControlled = Yes"
)

_PATTERNS = (
    ENCRYPTION_TOKEN_RE,
    AUTH_RE,
    PRESENCE_URL_RE,
    DATA_ITEM_RE,
    LOCAL_PLAYER_RE,
)


class OwnProfileIdResolver:
    """Learns the local profile id once and then stops looking."""

    INTERESTS = (
        "EncryptionToken=",
        "Client authentication succeeded",
        "/presence/public/profiles/",
        '"parties|',
        '"matchmaking-tickets|',
        "IsLocallyControlled = Yes",
    )

    def __init__(self) -> None:
        self._profile_id: str | None = None

    @property
    def profile_id(self) -> str | None:
        return self._profile_id

    def reset(self) -> None:
        self._profile_id = None

    def feed(self, line: LogLine) -> str | None:
        """Returns the profile id the first time it is learned, otherwise None."""
        if self._profile_id is not None:
            return None
        for pattern in _PATTERNS:
            match = pattern.search(line.raw)
            if match:
                self._profile_id = match.group(1).lower()
                return self._profile_id
        return None
