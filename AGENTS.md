# Project Conventions

ShamsiTray is a Python PySide6/PyQt6 system-tray calendar app for Windows.

## Versioning (Semantic Versioning + git tags)

- The single source of truth is `APP_VERSION` in `src/config.py`.
- A release = bump `APP_VERSION` -> commit -> create an annotated tag:
  `git tag -a v<version> -m "<short description>"`
- Tag rules (SemVer):
  - PATCH (`1.3.1`) — bug fixes only
  - MINOR (`1.4.0`) — new feature, backward compatible
  - MAJOR (`2.0.0`) — breaking change
- A tag should always match `APP_VERSION` exactly (e.g. both `1.4.0`).

## History

- `main` holds the linear release history; every released version is tagged.
- Historically a folder was copied per version (`v0.x`/`v1.x`); those snapshots
  were folded into the linear commit history.
- Installers are tracked under `Output/` inside the commit of the version they
  belong to (`v1.0.0`, `v1.1.0`, `v1.2.0`, `v1.3.1`).
- `Logo/` is git-ignored design work; release configs under `build/` are tracked.
- `experiment/xnightstar` preserves the xNightStar calendar experiment that was
  not adopted; it forks `main` at `v0.1.3`.

## Workflow

- Commit per logical change, not once per version.
- Use branches for experiments/features (`git switch -c feature/<name>`),
  never copy folders.
- Run the app with `python run.py`.