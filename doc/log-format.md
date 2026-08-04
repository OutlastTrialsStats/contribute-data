# The Outlast Trials — log format

Everything TOTStatsMonitor knows about the game comes from the Unreal Engine log files the game
writes to `%LOCALAPPDATA%\OPP\Saved\Logs\` (`OPP` is the game's internal project name). Nothing is
read from game memory and no game files are modified.

This document records the line formats the parsers depend on. It was compiled by analysing 10 real
session logs (0.1–5.7 MB). Counts below are occurrences across those logs. All UUIDs in the examples
are placeholders.

> If a future game patch changes any of this, the parser will degrade rather than crash — but this
> file is where you look first.

---

## File handling

| Property | Value |
|---|---|
| Directory | `%LOCALAPPDATA%\OPP\Saved\Logs` |
| Live file | `OPP.log` — **always**; it is never one of the backups |
| Rotation | On game start the previous `OPP.log` is renamed `OPP-backup-YYYY.MM.DD-HH.MM.SS.log` and a fresh `OPP.log` is created |
| Encoding | UTF-8, **with BOM** on the first line |
| First line | `Log file open, MM/DD/YY HH:MM:SS` (no timestamp prefix) |
| Last line | `Log file closed, MM/DD/YY HH:MM:SS` (no timestamp prefix) |
| Write rate | ~700 B/s during play |

Picking "the newest `*.log` by mtime" is **wrong**: during rotation the just-renamed backup briefly
has the newer mtime, and a tailer can latch onto a dead file for the rest of the session. Prefer
`OPP.log` and fall back to newest-by-mtime only when it does not exist.

### Line prefix

```
[2026.08.02-15.35.43:756][138]RB:  GamePhase changed to WaitingForPlayers from None.
 └──────── local time ───────┘└┬┘└──────────────────── body ─────────────────────┘
                            frame counter
