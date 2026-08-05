# Changelog

## [2.0.0](https://github.com/OutlastTrialsStats/totstats-monitor/compare/v1.2.1...v2.0.0) (2026-08-05)


### ⚠ BREAKING CHANGES

* Introduce trial catalog and Discord Rich Presence integration

### Features

* Add changelog sections and commit convention documentation ([ef4adf6](https://github.com/OutlastTrialsStats/totstats-monitor/commit/ef4adf64ec40d411a3bb387c557ad318349c6e1a))
* Add changelog sections and commit convention documentation ([7f3b55a](https://github.com/OutlastTrialsStats/totstats-monitor/commit/7f3b55a7872bd930ed865d9aa6d1c4cacba23648))
* Add release automation workflow using release-please and update build process ([187b6b0](https://github.com/OutlastTrialsStats/totstats-monitor/commit/187b6b0890aaaea8c159093149e2e4d1480c11d9))
* Add release automation workflow using release-please and update… ([6be4a94](https://github.com/OutlastTrialsStats/totstats-monitor/commit/6be4a94757efec5f0da597aa4421ed78d4bee3ae))
* Introduce trial catalog and Discord Rich Presence integration ([a9634de](https://github.com/OutlastTrialsStats/totstats-monitor/commit/a9634de153979d9faf78cbff30dcd671d9925445))
* Track session start time for Discord presence integration ([564c542](https://github.com/OutlastTrialsStats/totstats-monitor/commit/564c542fe853c5ed948df536298070e05360d891))


### Code Refactoring

* Remove extensive comments and improve log enrichments for Discord presence ([5ba0949](https://github.com/OutlastTrialsStats/totstats-monitor/commit/5ba0949b68e397f8c7606c616ef81b0ed952097c))


### Dependencies

* bump googleapis/release-please-action from 4 to 5 ([6d2be37](https://github.com/OutlastTrialsStats/totstats-monitor/commit/6d2be37312bb7aa92bb8a82510d13ee7091eb1e5))

## [1.2.1](https://github.com/OutlastTrialsStats/contribute-data/compare/v1.2.0...v1.2.1) (2026-04-02)

### Continuous Integration

* Reworked build workflow: permissions, Python version, pip cache; release action bumped to v2
* Added Dependabot configuration for GitHub Actions and pip

### Dependencies

* Bump actions/checkout from 4 to 6
* Bump actions/setup-python from 5 to 6
* Bump actions/upload-artifact from 4 to 7

> Note: `__version__` was not bumped for this release — the shipped executable reports 1.2.0
> internally. Fixed as part of the release automation setup.

## [1.2.0](https://github.com/OutlastTrialsStats/contribute-data/compare/v1.1.0...v1.2.0) (2026-04-02)

### Features

* System tray support with Status, Console and Uninstall menu entries
* Self-installation to `%LOCALAPPDATA%\TOTStatsMonitor\` including autostart management
* `build.py` as local/CI build script generating the Windows VERSIONINFO resource

### Bug Fixes

* Reworked logging and autostart handling, added UI queue for main thread tasks
* Force UTF-8 encoding when reading the version from the source file

## [1.1.0](https://github.com/OutlastTrialsStats/contribute-data/releases/tag/v1.1.0) (2025-12-24)

### Features

* First published version: log monitor reporting player IDs to the contribute API
* PyInstaller build pipeline producing `TOTStatsMonitor.exe`

### Bug Fixes

* Handle HTTP 208 responses from the contribute API correctly
