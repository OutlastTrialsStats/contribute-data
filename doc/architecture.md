# Architecture

The app exists to answer one question continuously — *what is the game doing right now?* — and to
let independent features act on the answer. Everything below follows from the fact that the
answer comes from a log file the game writes for its own reasons.

## Data flow

```
%LOCALAPPDATA%\OPP\Saved\Logs\OPP.log
            │
            │  polled every 250 ms while OPP is running
            ▼
      shared/log_tail.py ── LogTailer ──────────── one reader, many subscribers
            │                    │
            │  LogLine           │  LogLine
            ▼                    ▼
   contribute/service.py     (presence/service.py — not built yet)
            │                    │
            │  queue             │
            ▼                    ▼
   contribute/api.py         (Discord IPC)
     HTTP worker thread
```

The tailer reads the file once and fans lines out. Two features each opening their own reader
would double the I/O, and — worse — could disagree about what the game is doing, because they
would be at different offsets in the same file.

Subscribers register literal substrings (`INTERESTS`). The tailer merges all subscribers'
substrings into a single pre-filter, so a line nobody cares about is rejected by one `in` check
before it is ever parsed. A subscriber registering no substrings disables that optimisation for
everyone, so don't.

## Threads

| Thread | Owns | Rules |
|---|---|---|
| main | Tk (hidden root, console window), UI queue | The **only** thread allowed to touch Tk |
| tray | pystray's Win32 message loop | Menu callbacks post to the UI queue; they never touch Tk or write settings |
| watcher | game process detection, log tailing, all parsing | The **only** thread that touches parser state |
| contribute-http | the outbound HTTP calls | Fed by a queue |

The split between the watcher and the HTTP worker is the important one: an unreachable API used
to stall log reading, because the request was made inline while parsing. Sinks called by the
tailer run on the watcher thread and must not block — they enqueue and return.

Cross-thread communication is deliberately boring: `shared/ui_queue.py` for "run this on the main
thread", a `queue.Queue` for outbound work, a `threading.Event` for "stop".

## Adding a feature

A feature is a package under `src/totstats/` with a service class. It needs three things:

1. **`INTERESTS`** — a tuple of literal substrings that appear in the log lines it cares about.
2. **`on_line(line: LogLine)`** — called on the watcher thread for each matching line. Parse,
   update state, enqueue work. Never block, never call the network here.
3. **`on_rotate()`** — called when the log file is replaced or the game restarts. Throw away
   per-session state; whatever you learned belongs to a session that has ended.

`LogLine` carries `raw`, `body` (the line without its `[timestamp][frame]` prefix), `ts`, `frame`
and `replay`. `replay` is true while the tailer is working through content that already existed
when it opened the file — useful for deciding whether something is news or history. On startup
the whole file is replayed, so a feature that starts mid-session can still reconstruct state.

Wiring it up in `app.py` is two calls:

```python
self.presence = PresenceService(...)
self._tailer.subscribe(
    self.presence.on_line,
    needles=PresenceService.INTERESTS,
    on_rotate=self.presence.on_rotate,
    name="presence",
)
```

Then add a `features.presence` check around it (the setting already exists — see
[settings.md](settings.md)) and a tray toggle.

Data files that ship with the feature go in the package and are read through
`paths.package_data_path("presence", "data", "trials.json")`, which resolves both in a source
checkout and inside the PyInstaller bundle. Add them to `--add-data` in `build.py`.

## What lives in shared/

Anything a second feature would otherwise reimplement:

| Module | Responsibility |
|---|---|
| `log_tail.py` | Incremental multi-subscriber tailing, rotation handling, line prefix parsing |
| `game_process.py` | Edge-triggered detection of the `TOTClient` process |
| `profile_id.py` | The local player's own profile ID, resolved from five different log sources |
| `applog.py` | Levelled logging with a ring buffer for the console window, plus a file sink |
| `paths.py` | Every filesystem location, resolved identically in dev and in the bundle |
| `settings.py` | The settings file |
| `autostart.py` | The HKCU Run entry, including migration of older value names |
| `installer.py` | Self-installation into `%LOCALAPPDATA%` and delayed self-deletion |
| `ui_queue.py` | Marshalling callables onto the main thread |

`shared/` must not import from `contribute/`, `presence/` or `ui/`. If a shared module needs to
know something feature-specific, the dependency is pointing the wrong way.

## Log reading, and why it looks the way it does

Three details in `log_tail.py` carry most of the correctness weight, all of them learned from
things that went wrong:

- **Binary reads, split on newlines, decoded after.** Polling four times a second means routinely
  reading while the game is halfway through writing a line. A partial line reaching a parser
  produces rare, unreproducible nonsense — a truncated UUID, half a JSON body. The trailing
  fragment is held back until its newline arrives.
- **The file handle is not kept open between polls.** CPython opens files without
  `FILE_SHARE_DELETE` on Windows, so a persistent handle would stop the game from renaming
  `OPP.log` during its own rotation.
- **`OPP.log` is preferred over newest-by-mtime.** During rotation the just-renamed backup briefly
  has the newer timestamp, and picking by mtime latches onto a dead file for the rest of the
  session.

See [log-format.md](log-format.md) for what the lines contain.
