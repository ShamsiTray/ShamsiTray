# AGENTS.md - ShamsiTray Development Guide

ShamsiTray is a Python PyQt6 system-tray calendar app for Windows that displays the current Shamsi (Jalali) date in the system tray.

---

## 1. Project Overview

- **Purpose**: Lightweight Persian calendar in system tray with popup calendar, date converter, holiday tracking, user events, and automatic app/holiday-data updates
- **Tech Stack**: Python 3.12+, PyQt6, jdatetime, pywin32
- **Architecture**:
  ```
  src/
    config.py            # Single source of truth (version, paths, themes, constants, settings keys, API URLs)
    main.py              # Entry point: QApplication, asset verification, fonts, settings migration, tray init
     core/
      app_controller.py  # SystemTrayIcon: calendar logic, event handling, update-wiring, timers
      event_service.py   # EventService: single owner of the event store - mutations, transactional saves, import reconciliation
      update_checker.py  # UpdateChecker: GitHub release + holiday-store checks, download, sha256 verify
    ui/
      windows/           # PersianCalendarWidget, DateConverterWindow, EventManagerWindow,
                         # HolidayViewerWindow, TutorialWindow, BaseFramelessWindow (+ window-chrome helpers)
      widgets/           # CalendarDayCell, Tooltip, EventInput, GoToDate, Checkbox (custom),
                         # ConfirmDialog (themed), ConfirmOverlay (in-calendar), Menu widgets
    utils/
      date_utils.py      # Jalali/Gregorian helpers, formatting, digit conversion, leap-year, validation
      asset_loader.py    # Font loading, asset verification
      logger.py          # Rotating file + console logging under %LOCALAPPDATA%\ShamsiTray\logs
      native_events.py   # Windows WM_TIMECHANGE / WM_SETTINGCHANGE native event filtering (clock changes, live system theme)
      startup_registry.py  # Autostart Run-key access (read/write/delete) behind a fakeable seam
      ui_helpers.py      # Tray pixmap, shared combo/button/line-edit/scrollbar stylesheets, fit_combo_width
      json_settings.py   # JsonSettings — QSettings-compatible API backed by settings.json (atomic writes)
      settings_migration.py  # One-time migration from legacy HKCU\Software\ShamsiTray registry to JSON
      event_io.py        # Versioned event store (v2), recurrence-key model, import/export helpers
      holiday_io.py      # Holiday data loading, versioned AppData store, atomic update swap
  assets/                # Icons, fonts, holidays.json, screenshots, welcome.gif
  build/                 # PyInstaller config, Inno Setup script, version details
  output/                # Local-only installer output (gitignored; released installers attached to GitHub)
  tests/                 # pytest + pytest-qt suite (offscreen platform via tests/conftest.py)
  ruff.toml              # Ruff lint config (run by CI and locally)
  .github/workflows/     # CI: version check + ruff + pytest on every push and PR
  ```

**User data lives in `%LOCALAPPDATA%\ShamsiTray`** (NOT the registry):
- `settings.json` — app settings (theme, autostart, update prefs, tutorial flag)
- `user_events.json` — user calendar events
- `holidays.json` — versioned holiday store; seeded from bundle on first run, swapped atomically on update
- `logs/shamsitray.log` — rotating file log

The legacy `HKCU\Software\ShamsiTray` registry key is only read once for migration, and only deleted by the uninstaller.

---

