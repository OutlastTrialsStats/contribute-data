"""Turns a game state into the payload Discord shows.

Pure: same state and catalog in, same payload out, which is what lets the service skip sending a
status Discord already has. A raw game identifier never reaches this output — an unknown trial is
described in words instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from totstats.presence.catalog import Catalog, TrialInfo
from totstats.presence.state import Activity, GameState, InvasionRole

# Discord truncates past 128 characters and rejects a single character.
MAX_TEXT = 128
MIN_TEXT = 2

MIN_PARTY = 2

SEPARATOR = " • "
GAME_NAME = "The Outlast Trials"
PROFILE_BUTTON = "Player Stats"

_QUIET = (Activity.UNKNOWN, Activity.OFFLINE)


@dataclass(frozen=True)
class Payload:
    details: str
    state: str
    large_image: str
    large_text: str
    small_image: str | None = None
    small_text: str | None = None
    party_id: str | None = None
    party_size: tuple[int, int] | None = None
    start: int | None = None
    buttons: tuple[tuple[str, str], ...] = ()

    def as_kwargs(self) -> dict:
        payload: dict = {
            "details": self.details,
            "state": self.state,
            "large_image": self.large_image,
            "large_text": self.large_text,
        }
        if self.small_image:
            payload["small_image"] = self.small_image
            payload["small_text"] = self.small_text or self.large_text
        if self.party_id and self.party_size:
            payload["party_id"] = self.party_id
            payload["party_size"] = list(self.party_size)
        if self.start:
            payload["start"] = self.start
        if self.buttons:
            payload["buttons"] = [{"label": label, "url": url} for label, url in self.buttons]
        return payload

    def summary(self) -> str:
        return f"{self.details} | {self.state}"


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) < MIN_TEXT:
        text = text.ljust(MIN_TEXT)
    return text[:MAX_TEXT]


def render(state: GameState, catalog: Catalog, profile_id: str | None = None) -> Payload | None:
    """The status to show, or None when there should be no status at all."""
    if state.activity in _QUIET:
        return None

    trial = catalog.trial(state.trial_id)
    program = catalog.program_name(state.program_id)
    difficulty = catalog.difficulty_name(state.difficulty)

    details, description = _describe(state, trial, program, difficulty)
    banner = trial.banner if trial is not None else None
    small_image, small_text = _role_icon(state, catalog)

    party_id, party_size = None, None
    if state.party_size and state.party_size >= MIN_PARTY and not state.in_invasion:
        party_id = state.party_key or "party"
        party_size = (state.party_size, max(state.party_max, state.party_size))

    link = catalog.profile_link(profile_id)
    large_text = GAME_NAME
    if trial is not None:
        large_text = f"{trial.name} — {trial.location}" if trial.location else trial.name

    return Payload(
        details=_clip(details),
        state=_clip(description),
        large_image=catalog.image(banner),
        large_text=_clip(large_text),
        small_image=small_image,
        small_text=small_text,
        party_id=party_id,
        party_size=party_size,
        start=int(state.trial_started_at) if state.in_trial and state.trial_started_at else None,
        buttons=((PROFILE_BUTTON, link),) if link else (),
    )


def _describe(
    state: GameState,
    trial: TrialInfo | None,
    program: str | None,
    difficulty: str | None,
) -> tuple[str, str]:
    """The two lines Discord shows: what the player is doing, and the detail under it."""
    if state.activity is Activity.MAIN_MENU:
        return "Main Menu", "Idle"
    if state.activity is Activity.MATCHMAKING:
        return "Sleep Room", "Looking for a group"
    if state.activity is Activity.RETURNING:
        return "Sleep Room", "Returning from a Trial"
    if state.activity is Activity.SLEEP_ROOM:
        return "Sleep Room", "Getting ready"
    if state.activity is Activity.PREPARING and trial is None:
        # The trial is picked but not announced yet; the player is still standing in the lobby.
        return "Sleep Room", "Preparing a Trial"

    parts: list[str] = []
    if state.activity is Activity.CHAIN:
        headline = program or "Escalation"
        if trial is not None:
            parts.append(trial.name)
        if state.chain_step:
            parts.append(f"Step {state.chain_step}")
    else:
        headline = trial.name if trial is not None else (program or "In a Trial")
        if trial is not None and trial.location:
            parts.append(trial.location)

    if state.invasion_role is not None:
        role = "Imposter" if state.invasion_role is InvasionRole.IMPOSTER else "Reagent"
        parts = [f"Invasion{SEPARATOR}{role}"]
    if state.activity is Activity.PREPARING:
        parts.insert(0, "Preparing")
    if difficulty:
        parts.append(difficulty)

    return headline, SEPARATOR.join(parts) if parts else GAME_NAME


def _role_icon(state: GameState, catalog: Catalog) -> tuple[str | None, str | None]:
    if state.invasion_role is None:
        return None, None
    banner = catalog.invasion_banners.get(state.invasion_role.value)
    if not banner:
        return None, None
    label = "Imposter" if state.invasion_role is InvasionRole.IMPOSTER else "Reagent"
    return catalog.image(banner), f"Invasion — {label}"
