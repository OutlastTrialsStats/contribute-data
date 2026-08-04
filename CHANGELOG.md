# Changelog

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