## 2. Quick Start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python run.py
pytest
```

`pytest` is configured via `pytest.ini` (`testpaths = tests`, `pythonpath = src`).

---

## 3. Key Files

| File | Purpose |
|------|---------|
| `src/config.py` | **Single source of truth**: `APP_VERSION`, paths, user-data paths, themes, settings keys, API URLs, constants |
| `run.py` | Bootstraps `sys.path` (adds `src/`), launches `main.main()` |
| `src/main.py` | App initialization: asset verification, fonts, registry→JSON migration, tray init, tutorial on first run |
| `build/PyinstallerConfig.json` | PyInstaller build config (icon, assets, version file, `pathex` = `src`, one-folder) |
| `build/SetupScript.iss` | Inno Setup installer script (holiday seeding, uninstall cleanup) |
| `build/details.txt` | Version resource for Windows exe properties |
| `build/check_versions.py` | Release gate: asserts config.py / SetupScript.iss / details.txt versions agree |
| `README.md` / `README.fa.md` | User-facing docs (English / Farsi) |
| `pytest.ini` | Test config: `testpaths = tests`, `pythonpath = src` |
| `requirements.txt` | Pinned runtime deps (PyQt6, jdatetime, pywin32) |
| `requirements-dev.txt` | Dev/test deps (pytest, pytest-qt, ruff) |

---

## 4. Versioning & Release Process

**Source of truth**: `APP_VERSION` in `src/config.py`. **Must stay in sync**: `MyAppVersion` in `build/SetupScript.iss` **and** `filevers`/`prodvers`/`FileVersion`/`ProductVersion` in `build/details.txt`.

**SemVer rules**:
- PATCH (`1.3.1`) — bug fixes only
- MINOR (`1.4.0`) — new feature, backward compatible
- MAJOR (`2.0.0`) — breaking change

**Manual release steps**:
0. Run `python build/check_versions.py` - it exits non-zero until the three version strings agree
1. Bump `APP_VERSION` in `src/config.py`
2. Update `MyAppVersion` in `build/SetupScript.iss` (must match)
3. Update version resource in `build/details.txt`
4. Commit, then build exe via PyInstaller (using `build/PyinstallerConfig.json`)
5. Build installer via Inno Setup (using `build/SetupScript.iss`)
6. Output: `output/ShamsiTraySetup-X.Y.Z.exe`
7. Create annotated tag: `git tag -a vX.Y.Z -m "Release X.Y.Z"`
8. Push: `git push && git push --tags`
9. Attach installer + sha256 digest to the GitHub release

**Installer notes**:
- **Autostart is NOT written by the installer** — the installer deliberately does NOT touch the `HKCU\...\CurrentVersion\Run` key; the app manages autostart itself.
- On install it seeds `%LOCALAPPDATA%\ShamsiTray\holidays.json` from the bundle with `onlyifdoesntexist` (reinstall never clobbers an updated holiday file).
- On uninstall (when "Remove user settings" is checked) it deletes `%LOCALAPPDATA%\ShamsiTray` and the legacy `HKCU\Software\ShamsiTray` key.

---

## 5. Code Conventions

- **Python**: 3.12+, PEP 8, type hints where practical
- **Imports**: stdlib → third-party → local (`from config import APP_CONFIG`)
- **Logging**: Use `utils.logger.setup_logging(__name__)` in each module
- **Error handling**: Try/except with user-facing `QMessageBox.critical()` for fatal errors
- **Comments**: explain the constraint, not the change. A comment earns its place by saying why a non-obvious line has to be the way it is — Qt/Windows behaviour, an invariant, a compatibility default, a tradeoff — and it is written in the present tense. Anything that only narrates what a commit changed belongs in the commit message and the release notes, not in the source. Tests are the exception: their docstrings may name the behaviour they pin down.
- **Settings**: `JsonSettings` (JSON-backed, QSettings-compatible API) → `%LOCALAPPDATA%\ShamsiTray\settings.json`. Atomic writes (temp file + `os.replace`), tolerant of corrupt files.
- **Persistence**: Use `utils/event_io.py` and `utils/holiday_io.py`; never write user data to the registry (legacy key is read-only migration source).
- **Themes**: Palettes in `Config.DARK_PALETTE` / `LIGHT_PALETTE`, applied via `Config.set_theme()` — which takes the *resolved* theme, not the preference: `Appearance/ThemeChoice` (`system` / `light` / `dark`, defaulting to `system`) is resolved first

---

## 6. Key Components

### `src/config.py` (Config class)
- `APP_VERSION`, `APP_NAME`, `COMPANY_NAME`
- Paths: `PROJECT_ROOT`, `ASSETS_DIR`, `ICON_PATH`, `FONT_DIR`, `TUTORIAL_GIF_PATH`, `HOLIDAYS_FILE_PATH`
- User-data paths under `%LOCALAPPDATA%\ShamsiTray`: `USER_DATA_DIR`, `USER_LOG_DIR`, `LOG_FILE_PATH`, `SETTINGS_FILE_PATH`, `USER_EVENTS_FILE_PATH`, `HOLIDAYS_STORE_PATH`
- Settings keys: `AUTO_START_SETTING_KEY` (`General/OpenAtLogin`), `CURRENT_THEME_CHOICE_SETTING_KEY` (`Appearance/ThemeChoice`), `TUTORIAL_SHOWN_SETTING_KEY` (`Tutorial/HasShown`), `ALWAYS_ON_TOP_SETTING_KEY` (`Calendar/AlwaysOnTop`; read with a `True` default, since the popup was pinned before the toggle existed), `UPDATE_CHECK_ENABLED_SETTING_KEY`, `LAST_UPDATE_CHECK_SETTING_KEY`, `IGNORED_UPDATE_VERSION_SETTING_KEY` (the legacy `UserData/Events` key lives in `settings_migration.LEGACY_USER_EVENTS_SETTING_KEY`)
- Supported calendar range: `SUPPORTED_MIN_YEAR` (1200) / `SUPPORTED_MAX_YEAR` (1600), the single source every surface clamps to
- Update endpoints: `APP_RELEASES_API_URL`, `APP_RELEASES_PAGE_URL`, `HOLIDAYS_UPDATE_URL` (all `github.com/ShamsiTray/ShamsiTray`)
- Font families (Vazirmatn, Inter, Font Awesome 7 Free), `Theme` inner class (`DARK`/`LIGHT`), theme palettes, tray-icon colors
- UI constants (font sizes, `CALENDAR_WIDTH`/`HEIGHT`, `CALENDAR_BORDER_RADIUS_PX`, `DRAGGABLE_AREA_HEIGHT`), Persian/Gregorian month and weekday names
- `FontAwesome` icon characters (`FAS` class: square/check, sun/moon, xmark, minus)
- Methods: `ensure_user_data_dirs()`, `set_theme()`, `get_current_palette()`, plus module-level `APP_CONFIG` instance

### `src/main.py` (Entry point)
- Sets `Qt.HighDpiScaleFactorRoundingPolicy.PassThrough`
- `QApplication.setQuitOnLastWindowClosed(False)`
- **Windows AppUserModelID**: `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID` for correct taskbar icon
- Verifies assets, loads fonts (Vazirmatn, Inter, Font Awesome 7 Free)
- Checks `QSystemTrayIcon.isSystemTrayAvailable()`
- Acquires a `QLockFile` single-instance lock (before settings and the migration), then creates `JsonSettings` and runs `migrate_from_registry()` (one-time legacy registry → JSON)
- Shows `TutorialWindow` on first run (tracked via `Tutorial/HasShown`)

### `src/core/event_service.py` (EventService)
- Single owner of the user-event store: the in-memory mapping, every mutation (add / update_key / remove_for_date / delete_key / upsert / clean_expired / plan_import + apply_import) and every save
- `reload()` refreshes the dict IN PLACE: the calendar holds a live reference, so rebinding would leave it reading a stale object
- Mutating paths are keyed, not date-scoped: `add()` replaces only the event of the same recurrence, and `update_key()` edits one entry — keeping that entry's key while the recurrence stands (a clamped occurrence must not walk a recurring event's anchor) and re-keying only itself when the recurrence changes
- `target_key()` states that verdict without saving — which key an event would land on — so the event manager's own editor reaches the same answer as `add()` instead of re-deriving one. A second caller reasoning about the store by visible date reintroduces the eviction `add()` no longer does
- `update_key()` REFUSES to land on an occupied key: an edit must never silently destroy another event. `merge_into` is the way past it once the user has been asked, folding the edited text into the target entry as a new line (never duplicating a line) in the same single save
- Transactional shape: snapshot → mutate in place → save; on failure the snapshot is restored IN PLACE (dict identity preserved so the calendar's live reference sees the rollback) and `on_save_error` fires for interactive paths
- Import is reconciled by visible date: `plan_import()` reports exactly which existing events an import would replace (exact-key overwrites AND same-date cross-representation collisions); `apply_import()` computes merge + replacement + expiry in memory and saves exactly once, so no half-imported file can outlive a failed save
- The controller and the event manager request operations; they never mutate persistence directly

### `src/core/app_controller.py` (SystemTrayIcon)
- Tray icon with dynamic date overlay (red on holidays/Fridays, accent on event days)
- Context menu: Calendar, Converter («تبدیل تاریخ»), «مدیریت رویدادها» (event manager), «مشاهده تعطیلات» (holiday viewer), «بررسی بروزرسانی» (update check), Theme toggle, Autostart toggle, Always-on-top toggle («تقویم همیشه در بالا»), Exit
- Calendar popup: month navigation, day cells with holiday/event indicators, go-to-date (right-click year), reopens on last-browsed month; left-click tray toggles the whole calendar. Unpinned it is a flyout rather than a pinned tool window: losing activation closes it, and the tray click that dismissed it does not reopen it (its press closed the popup, so its release only finishes the toggle).
- Event management: add/edit/delete with recurrence (`none`/`monthly`/`yearly`), auto-delete (one-time only), expired-event cleanup at startup and at midnight; every store mutation routes through `core/event_service.py`. A date can hold several events (they are told apart by key), so the day's menu edits and deletes one event at a time, and adding replaces only the event of the same recurrence
- Import: the file is reconciled against the store first; when it would replace existing events a themed confirm shows the count and a preview, and the whole import applies as ONE atomic save
- Right-clicking a day offers «کپی تاریخ» (Jalali / Gregorian / both) with a brief «کپی شد» flash
- Right-clicking a day also offers «فاصله تا امروز» in its own group: a themed in-calendar overlay whose box carries the signed day total and direction, the Jalali y/m/d breakdown (omitted under one month, where it would restate the total verbatim - `DateDistance.has_calendar_units`), and the day's own date («تاریخ امروز است.» when the day is today). Measured from the calendar's `current_date`, so it cannot disagree with the grid
- Date converter: Shamsi ↔ Gregorian with copy-to-clipboard and live red border for out-of-range years. Its «فاصله زمانی» line breaks the gap down in **Jalali** via the shared `describe_date_distance()`, so it and the calendar notice cannot disagree
- Timers: minute tick, midnight rollover (`ms_until_midnight` + 500 ms buffer via `schedule_next_midnight_check`), Windows time-change handling via `TimeChangeEventFilter`
- Update wiring: daily auto-check (throttled), manual check, installer download (sha256-verified) to Downloads, holiday-store refresh; the update popup is a themed `ConfirmDialog` three-way choose (download / ignore / remind later). The installer download shows the themed `DownloadUpdateDialog` (no stock progress dialogs).
- Update reliability: `UpdateChecker.check_concluded(bool)` ends every round — success stamps `Updates/LastCheckMs`, failure schedules an automatic-check retry every 10 minutes (max 3 per session, `AUTO_CHECK_RETRY_DELAY_MS`/`AUTO_CHECK_MAX_RETRIES` in `app_controller.py`). The retry verdict reads the round snapshot `_round_was_manual`, not the live manual flag (already consumed by `round_finished`, which fires first) — a failed manual round reports to the user and stops there.
- Reply hygiene: every `QNetworkReply` is handled once (self-disconnecting `finished` handler), guarded with `isOpen()` before any `readAll()`, and released via `deleteLater()` — reading an aborted TLS transport is what makes Qt print `QIODevice::read (QSslSocket): device not open`. The installer download streams in `readyRead` chunks to a `<name>.exe.part` file (incremental sha256, atomic rename on verify) so the reply is never read post-close and RAM stays flat regardless of installer size.
- Update test hooks (env vars, read at check time): `SHAMSITRAY_DEBUG_DATA_VERSION=<int>` overrides the local holiday-store version (set `0` to force a holiday update), `SHAMSITRAY_HOLIDAYS_URL=<url>` overrides the holiday update endpoint (e.g. a local `python -m http.server`).
- `ConfirmDialog` is draggable from blank surfaces and auto-grows its fixed width so the widest button caption never clips. Inside the calendar it is replaced by `ConfirmOverlay`: same card, but a non-draggable child widget over the dimmed grid, parented and shown/hidden by the calendar
- Theme: a three-way preference (`Appearance/ThemeChoice` — `system` follows Windows, `light`/`dark` pin it; `_theme_choice()`, `Config.THEME_CHOICES`, and a menu toggle that cycles all three). `_get_windows_theme()` resolves the theme that actually applies and `_apply_theme()` sets the global stylesheet and re-styles every open window

### `src/core/update_checker.py` (UpdateChecker)
- Compares remote vs local app version; exposes `is_newer_version()`, `digest_hex()`, `DAY_MS`
- GitHub releases API for app updates; raw.githubusercontent for holiday-store updates (`HOLIDAYS_UPDATE_URL`)
- Downloads release installer and verifies SHA-256 checksum before handing off

### `src/ui/windows/`
- `BaseFramelessWindow`: base for all popups — rounded rect paint, draggable top 40px (shared `FramelessDragMixin` from `ui_helpers`, bottom clamp keeps the top 50 px reachable), translucent bg, always-on-top tool window (`WindowTitleBar` + `apply_windows_styles()` helpers + Windows style fixes). `set_always_on_top()` flips `WindowStaysOnTopHint` on a window that is already up (a flag change only takes effect on the next show, so it re-shows in place and re-activates), and a window that opts in with `CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED` (the calendar popup) dismisses itself when it loses activation to a foreign window — the dialogs it opened itself are recognised through the parent chain
- `PersianCalendarWidget`: main calendar popup (month grid, nav, today button, gregorian date with format toggle, event context menus, go-to-date overlay, reopens on last-browsed month); signals `event_added`/`event_removed` plus the key-scoped `event_updated_by_key`/`event_removed_by_key`. The editor save carries the key of the event it was opened for (`_edited_target_key` mirrors the store's re-key rule); when that target is occupied it emits nothing and asks, via the merge overlay, whether to fold the two events together. The add editor is opened blank on a date that already holds events, with the modes in use there disabled, and is not offered at all when a date carries all three
- `DateConverterWindow`: Jalali ↔ Gregorian converter (year/month/day combos, elapsed-time display, copy-to-clipboard, live red border for out-of-range years)
- `EventManagerWindow`: searchable/grouped event list with filters, inline edit overlay (shared `EventInputWidget`, date selector visible in edit mode so an event's date can be changed — prefilled with the event's anchor / next occurrence for recurring), confirmed delete, import/export buttons, auto-delete badges; syncs with calendar edits. Its add path asks the store for `target_key()` and only reports a collision when THAT key is occupied (an add stacks beside another recurrence); its edit path stays an explicit date-level confirmation, because the store is keyed and an edit must never destroy an event it was not opened for
- `HolidayViewerWindow`: read-only grouped-by-month holiday browser with year stepper
- `TutorialWindow`: first-run guide with welcome.gif (500×365)

### `src/ui/widgets/`
- `CalendarDayCell` (`ClickableLabel`): day cell with `clicked`/`add_event_requested`/`remove_event_requested`/`distance_requested` plus the per-event `edit_event_requested_specific`/`remove_event_requested_specific` (a day with several events gets one row per event, each carrying the event's key), custom tooltip (500ms, cursor-position truth check), context menu (re-syncs host hover via `normalize_day_hover`). Add and edit are separate rows — a date with events keeps a blank «افزودن رویداد» beside the edit/delete rows rather than one row that relabels itself and opens a prefilled editor — and a per-event label is folded onto one line, because a raw multi-line `text` (a merged event) blows the menu out sideways
- `Tooltip` (`CustomTooltip`): singleton tooltip bypassing Qt6 native rendering (border-radius fix on Windows)
- `EventInput` (`EventInputWidget`): RTL event editor overlay with recurrence combo (plain, `fit_combo_width`, modes already used on the date dimmed via `set_disabled_recurrences` — a date holds at most one event per mode), auto-delete checkbox, reusable date-selector row, year-range clamping (1200–1600) + red border hint. The dimmed rows stay listed (the mode is a choice the date has spent, not a hidden one) and the combo never sits on one: both `set_data` and `set_disabled_recurrences` push the selection to the first usable mode, because the add path prefills «بدون تکرار» and that is row 0
- `GoToDate` (`GoToDateWindow`): jump-to-month widget (Persian year 1200–1600, custom rounded bg)
- `Checkbox` (`CustomCheckbox`, `IconCheckboxActionWidget`): FontAwesome-icon checkboxes
- `ConfirmDialog` (`ConfirmDialog`): themed dialog — `ask` (yes/no), `choose` (three-way), `notify` (single button, optional `detail` line); used by update popup + all confirm flows; draggable, button-fit auto-width. `notify(..., key=...)` opts a notice into single-instance replacement: a newer result of the same key re-words the notice already on screen instead of stacking a second window (the update round uses `UPDATE_CHECK_NOTICE_KEY`)
- `ConfirmCard` (`ConfirmCard` / `ConfirmOverlay`): the shared card half of both surfaces — badge, title, message, detail box, buttons, painting. A **plain mixin**, not a widget base, so one card serves a `QDialog` and a `QWidget` child without giving either two QWidget branches; it sets `WA_TranslucentBackground` and delegates finishing to `_finish_choice()` (accept/reject on the dialog, hide on the overlay). `ConfirmOverlay` is persistent and fixed-*shape* (notice = 1 button, ask = 2), not fixed-content: the delete card raises its description line per question (`set_message`) and keeps the preview box for the event text alone, mirroring the event manager's dialog. Every overlay's `chosen` must be connected by the calendar - an overlay only hides itself, so an unconnected one leaves the dimmer up over a card that is already gone
- `DownloadDialog` (`DownloadUpdateDialog`): themed installer-download progress card (determinate/busy, Persian digit counters, cancel signal wired to `UpdateChecker.cancel_download`)
- `MenuWidgets` (`HoverWidget`, `MenuActionWidget`, `ThemeToggleActionWidget`): custom tray-menu action widgets with hover states

### `src/utils/`
- `date_utils.py`: `to_persian_digits()`, `from_persian_digits()`, month/weekday name helpers, leap-year + days-in-month for both calendars, `validate_year_range()`, and the date-distance layer — `DateDistance` (frozen dataclass: `years`/`months`/`days` + signed `total_days`, with `is_today` and `has_calendar_units` derived - the latter False exactly when the breakdown would restate the total; both formatters are undefined for today and every caller branches on `is_today` first), `describe_date_distance()`, `format_distance_total()`, `format_distance_breakdown()`. The decomposition is largest-unit-first with per-step day clamping, so it is order-dependent and deliberately **not** a fixed conversion of the units into days
- `asset_loader.py`: `verify_assets()`, `load_fonts()`
- `logger.py`: `setup_logging()` — RotatingFileHandler (1MB × 3 backups) + console, millisecond timestamps. `install_qt_message_handler()` mirrors Qt's own diagnostics into that log under `qt.<category>` loggers, drops the benign warnings in `_QT_BENIGN_WARNINGS` by severity (never by text alone), and lets a fatal terminate the process like Qt's default handler
- `native_events.py`: `TimeChangeEventFilter(QAbstractNativeEventFilter)` — handles Windows `WM_TIMECHANGE` (0x001E) as a pure detector (the controller coalesces bursts via `TIME_CHANGE_COALESCE_MS`, so a burst costs one refresh; the raw per-message trace is DEBUG-only) and `WM_SETTINGCHANGE` (0x001A), filtered to the `ImmersiveColorSet` section — which is what lets the app follow the Windows light/dark setting live. The settings-change lParam string is read as a wchar walk capped at 32 chars, so a malformed payload cannot be walked arbitrarily far
- `startup_registry.py`: `StartupRegistry` — autostart `Run`-key access (`read()` / `write()` / `delete()`) plus `RUN_KEY_PATH`. The controller's autostart policy goes through this seam so tests can drive it against an in-memory backend
- `ui_helpers.py`: `create_tray_pixmap()` (DPI-aware), `paint_rounded_card()` + `FramelessDragMixin` (shared frameless drag AND mouse-event routing, with `drag_strip_height` / `drag_bottom_keep_visible` knobs), `YearRangeValidationMixin` (shared red-border year validation), `combo_stylesheet()` + button/line-edit/scrollbar stylesheets (`global_scrollbar_stylesheet()`, `nav_button_stylesheet()`), `fit_combo_width()`
- `json_settings.py`: `JsonSettings` — QSettings-compatible API over `settings.json` (atomic writes, corrupt-file tolerance); a failed write keeps its keys dirty, so re-setting the same value retries the disk write instead of hitting the equal-value early return
- `settings_migration.py`: `migrate_from_registry()` — one-time, idempotent (via `Migration/RegistryMigratedToJSON`) registry → JSON
- `event_io.py`: `load_user_events()`/`save_user_events()` (versioned v2 store), recurrence-key model (`make_event_key`/`parse_event_key`/`recurrence_of_key`: one-time `YYYY-MM-DD`, yearly `0000-MM-DD`, monthly `0000-00-DD`), `normalize_*` (legacy v1 migration + canonical key validation; load counts and logs same-date key collisions, last write wins, and a clean load re-arms saves), `export_events_to_file()`/`import_events_from_file()` (native file dialogs), import reconciliation (`keys_share_visible_date()`, `build_import_plan()` — the visible-date collision model the EventService uses)
- `holiday_io.py`: `parse_holidays()`, `read_version()`, `resolve_holidays_store()`, `update_holidays_store()` — versioned AppData store, seed from bundle, atomic swap

---

## 7. Build Process

**PyInstaller** (`build/PyinstallerConfig.json`):
- Entry `run.py`; one-folder mode (`onefile: false`), windowed (`console: false`), `contents_directory: "."`
- Icon: `assets/images/icons/icon.ico`
- Assets: only runtime files (`assets/fonts/`, `assets/data/holidays.json`,
  `assets/images/icons/icon.ico`, `assets/images/welcome.gif`) → same paths;
  PSDs/LogoEvolution/screenshots/badges are NOT bundled
- Version resource: `build/details.txt`
- Pathex includes `src/`

**Inno Setup** (`build/SetupScript.iss`):
- Modern wizard, x64 only, Windows 10 1809+ (`MinVersion=10.0.17763`, the oldest build PyQt6 6.x / Python 3.12 run on)
- **Does NOT write the autostart `Run` key** (the app manages autostart itself)
- Seeds `%LOCALAPPDATA%\ShamsiTray\holidays.json` with `onlyifdoesntexist` / `uninsneveruninstall`
- Uninstaller: checks for running instance (tasklist), custom page with "remove user settings" checkbox clearing `%LOCALAPPDATA%\ShamsiTray` + legacy `HKCU\Software\ShamsiTray`. A silent (`/VERYSILENT`) run never prompts or blocks on a live tray or a locked exe; at post-uninstall the install directory loses only the empty subdirectories Inno left behind, and goes itself only if that left it empty - files the uninstaller does not own are never force-deleted
- Output: `output/ShamsiTraySetup-<version>.exe`

---

## 8. Testing

**Automated** (pytest + pytest-qt, `pytest.ini` already configured; UI tests run headless via the offscreen Qt platform in `tests/conftest.py`):
```powershell
pip install -r requirements-dev.txt
pytest
```

The suite never touches the developer's real Windows registry: booting a tray
would otherwise write `HKCU\...\Run\ShamsiTray`, so every boot injects the
in-memory backend in `tests/fake_registry.py` via the `fake_startup_registry`
fixture. The real `winreg` implementation has a separate opt-in integration test,
deselected by default (`pytest.ini` sets `-m "not windows_integration"`):

```powershell
pytest -m windows_integration
```
Test modules (in `tests/`): every module of the app has a dedicated file —
persistence/settings: `json_settings`, `settings_migration`, `event_io`,
`holiday_io`, `event_service`; core: `update_checker` (pure helpers + full
networking over a local HTTP server: check round-trips, streaming installer
download, sha256 verification, cancel, truncated transfers), `app_controller`
(update-flow orchestration, retry logic, tray rendering/tooltips, timers,
theme & startup settings, window lifecycle, import/export); UI: `config`,
`ui_helpers` (drag mixin, rounded card, pixmaps, stylesheet builders),
`logger`, `asset_loader`, `native_events`, `tooltip`, `window_chrome`,
`checkbox`, `download_dialog`, `go_to_date`, `calendar_day_cell`,
`base_window`, `tutorial_window`, `calendar_window`, `main`; plus the
app-wide suite — `clock`, `calendar_model`, `converter_window`,
`new_windows`, `boot_smoke`. (`test_dates` covers the date/calendar
utilities, `test_events` the event key-model, and `startup_registry_integration`
the real winreg backend, opt-in via marker.)

Conventions worth keeping when adding tests:
- `tests/conftest.py` drops the scheduled 30s auto update check (autouse
  `no_stray_network_checks`) so no test can ever touch the real network.
- Offscreen Qt has no real cursor: `tests/qt_mousing.py` synthesizes mouse
  events; child-widget visibility checks need the parent actually `show()`n.
- `utils.logger` sets `propagate = False`, so `caplog` stays empty — attach a
  capture handler to the specific module logger instead.
- `tests/` is a package-free folder but imported as `tests.xxx` by the suite
  (pytest `rootdir` + `pythonpath = src`); keep helper names unique.

**Manual checklist** (run after changes):
- [ ] Tray icon shows correct Shamsi day number
- [ ] Tray icon color: red on Fridays/holidays, normal otherwise
- [ ] Left-click tray → calendar popup opens at current month
- [ ] Calendar: month nav, today button, go-to-date (right-click year), reopens on last-browsed month
- [ ] Hover day cell → tooltip with holiday/event details
- [ ] Right-click day → add/edit/delete event (recurrence, auto-delete)
- [ ] Tray context menu → Date Converter works both ways
- [ ] Theme toggle cycles System/Light/Dark and persists across restarts
- [ ] Autostart toggle writes/removes registry `Run` key (via app, not installer)
- [ ] Baseline: fresh machine → settings.json + holidays.json seeded in `%LOCALAPPDATA%\ShamsiTray`
- [ ] Upgrade path: 1.3.1 → current (registry→JSON migration fires; holiday store seeds)
- [ ] Update check: manual «بررسی بروزرسانی» works; event manager import/export works
- [ ] Tutorial shows on first run only
- [ ] Installer: installs, creates start menu entry, autostart managed by app
- [ ] Uninstaller: removes files, optionally removes settings

---

## 9. Lint, Typecheck & CI

CI (`.github/workflows/ci.yml`) runs `python build/check_versions.py`,
`ruff check` and `pytest` on a Windows runner for every pull request and every
push to `main`. Locally, the same checks:

```powershell
# Install
pip install ruff mypy

