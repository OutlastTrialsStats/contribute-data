"""Turns game log lines into typed presence events.

Pure and stateless: every function here maps one line to at most one event, so the state machine
in state.py owns all the interpretation. Anything the game words differently after a patch has to
degrade to None here rather than raise — the watcher thread runs this.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from totstats.shared.log_tail import LogLine

# OnlineCoreHttpLogs: Verbose: Operation FCoreUpdatePresenceOperation(83) request body: {...}
#
# Anchored on the operation name, never on "request body:" alone: other operations log bodies too
# and some of them contain session tokens. Verified against real logs: the body is always on the
# same line as the operation name.
PRESENCE_OP = "FCoreUpdatePresenceOperation"
REQUEST_BODY = "request body:"

# RB:  GameStageInfo changed. Program ID: programCoreCH, Trial ID: CHJ_MT03,
#      Program difficulty: Normal, Stage: CourthouseJudicial, Mission: CHJ_MT03, Seed: 617617,
#      EffectiveNumberOfPlayers: 1
STAGE_INFO_RE = re.compile(
    r"GameStageInfo changed\..*?Program ID:\s*(?P<program>\w+).*?Trial ID:\s*(?P<trial>\w+)"
    r".*?Program difficulty:\s*(?P<difficulty>\w+).*?Stage:\s*(?P<stage>\w+)"
    r".*?EffectiveNumberOfPlayers:\s*(?P<players>\d+)"
)

# RB:  GamePhase changed to StageStarted from StageReady.
PHASE_RE = re.compile(r"GamePhase changed to (?P<to>\w+) from (?P<from>\w+)")

# LogLoad: LoadMap: 1.2.3.4:7778/Game/Maps/Global/OPP_Persistent?...?Source=Lobby?game=...
SOURCE_RE = re.compile(r"[?&]Source=(\w+)")

MAP_MAIN_MENU = "mainmenu"
MAP_LOBBY = "lobby"
MAP_TRIAL = "trial"

_MAPS = (
    ("/Game/Maps/Global/MainMenu", MAP_MAIN_MENU),
    ("/Game/Maps/Lobby/Lobby_Persistent", MAP_LOBBY),
    ("/Game/Maps/Global/OPP_Persistent", MAP_TRIAL),
)

# Difficulty reaches us as text ~1.5 s before the presence body carries the number.
DIFFICULTY_BY_TEXT = {"Easy": 1, "Normal": 2, "Hard": 3, "Insane": 4}


@dataclass(frozen=True)
class PresencePost:
    """The presence the game publishes about itself — the authoritative view of own state."""

    presence_state: str | None
    program_id: str | None
    trial_id: str | None
    difficulty: int | None
    chain_step: int | None
    player_count: int | None
    invasion_state: str | None


@dataclass(frozen=True)
class StageInfo:
    program_id: str | None
    trial_id: str | None
    difficulty: int | None
    stage: str | None
    players: int | None


@dataclass(frozen=True)
class PhaseChange:
    to_phase: str
    from_phase: str


@dataclass(frozen=True)
class MapLoad:
    kind: str
    source: str | None


@dataclass(frozen=True)
class PartyRoster:
    item_id: str
    members: int
    max_size: int | None


@dataclass(frozen=True)
class GameExit:
    pass


Event = PresencePost | StageInfo | PhaseChange | MapLoad | PartyRoster | GameExit


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _count(value: object) -> int | None:
    """Player counts arrive as ints in own bodies and as floats in received messages."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = int(value)
    return number if number > 0 else None


def _difficulty(value: object) -> int | None:
    number = _count(value)
    return number if number is not None and 1 <= number <= 4 else None


def _chain_step(value: object) -> int | None:
    """-1 outside a chain, 0 inside a plain trial; only a positive step means Escalation."""
    return _count(value)


class PresenceParser:
    INTERESTS = (
        PRESENCE_OP,
        "GameStageInfo changed",
        "GamePhase changed to ",
        "LogLoad: LoadMap:",
        '"parties|',
        "LogExit: Exiting.",
    )

    def parse(self, line: LogLine) -> Event | None:
        raw = line.raw
        if PRESENCE_OP in raw:
            return self._presence(raw)
        if "GameStageInfo changed" in raw:
            return self._stage_info(raw)
        if "GamePhase changed to " in raw:
            return self._phase(raw)
        if "LogLoad: LoadMap:" in raw:
            return self._map(raw)
        if '"parties|' in raw:
            return self._party(raw)
        if "LogExit: Exiting." in raw:
            return GameExit()
        return None

    def _presence(self, raw: str) -> PresencePost | None:
        marker = raw.find(REQUEST_BODY)
        if marker < 0:
            return None
        body = _load_json(raw, raw.find("{", marker))
        if body is None:
            return None
        properties = body.get("properties")
        if not isinstance(properties, dict):
            return None
        return PresencePost(
            presence_state=_text(properties.get("presenceState")),
            program_id=_text(properties.get("programId")),
            trial_id=_text(properties.get("trialId")),
            difficulty=_difficulty(properties.get("programDifficulty")),
            chain_step=_chain_step(properties.get("trialChain")),
            player_count=_count(properties.get("playerCount")),
            invasion_state=_text(properties.get("invasionState")),
        )

    def _stage_info(self, raw: str) -> StageInfo | None:
        match = STAGE_INFO_RE.search(raw)
        if match is None:
            return None
        return StageInfo(
            program_id=match.group("program"),
            trial_id=match.group("trial"),
            difficulty=DIFFICULTY_BY_TEXT.get(match.group("difficulty")),
            stage=match.group("stage"),
            players=_count(int(match.group("players"))),
        )

    def _phase(self, raw: str) -> PhaseChange | None:
        match = PHASE_RE.search(raw)
        if match is None:
            return None
        return PhaseChange(to_phase=match.group("to"), from_phase=match.group("from"))

    def _map(self, raw: str) -> MapLoad | None:
        for needle, kind in _MAPS:
            if needle in raw:
                source = SOURCE_RE.search(raw)
                return MapLoad(kind=kind, source=source.group(1) if source else None)
        return None

    def _party(self, raw: str) -> PartyRoster | None:
        """The party roster, from the only RTA message that carries our own party.

        team1 is the roster as pipe-joined profile ids. allowList is the invite list and
        matchProfileIds are matchmaking candidates — neither is a party size.
        """
        message = _load_json(raw, raw.find("{"))
        if message is None:
            return None
        item_id = _text(message.get("dataItemId"))
        if item_id is None or not item_id.startswith("parties|"):
            return None
        data = message.get("data")
        if not isinstance(data, dict):
            return None
        party_data = data.get("partyData")
        if not isinstance(party_data, dict):
            return None
        team = _text(party_data.get("team1"))
        if team is None:
            return None
        members = len([member for member in team.split("|") if member])
        if members == 0:
            return None
        return PartyRoster(item_id=item_id, members=members, max_size=_count(data.get("maxSize")))


def _load_json(raw: str, start: int) -> dict | None:
    if start < 0:
        return None
    try:
        parsed = json.loads(raw[start:])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
