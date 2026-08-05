# Settings

TOTStatsMonitor keeps its settings in a single JSON file:

```
%LOCALAPPDATA%\TOTStatsMonitor\settings.json
```

The file is written when a setting changes, not on every start. If it does not exist, the
defaults below apply — a fresh installation therefore has no settings file until the first-run
question is answered.

## Schema

```jsonc
{
  "version": 1,
  "autostart": null,
  "features": {
    "contribute": true,
    "presence": false
  }
}
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `version` | number | `1` | Schema version. Written by the app, ignored when reading — a field added with a default needs no bump. |
| `autostart` | `true` \| `false` \| `null` | `null` | Whether to start with Windows. `null` means the user has not been asked yet. |
| `features.contribute` | boolean | `true` | Report newly seen players to outlasttrialsstats.com. |
| `features.presence` | boolean | `false` | Reserved for Discord Rich Presence. **Not implemented yet** — setting it to `true` currently does nothing. |

## Autostart

`autostart` is tri-state on purpose. Earlier versions wrote the registry entry on every start
without ever asking; the third state is what lets the app tell "never asked" apart from "asked,
and the answer was no".

Resolution happens once per start, before the tray icon appears:

1. `autostart` is `true` or `false` → the registry entry is brought in line with it. A user who
   said no stays at no; the entry is not silently recreated.
2. `autostart` is `null` and an entry from an older version exists → adopted as `true` and
   rewritten under the current name. Updating never loses your autostart and never asks again
   for something you already agreed to.
3. `autostart` is `null` and no entry exists → you are asked once, and the answer is saved.
4. `autostart` is `null` and the app was started with `--silent` → nothing is asked and nothing
   is written; the question waits for the next interactive start. A dialog appearing during
   logon, from a process with no window, would be indistinguishable from malware.

The registry value lives under `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run` and is named
`TOTStatsMonitor`. Releases up to and including 1.2.1 used `OutlastTrialsMonitor`; that name is
still recognised, migrated and cleaned up, but never written.

## Feature toggles

`Contribute player data` in the tray menu flips `features.contribute` and takes effect
immediately — log lines are still read, but nothing is parsed or sent while it is off. The tray
status reads `Paused` in that state.

`features.presence` has no tray entry yet, because there is nothing behind it to switch on. It
is written from the start so that shipping the feature later is a change of value rather than a
change of format.

## When the file is unreadable

Settings are read during startup, before there is any UI, and the shipped build runs without a
console — so a parse error must never surface as a crash. Instead:

- **Missing** → defaults, no message. This is the normal first start.
- **Not valid JSON** → defaults, a warning in the log, and the damaged file is renamed to
  `settings.json.bad` so it is not silently overwritten by the next save.
- **A field with the wrong type** → that field falls back to its default; the rest of the file is
  still used. `"autostart": "yes"` is not `true`, it is "unreadable", and so resets to `null`.
- **Unknown fields** → ignored and dropped on the next save.

Writes go to `settings.json.tmp` first and are then renamed into place, so an interrupted write
cannot leave a half-written file behind.