# Lint + format
ruff check src/ tests/ run.py
ruff format src/

# Type check (once type hints are comprehensive)
mypy src/
```

`ruff format` and `mypy` stay local conveniences: the tree is not format-clean,
so CI does not gate on either.

---

## 10. Git Workflow

- `main` holds linear release history; every released version is tagged
- Current work in progress: `feature/roadmap-hardening` (v1.4, unmerged)
- **Atomic commits**: one logical change per commit — a fix or feature lands with its tests in the same commit, and any `AGENTS.md`/docs the change makes true ride along with it instead of arriving as a separate `docs:` commit. Every commit leaves the tree in a passing state, so history stays bisectable and revert-friendly.
- Commit subjects follow Conventional Commits and are always scoped: `type(scope): imperative summary` — lowercase, no trailing period, at most 72 characters, English only (name a UI label by what it is, e.g. "Convert button", not by its text)
  - Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style` (`style` is only for purely mechanical diffs; those go in `.git-blame-ignore-revs`)
  - Scopes name the feature area, not the layer: `events`, `calendar`, `converter`, `holidays`, `tray`, `update`, `dialog`, `theme`, `ui` (shared widgets and helpers), `dates`, `settings`, `logging`, `installer`; tooling uses `build`, `deps`, `assets`, `release`; docs use `agents`, `readme`, `comments`; a repo-wide change (suite-wide tests, mechanical formatting) uses `app`
  - Bodies are optional: a few lines on what and why (about six at most, wrapped at 72), no file lists, test inventories or change narration
- `.git-blame-ignore-revs` lists purely mechanical commits so `git blame` skips them (enable locally with `git config blame.ignoreRevsFile .git-blame-ignore-revs`; GitHub reads it automatically). Add a commit only if its whole diff is mechanical, and re-check the hashes after any history rewrite
- Commit bodies state what changed and why in app terms — never local paths or private-project/provenance references
- Use branches for experiments/features: `git switch -c feature/<name>`
- Never copy folders for versions (historical `v0.x`/`v1.x` folders were folded into history)
- `experiment/xnightstar` branch preserves the abandoned xNightStar calendar experiment (forked at `v0.1.3`)
- `assets/images/LogoEvolution/` is git-ignored design work; `build/` configs are tracked
- Installers are never committed: they live in the git-ignored `output/` folder and are attached to GitHub releases