```

`[YYYY.MM.DD-HH.MM.SS:mmm][NNN]` — **naive local time**, present on every line after engine init.
The frame counter is right-aligned in a 3-char field, so it can contain leading spaces (`[  0]`).
Header and footer lines have no prefix.

---

## Own player state

### `presenceState` — the authoritative source

The game POSTs its own presence to the backend and logs the request body verbatim:

```
[2026.08.02-15.33.41:072][229]OnlineCoreHttpLogs: Verbose: Operation FCoreUpdatePresenceOperation(110) request body: {"profileId":"00000000-0000-0000-0000-000000000000","applicationId":"...","properties":{"buildId":"250521","region":"-","presenceState":"mainmenu","programId":null,"trialId":null,"programDifficulty":-1,"trialChain":-1,"joinable":false,"publicRequiresInvite":false,"friendRequiresInvite":false,"playerCount":1,"crossplay":true,"invasionId":"-","invasionState":"-"}}
```

Present in 9 of 10 logs (missing only from a 127 KB session that never reached login).

**Anchor on `FCoreUpdatePresenceOperation`, not on `request body:`** — other operations
(`FCreateClientSessionOperation` and friends) log bodies too, some containing auth tokens.

`properties`:

| Field | Notes |
|---|---|
| `presenceState` | see table below |
| `programId` | `null` outside a trial, else e.g. `programCoreCH` |
| `trialId` | `null` outside a trial, else e.g. `CHJ_MT03` |
| `programDifficulty` | `-1` outside a trial, else `1..4` — see below |
| `trialChain` | `-1` outside a chain, else the chain step (observed 2→12 ascending) |
| `playerCount` | party size |
| `invasionId` / `invasionState` | `"-"` when not applicable |
| `region`, `joinable`, `crossplay` | informational |

Observed `presenceState` values (all logs):

| Value | Count | Meaning |
|---|---|---|
| `returningtolobby` | 190 | trial over, heading back |
| `trial` | 136 | in a trial |
| `preparingtrial` | 136 | trial selected, loading |
| `lobby` | 123 | Sleep Room |
| `trialchain` | 106 | in an Escalation chain |
| `mainmenu` | 25 | main menu |
| `invadingtrial` | 17 | playing as the invading Prime Asset |
| `findingparty` | 10 | matchmaking for a party |

### `programDifficulty` is 1-based

Verified by cross-referencing every presence body against the nearest preceding `GameStageInfo`
for the same `trialId`:

| Numeric | Text | Display name | Evidence |
|---|---|---|---|
| `-1` | — | — | outside a trial |
| `1` | `Easy` | Introductory | `TFS_MT01`, `PSB_MT02`, `SMC_MT01`, `MHS_MT04` |
| `2` | `Normal` | Standard | `CHJ_MT03`, `CH_Trial`, `FPB_MT01`, `FPI_MT01`, `PSO_MT01`, `SMC_MT02` |
| `3` | `Hard` | Intensive | `CHA_MT01`, `MHS_MT03` |
| `4` | `Insane` | Psychosurgery | inferred — appears only in other players' presence, never in an own body in the sample set |

This is **not** the website's `difficultyToBadgeCode` mapping (which starts at Easy → 0). Do not
reuse that table.

Note the type difference: own POST bodies encode these as **integers** (`3`), received RTA presence
messages as **floats** (`3.0`). Coerce with `int()`.

### Own profile ID — five sources

In resolution order (first hit wins):

1. **`?EncryptionToken=` in a `LoadMap` line** — earliest and most reliable, needs no verbose HTTP
   logging, present on every server map load.
2. `OnlineCoreLogs: Client authentication succeeded. Profile ID: <uuid>. Session ID: <uuid>.`
3. The presence POST URL: `.../presence/public/profiles/<uuid>/presence`
4. The third segment of `parties|<applicationId>|<ownProfileId>` or
   `matchmaking-tickets|<applicationId>|<ownProfileId>`
5. `Player Init Replicated … IsLocallyControlled = Yes`

---

## Corroborating signals

These arrive faster than the presence POST or cover the case where verbose HTTP logging is off.

### `GameStageInfo` — trial descriptor, ~1.5 s ahead of the presence POST

```
[2026.08.02-15.35.43:756][138]RB:  GameStageInfo changed. Program ID: programCoreCH, Trial ID: CHJ_MT03, Program difficulty: Normal, Stage: CourthouseJudicial, Mission: CHJ_MT03, Seed: 617617, EffectiveNumberOfPlayers: 1
```

`Program difficulty` is already the canonical text (`Easy|Normal|Hard|Insane`).

### `GamePhase` — sub-state inside a trial

```
[2026.08.02-15.35.51:644][500]RB:  GamePhase changed to WaitingForPlayersSitting from WaitingForPlayers.
```

Observed sequence: `WaitingForPlayers → WaitingForPlayersSitting → LoadingStage → Populating →
WaitingForClientsPopulate → StageReady → StageStarted → StageEnding → StageSuccess →
PostGameExitTimeout → ReturnToLobby`. `StageFailed` exists but did not occur in the sample set.

**`StageStarted` is the real start of the trial** — that is the timestamp Discord's elapsed counter
should use, not the app's start time.

### `LoadMap` — map changes, own ID, and the trial that just ended

```
[2026.08.02-15.33.29:616][  0]LogLoad: LoadMap: /Game/Maps/Global/MainMenu?Name=Player
[2026.08.02-15.34.11:938][898]LogLoad: LoadMap: 1.2.3.4:7784/Game/Maps/Lobby/Lobby_Persistent?PlayerSessionId=psess-...?EncryptionToken=<own uuid>?Source=MainMenu?game=/Game/Systems/Global/RBLobbyGameMode_BP.RBLobbyGameMode_BP_C
[2026.08.02-15.35.42:684][115]LogLoad: LoadMap: 1.2.3.4:7778/Game/Maps/Global/OPP_Persistent?PlayerSessionId=psess-...?EncryptionToken=<own uuid>?Source=Lobby?game=...
[2026.08.02-15.44.16:693][699]LogLoad: LoadMap: 1.2.3.4:7780/Game/Maps/Lobby/Lobby_Persistent?...?Source=Experiment?ProgramId=programCoreCH?Stage=CourthouseJudicial?Trial=CHJ_MT03?game=...
```

| Map | Count | Meaning |
|---|---|---|
| `/Game/Maps/Global/MainMenu` | 17 | main menu |
| `/Game/Maps/Lobby/Lobby_Persistent` | 15 | Sleep Room |
| `/Game/Maps/Global/OPP_Persistent` | 13 | a trial |

| `?Source=` | Count | Meaning |
|---|---|---|
| `MainMenu` | 22 | entering from the main menu |
| `TrialChaining` | 20 | next link of an Escalation chain |
| `Lobby` | 8 | starting a trial from the Sleep Room |
| `ExperimentFail` | 4 | returning after a failed trial |
| `Experiment` | 2 | returning after a completed trial |

Returning loads also carry `?ProgramId=` / `?Stage=` / `?Trial=` of the trial that just ended.

### Shutdown

```
[2026.08.02-16.23.43:616][806]LogExit: Exiting.
[2026.08.02-16.23.43:627][806]Log file closed, 08/02/26 16:23:43
```

---

## RTA WebSocket messages

```
RTA: Received message: {"messageId": "...", "type": "data-item-updated", "dataItemId": "...", "data": {...}, "timestamp": 1785492538930}
```

The JSON is pretty-ish printed (spaces after colons) — parse it, do not pattern-match it.

`dataItemId` prefixes across all logs: `presence` (629), `matchmaking-tickets` (54),
`subscriptions` (39), `parties` (38), `relationships` (1), plus 9 messages with no `dataItemId`.

### `presence|<profileId>` — **other players only**

Verified across all 10 logs: the own profile ID **never** appears in a received `presence|`
`dataItemId`. These messages describe friends and party members. They carry the same `properties`
shape as the own POST body (with float numerics), but they must not be used to derive own state.

### `parties|<applicationId>|<ownProfileId>` — party roster

```json
{"dataItemId": "parties|<appId>|<ownId>",
 "data": {"type": "party_invite_sent", "partyId": "...", "sourceProfileId": "...",
          "partyData": {"gameSessionState": "inLobby", "gameSessionRegion": "eu-central-1",
                        "team1": "<uuid>|<uuid>|<uuid>", "team2": "", "version": 25},
          "maxSize": 4, "allowList": ["<uuid>", "..."]}}
