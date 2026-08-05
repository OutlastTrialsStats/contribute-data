# Commit Convention

This repository uses [Conventional Commits](https://www.conventionalcommits.org/). Commit messages
on `main` drive the release: `release-please` reads them to determine the next version and to
generate `CHANGELOG.md`.

## Format

```
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

```
feat: add Discord rich presence support
fix(tray): console window no longer blocks shutdown
feat(api)!: switch contribute endpoint to v2
```

## Types

| Type       | Version bump | Changelog                |
|------------|--------------|--------------------------|
| `feat`     | minor        | Features                 |
| `fix`      | patch        | Bug Fixes                |
| `perf`     | patch        | Performance Improvements |
| `refactor` | patch        | Code Refactoring         |
| `chore`    | patch        | Miscellaneous Chores     |
| `deps`     | patch        | Dependencies             |
| `docs`     | none         | hidden                   |
| `style`    | none         | hidden                   |
| `ci`       | none         | hidden                   |

"hidden" means the commit is valid but neither triggers a release nor appears in the changelog.

A `!` before the colon or a `BREAKING CHANGE:` footer bumps the **major** version, regardless of
type.

Dependabot uses these types automatically: `deps` for pip packages (they are bundled into the
executable, so they warrant a release) and `ci` for GitHub Actions (they only affect the workflows).

## Trailers

Do not add `Co-Authored-By` trailers for AI assistants, or "generated with" lines, to commit
messages or pull request descriptions. The commit body ends with the body. This applies to
anyone using an AI coding tool on this repository — configure it accordingly.