"""Resolves the local player's profile UUID from the game log.

Five independent sources carry it. The old implementation used only the authentication line,
which meant that if the app started after login — the normal case for a mid-session launch, and
guaranteed when replay is capped — it silently never contributed anything.

Sources in resolution order:

1. ``?EncryptionToken=`` on a server ``LoadMap`` — earliest, and present on every map load
2. ``Client authentication succeeded. Profile ID: ...`` — only at login
3. the presence POST URL ``/presence/public/profiles/<uuid>/presence``
4. the third segment of an RTA ``parties|`` / ``matchmaking-tickets|`` data item id
5. ``Player Init Replicated ... IsLocallyControlled = Yes``
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
