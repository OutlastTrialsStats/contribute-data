# TOTStatsMonitor

A small companion app for [outlasttrialsstats.com](https://outlasttrialsstats.com). It sits in
your Windows system tray, watches The Outlast Trials' own log file while you play, and turns that
into two things: community statistics, and — soon — Discord Rich Presence.

It reads a log file the game already writes. It does not touch the game, its memory, or its
files, and it needs no launch options.

## Quick Start

**No Python installation required.**

[<img src="https://img.shields.io/badge/Download-TOTStatsMonitor.exe-blue?style=for-the-badge&logo=windows" alt="Download TOTStatsMonitor.exe">](https://github.com/OutlastTrialsStats/contribute-data/releases/latest/download/TOTStatsMonitor.exe)

1. Download and double-click to run.
2. That's it.

The app copies itself to `%LOCALAPPDATA%\TOTStatsMonitor\` on first run, so you can delete the
downloaded file afterwards. It also sets itself to start with Windows, so it is already running
the next time you play. Untick **Start with Windows** in the tray menu and the registry entry is
removed — that choice sticks, the app will not put it back on the next start.

## Features

### Contribute player data

While you are in a match, the app picks up the profile IDs of the players you meet and sends them
to outlasttrialsstats.com. That is how new players get discovered and added to the community
statistics database — the site can only track players it already knows about.

All contributors automatically receive an exclusive contributor badge on their profile at
outlasttrialsstats.com.

Only profile IDs are sent. No chat, no personal data, nothing about your own performance. You can
watch exactly what happens in the Console window, and switch the whole thing off from the tray
menu without uninstalling.

### Discord Rich Presence — planned

Showing what you are currently playing on your Discord profile: which trial, which difficulty,
how full the party is, and how long you have been in there.

This is not implemented yet. When it ships it will be part of this same app — one download, one
tray icon, one toggle, and **no Steam launch options and no files dropped into your game
directory**.

## System Tray

The app runs in the background and shows an icon in the Windows system tray (bottom-right, behind
the `^` arrow). Right-click it for the menu:

| Option | Description |
|---|---|
| **Status** | Whether it is monitoring, waiting for the game, or paused |
| **Contribute player data** | Turns contributing on or off immediately, without uninstalling |
| **Start with Windows** | Adds or removes the autostart entry |
| **Console** | A live log window: detected players, API responses, errors |
| **Uninstall** | Removes autostart, deletes the installed files, and shuts down |
| **Exit** | Stops the app without uninstalling |

Settings are stored in `%LOCALAPPDATA%\TOTStatsMonitor\settings.json`.

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, and
[doc/commit-convention.md](doc/commit-convention.md) for the commit message format — commit
messages drive the version bump and the changelog through `release-please`.

## License

[GPL-3.0](LICENSE)

## Disclaimer

We are not Red Barrels and not partnered with Red Barrels or The Outlast Trials.