```

- **`partyData.team1`** is the roster: pipe-joined profile UUIDs. An empty string means "no party".
- `maxSize` is always `4` in the sample set.
- `team2` was empty in every sample.
- `allowList` is the *invite* list, not the roster — do not count it.
- **`data.members` does not exist.** It occurs exactly once across all 10 logs. Any implementation
  reading the party size from `members` is effectively dead code.

### `matchmaking-tickets|<applicationId>|<ownProfileId>`

```json
{"data": {"type": "searching", "context": "personal", "ticketId": "...",
          "potentialMatch": ["<uuid>"], "matchProfileIds": ["<uuid>"], "backfill": false}}
```

`type` ∈ `searching | succeeded | data-item-updated`. `context` ∈ `global | personal | trial |
party | endgame` — **`findparty` never occurs**. On `succeeded`, `gameSessionInfo.team` was
`"players"` in every sample (not `team1`/`team2`).

`matchProfileIds` holds matchmaking candidates (6–8 entries in a full match), **not** the party
size. Using it as a player count produces nonsense like "(8/4)".

---

## Contribute: players in your session

```
[2026.08.02-15.34.12:571][905]RB:  [Name] Player Init Replicated. Player Id = Name [TAG] [00000000-0000-0000-0000-000000000000],  Player Slot = 8, IsLocallyControlled = No
```

- The line repeats the display name twice: once in the leading `[...]`, once after `Player Id =`.
- Note the **two spaces** before `Player Slot`, and that some lines have a trailing space.
- `IsLocallyControlled = Yes` marks the local player — never contribute your own ID from here, but
  it is a valid source for *learning* your own ID.
- Display names contain spaces, non-ASCII characters (Cyrillic, `†`), dots and angle brackets, and
  may themselves contain `[` / `]`. **Anchor the regex on the UUID**, not on the brackets around the
  name.

---

## Other verified details

- Program IDs seen: `programCoreCH`, `programCoreDT`, `programCoreOR`, `programCorePS`,
  `programCoreSR`, `programCoreTS` (pattern `programCore<FAMILY>`), plus `programCHAIN`,
  `programINVASION`, `programCREATOR`, `programBloodDonations3`.
- **`programCREATOR` reports `trialId: "trial02"`**, which does not exist in the website's trial
  catalog. Unknown trial IDs must degrade gracefully rather than being shown raw.
- `invasionState` values: `-`, `Available_PendingPlayerRequest`, `InvasionStarted`, and
  `Disabled_*` variants (`DisabledByObjective`, `GlobalInvasionNotUnlocked`,
  `InvasionGameModeDisabled`, `NoPlayers`, `PlayerChoice`, `StageNotStarted`).
- Escalation is `presenceState: trialchain` + `programId: programCHAIN`; the chain step is
  `trialChain`.

## Reference session timeline

From a real Core-program session, for validating a state machine end to end:

```
15.33.29  LoadMap /Game/Maps/Global/MainMenu?Name=Player
15.33.41  presence mainmenu
15.34.11  LoadMap …/Lobby_Persistent?…?Source=MainMenu
15.34.14  presence lobby
15.35.28  presence preparingtrial
15.35.42  LoadMap …/OPP_Persistent?…?Source=Lobby
15.35.43  GamePhase WaitingForPlayers        ┐ same millisecond
15.35.43  GameStageInfo programCoreCH / CHJ_MT03 / Normal / 1 player
15.35.45  presence trial                      ← 1.5 s after GameStageInfo
15.35.51  GamePhase WaitingForPlayersSitting
15.35.54  GamePhase LoadingStage
15.36.11  GamePhase Populating
15.36.47  GamePhase WaitingForClientsPopulate
15.36.58  GamePhase StageReady
15.37.06  GamePhase StageStarted              ← the trial clock starts here
15.43.34  GamePhase StageEnding
15.43.42  GamePhase StageSuccess
15.43.42  presence returningtolobby
15.44.05  GamePhase ReturnToLobby
15.44.16  LoadMap …/Lobby_Persistent?…?Source=Experiment?Trial=CHJ_MT03
15.44.19  presence lobby
…
16.23.43  LogExit: Exiting.
```

---

## Privacy note

These logs contain real profile UUIDs, display names, server IPs and session tokens of everyone you
played with. Never commit raw log excerpts to this repository, and scrub any excerpt used in a bug
report.
