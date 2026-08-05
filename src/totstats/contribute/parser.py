"""Extracts the players in your session from the game log."""

from __future__ import annotations

import re
from dataclasses import dataclass

from totstats.shared.log_tail import LogLine

# RB:  [Name] Player Init Replicated. Player Id = Name [TAG] [uuid],  Player Slot = 3,
#      IsLocallyControlled = No
#
# Anchored on the UUID, not on the brackets around the display name — see doc/log-format.md.
PLAYER_RE = re.compile(
    r"Player Init Replicated\. Player Id = (?P<name>.*?) \[(?P<tag>[^\]]*)\] "
    r"\[(?P<uuid>[0-9a-fA-F-]{36})\],\s+Player Slot = (?P<slot>\d+), "
    r"IsLocallyControlled = (?P<local>Yes|No)"
)


@dataclass(frozen=True)
class SeenPlayer:
    name: str
    tag: str
    profile_id: str
    slot: int
    is_local: bool


class ContributeParser:
    INTERESTS = ("Player Init Replicated",)

    def parse(self, line: LogLine) -> SeenPlayer | None:
        match = PLAYER_RE.search(line.raw)
        if match is None:
            return None
        return SeenPlayer(
            name=match.group("name"),
            tag=match.group("tag"),
            profile_id=match.group("uuid").lower(),
            slot=int(match.group("slot")),
            is_local=match.group("local") == "Yes",
        )
