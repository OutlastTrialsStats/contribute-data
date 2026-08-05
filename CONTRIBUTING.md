# Contributing

Thanks for helping out. This is a small Windows-only app; the setup is correspondingly small.

## Development setup

Python 3.12 is what CI builds with, and `pyproject.toml` targets it. Use it locally too — an
older interpreter will happily run most of the code and then disagree with CI over syntax.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the project itself in editable mode, which is what puts the
`src/` layout on the import path. Without it `python -m totstats` finds nothing.

```powershell
.venv\Scripts\python -m totstats --version
```

## Running it without the game

Starting the app for real installs it into `%LOCALAPPDATA%`, asks about autostart and sends data
to the live API — none of which you want while developing. Use `--dry-run` instead:

```powershell
# Copy a session's logs somewhere safe first; the game overwrites OPP.log.
Copy-Item "$env:LOCALAPPDATA\OPP\Saved\Logs" C:\temp\logs -Recurse

.venv\Scripts\python -m totstats --dry-run --verbose --logs-dir C:\temp\logs
```

A dry run reads the given directory whether or not the game is running, sends nothing (every
request is logged as `Would contribute`), writes its log to `totstats-dryrun.log` in the working
directory instead of the installation, keeps its settings in memory, and does not touch the
registry. It replays the whole file on startup, so a recorded session runs end to end.

| Flag | Effect |
|---|---|
| `--dry-run` | Read logs without the game, send nothing, touch nothing |
| `--logs-dir PATH` | Read from PATH instead of `%LOCALAPPDATA%\OPP\Saved\Logs` |
| `--verbose` | Log at debug level, including replayed lines |
| `--no-install` | Do not copy the executable into `%LOCALAPPDATA%` and relaunch |
| `--silent` | No console output; this is what the autostart entry uses |

## Before opening a pull request

```powershell
.venv\Scripts\ruff check .
```

CI runs the same command and the build job depends on it. There is no test suite yet.

To produce the executable:

```powershell
.venv\Scripts\python build.py
```

`build.py` reads the version from `src/totstats/__init__.py` and refuses to build if it disagrees
with `.release-please-manifest.json`. Both are updated by `release-please`; do not bump either by
hand.

## Code layout

```
src/totstats/
├─ __main__.py    argparse CLI
├─ app.py         wiring and lifecycle — the only place that knows every component
├─ shared/        infrastructure both features need
├─ contribute/    the contribute feature
└─ ui/            tray icon, console window, first-run prompt
```

The rule that keeps this workable: **`shared/` knows nothing about features, and features know
nothing about each other.** Anything Discord-specific belongs in a `presence/` package, not in
`shared/` and never in `contribute/`.

`shared/log_tail.py` is the piece to understand first. The game's log is read once, by one
tailer, and dispatched to subscribers — reading it twice would double the I/O and let two
features disagree about what the game is doing. A feature subscribes with a list of literal
substrings it cares about, and only lines containing one of them reach it.

See [doc/architecture.md](doc/architecture.md) for the thread model and for how a second feature
is added, and [doc/log-format.md](doc/log-format.md) for what the log lines actually mean.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), described in
[doc/commit-convention.md](doc/commit-convention.md). They drive the version bump and the
changelog, so the type you pick has consequences.
