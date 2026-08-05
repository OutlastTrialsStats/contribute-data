"""Reduces presence events into one snapshot of what the player is doing.

Owned by the watcher thread. Every snapshot is frozen, so the presence worker can read one without
locking and compare two for equality.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from totstats.presence.parser import (
    Event,
    GameExit,
    MapLoad,
    PartyRoster,
    PhaseChange,
    PresencePost,
    StageInfo,
)

PROGRAM_INVASION = "programINVASION"

# The phase that starts the trial clock, and the phases that end it.
PHASE_STARTED = "StageStarted"
PHASE_ENDED = ("StageEnding", "StageSuccess", "StageFailed", "PostGameExitTimeout", "ReturnToLobby")

# A map load describes the same transition as the presence the game posts a moment later. Within
# this window the post wins; outside it the map is all we have.
POST_AUTHORITY = timedelta(seconds=5)

DEFAULT_PARTY_MAX = 4


class Activity(StrEnum):
    UNKNOWN = "unknown"
    MAIN_MENU = "mainmenu"
    SLEEP_ROOM = "lobby"
    MATCHMAKING = "findingparty"
    PREPARING = "preparingtrial"
    TRIAL = "trial"
    CHAIN = "trialchain"
    RETURNING = "returningtolobby"
    OFFLINE = "offline"


class InvasionRole(StrEnum):
    REAGENT = "reagent"
    IMPOSTER = "imposter"


_ACTIVITY_BY_PRESENCE = {
    "mainmenu": Activity.MAIN_MENU,
    "lobby": Activity.SLEEP_ROOM,
    "findingparty": Activity.MATCHMAKING,
    "preparingtrial": Activity.PREPARING,
    "trial": Activity.TRIAL,
    "trialchain": Activity.CHAIN,
    "invadingtrial": Activity.TRIAL,
    "returningtolobby": Activity.RETURNING,
}

_ACTIVITY_BY_MAP = {
    "mainmenu": Activity.MAIN_MENU,
    "lobby": Activity.SLEEP_ROOM,
    "trial": Activity.TRIAL,
}

_IN_TRIAL = (Activity.TRIAL, Activity.CHAIN)


@dataclass(frozen=True)
class GameState:
    activity: Activity = Activity.UNKNOWN
    program_id: str | None = None
    trial_id: str | None = None
    difficulty: int | None = None
    chain_step: int | None = None
    phase: str | None = None
    party_size: int | None = None
    party_max: int = DEFAULT_PARTY_MAX
    party_key: str | None = None
    invasion_role: InvasionRole | None = None
    trial_started_at: float | None = None

    @property
    def in_trial(self) -> bool:
        return self.activity in _IN_TRIAL

    @property
    def in_invasion(self) -> bool:
        """Party counts include the enemy team here, so they are not worth showing."""
        return self.invasion_role is not None or self.program_id == PROGRAM_INVASION


class ClockSync:
    """Translates log timestamps to POSIX seconds.

    The log prefix is naive: it carries no timezone. Comparing live lines against the wall clock
    tells us how far off it is, so Discord's elapsed counter stays right even if a future build
    logs UTC. Replayed lines never inform the offset — they are minutes or hours old by definition.
    """

    # Below this the difference is just tailing latency, not a timezone.
    THRESHOLD = 60.0

    def __init__(self, samples: int = 5) -> None:
        self._samples = samples
        self._offsets: list[float] = []

    def observe(self, ts: datetime | None) -> None:
        if ts is None:
            return
        self._offsets.append(time.time() - ts.timestamp())
        if len(self._offsets) > self._samples:
            self._offsets.pop(0)

    @property
    def offset(self) -> float:
        if not self._offsets:
            return 0.0
        middle = sorted(self._offsets)[len(self._offsets) // 2]
        return middle if abs(middle) > self.THRESHOLD else 0.0

    def to_posix(self, ts: datetime) -> float:
        return ts.timestamp() + self.offset


class StateMachine:
    """Applies events in log order. apply() reports whether the snapshot changed."""

    def __init__(self, clock: ClockSync | None = None) -> None:
        self.clock = clock or ClockSync()
        self._state = GameState()
        self._last_post: datetime | None = None

    @property
    def snapshot(self) -> GameState:
        return self._state

    def reset(self) -> None:
        self._state = GameState()
        self._last_post = None

    def apply(self, event: Event, ts: datetime | None, live: bool) -> bool:
        if live:
            self.clock.observe(ts)

        before = self._state
        if isinstance(event, PresencePost):
            self._apply_post(event, ts)
        elif isinstance(event, StageInfo):
            self._apply_stage(event)
        elif isinstance(event, PhaseChange):
            self._apply_phase(event, ts)
        elif isinstance(event, MapLoad):
            self._apply_map(event, ts)
        elif isinstance(event, PartyRoster):
            self._apply_party(event)
        elif isinstance(event, GameExit):
            self._state = GameState(activity=Activity.OFFLINE)
            self._last_post = None
        return self._state != before

    def _apply_post(self, post: PresencePost, ts: datetime | None) -> None:
        self._last_post = ts
        state = self._state

        activity = _ACTIVITY_BY_PRESENCE.get(post.presence_state or "", state.activity)
        role = _role_for(post)
        changed_trial = post.trial_id != state.trial_id

        state = replace(
            state,
            activity=activity,
            program_id=post.program_id,
            trial_id=post.trial_id,
            difficulty=post.difficulty,
            chain_step=post.chain_step,
            invasion_role=role,
        )
        # Own player count, reliable outside a trial. Inside one EffectiveNumberOfPlayers is
        # closer to the truth, so the post only fills a gap there.
        if post.player_count is not None and not state.in_invasion:
            if not state.in_trial or state.party_size is None:
                state = replace(state, party_size=post.player_count)

        self._state = state
        if changed_trial or not state.in_trial:
            self._clear_clock()

    def _apply_stage(self, stage: StageInfo) -> None:
        """The trial descriptor, ~1.5 s ahead of the presence post — a preview, not a correction."""
        state = self._state
        if state.trial_id is not None and state.trial_id != stage.trial_id:
            return
        state = replace(
            state,
            program_id=stage.program_id or state.program_id,
            trial_id=stage.trial_id or state.trial_id,
            difficulty=stage.difficulty or state.difficulty,
        )
        if stage.players is not None and not state.in_invasion:
            state = replace(state, party_size=stage.players)
        self._state = state

    def _apply_phase(self, phase: PhaseChange, ts: datetime | None) -> None:
        self._state = replace(self._state, phase=phase.to_phase)
        if phase.to_phase == PHASE_STARTED and ts is not None:
            self._state = replace(self._state, trial_started_at=self.clock.to_posix(ts))
        elif phase.to_phase in PHASE_ENDED:
            self._clear_clock()

    def _apply_map(self, load: MapLoad, ts: datetime | None) -> None:
        if load.kind in ("mainmenu", "lobby"):
            self._clear_clock()
        if self._post_is_authoritative(ts):
            return
        activity = _ACTIVITY_BY_MAP.get(load.kind)
        if activity is not None:
            self._state = replace(self._state, activity=activity)

    def _apply_party(self, roster: PartyRoster) -> None:
        if self._state.in_invasion:
            return
        self._state = replace(
            self._state,
            party_size=roster.members,
            party_max=roster.max_size or self._state.party_max,
            # The party id is an account identifier; Discord only needs something stable.
            party_key=hashlib.sha1(roster.item_id.encode("utf-8")).hexdigest()[:16],
        )

    def _post_is_authoritative(self, ts: datetime | None) -> bool:
        if self._last_post is None or ts is None:
            return False
        return abs(ts - self._last_post) < POST_AUTHORITY

    def _clear_clock(self) -> None:
        if self._state.trial_started_at is not None:
            self._state = replace(self._state, trial_started_at=None)


def _role_for(post: PresencePost) -> InvasionRole | None:
    if post.presence_state == "invadingtrial":
        return InvasionRole.IMPOSTER
    if post.program_id == PROGRAM_INVASION:
        return InvasionRole.REAGENT
    return None
