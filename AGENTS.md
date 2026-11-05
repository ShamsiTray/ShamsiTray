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
    themes.py            # The theme registry: every palette (stock dark + the gallery packs), load-bearing data
    main.py              # Entry point: QApplication, asset verification, fonts, settings migration, tray init
     core/
      app_controller.py  # SystemTrayIcon: calendar logic, event handling, update-wiring, timers
      event_service.py   # EventService: single owner of the event store - mutations, transactional saves, import reconciliation
      update_checker.py  # UpdateChecker: GitHub release + holiday-store checks, download, sha256 verify
    ui/
      windows/           # PersianCalendarWidget, DateConverterWindow, DateDistanceWindow,
                         # EventManagerWindow, HolidayViewerWindow, ThemeGalleryWindow, TutorialWindow,
                         # BaseFramelessWindow (+ window-chrome helpers)
      widgets/           # CalendarDayCell, Tooltip, EventInput, GoToDate, Checkbox (custom),
                         # ConfirmDialog (themed), ConfirmOverlay (in-calendar), CalendarSwitch
                         # («شمسی | میلادی» pill of the date tools' caption bars), Menu widgets,
                         # tray-menu builder, OverlayBlocker (one dimmer behind every overlay),
                         # theme_shot + gallery_widgets (the theme gallery's preview renderer and cards)
    utils/
      date_utils.py      # Jalali/Gregorian helpers, formatting, digit conversion, leap-year, validation
      asset_loader.py    # Font loading, asset verification
      logger.py          # Rotating file + console logging under %LOCALAPPDATA%\ShamsiTray\logs
      native_events.py   # Windows WM_TIMECHANGE / WM_SETTINGCHANGE native event filtering (clock changes, live system theme)
      startup_registry.py  # Autostart Run-key access (read/write/delete) behind a fakeable seam
      windows_theme.py   # WindowsThemeBackend: the winreg read behind the 'system' theme verdict
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
- **Comments**: Comment only when it adds something the code can't say: why a choice was made, a constraint, a workaround, a non-obvious side effect. Don't narrate what the code does, restate names or types, or describe the change you just made. Leave existing comments alone unless your change makes them wrong. A constraint's rationale lives once at its owner (the constant or class docstring); elsewhere, point to it by symbol name in a few words. Tests are the exception: a docstring may state the behavior or regression the test pins down, when the test name alone doesn't make it clear. Describe the behavior, not the steps.
- **Settings**: `JsonSettings` (JSON-backed, QSettings-compatible API) → `%LOCALAPPDATA%\ShamsiTray\settings.json`. Atomic writes (temp file + `os.replace`), tolerant of corrupt files.
- **Persistence**: Use `utils/event_io.py` and `utils/holiday_io.py`; never write user data to the registry (legacy key is read-only migration source).
- **Themes**: Palettes live in `src/themes.py` (the stock dark theme plus the gallery packs); `Config.DARK_PALETTE` is `THEMES["dark"]` and every other palette is addressed by its registry key. Applied via `Config.set_theme()` — which takes the *resolved* theme key, not the preference: `Appearance/ThemeChoice` (`system` or a theme key, defaulting to `system`) is resolved first, and a legacy `"light"` save maps onto `Config.SYSTEM_LIGHT_THEME`

---

## 6. Key Components

### `src/config.py` (Config class)
- `APP_VERSION`, `APP_NAME`, `COMPANY_NAME`
- Paths: `PROJECT_ROOT`, `ASSETS_DIR`, `ICON_PATH`, `FONT_DIR`, `TUTORIAL_GIF_PATH`, `HOLIDAYS_FILE_PATH`
- User-data paths under `%LOCALAPPDATA%\ShamsiTray`: `USER_DATA_DIR`, `USER_LOG_DIR`, `LOG_FILE_PATH`, `SETTINGS_FILE_PATH`, `USER_EVENTS_FILE_PATH`, `HOLIDAYS_STORE_PATH`
- Settings keys: `AUTO_START_SETTING_KEY` (`General/OpenAtLogin`), `CURRENT_THEME_CHOICE_SETTING_KEY` (`Appearance/ThemeChoice`; holds `system` or a theme key — a legacy `"light"` save maps onto `SYSTEM_LIGHT_THEME` at read time), `FAVORITE_THEMES_SETTING_KEY` (`Appearance/FavoriteThemes`; the gallery stars), `TUTORIAL_SHOWN_SETTING_KEY` (`Tutorial/HasShown`), `ALWAYS_ON_TOP_SETTING_KEY` (`Calendar/AlwaysOnTop`; read with a `True` default, since the popup was pinned before the toggle existed), `UPDATE_CHECK_ENABLED_SETTING_KEY`, `LAST_UPDATE_CHECK_SETTING_KEY`, `IGNORED_UPDATE_VERSION_SETTING_KEY` (the legacy `UserData/Events` key lives in `settings_migration.LEGACY_USER_EVENTS_SETTING_KEY`)
- Supported calendar range: `SUPPORTED_MIN_YEAR` (1200) / `SUPPORTED_MAX_YEAR` (1600), the single source every surface clamps to
- Update endpoints: `APP_RELEASES_API_URL`, `APP_RELEASES_PAGE_URL`, `HOLIDAYS_UPDATE_URL` (all `github.com/ShamsiTray/ShamsiTray`)
- Font families (Vazirmatn, Inter, Font Awesome 7 Free), `Theme` inner class (`SYSTEM`/`DARK`), tray-icon colors
- Theme registry: `DARK_PALETTE` (`THEMES["dark"]`), `SYSTEM_LIGHT_THEME` (`catppuccin_latte` — the stock light palette's successor for the `system` verdict; `"light"` is not a selectable key), `EXTRA_THEMES` (the 72 gallery packs), `THEME_NAMES` (slug-level exact display names: brand spellings and the `&` cloud customs — consulted first by config's resolver), `THEME_CHOICES` (`system` + every registry key — the validator of the persisted preference), `theme_catalog()` (gallery order: dark theme first, then dark-then-light in the themes module's file order — the picker browses by popularity, never alphabetized), `theme_display_name()`, `palette_is_dark()` (WCAG luminance verdict the gallery's dark/light grouping runs on — the tray glyph's polarity is the taskbar verdict's, not this)
- UI constants (font sizes, `CALENDAR_WIDTH`/`HEIGHT`, `CALENDAR_BORDER_RADIUS_PX`, `DRAGGABLE_AREA_HEIGHT`), Persian/Gregorian month and weekday names
- `FontAwesome` icon characters (`FAS` class: square/check, xmark, minus, trash, palette)
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
- `on_store_changed` fires once per committed save, announced through the service's own dispatch: a commit the composition itself makes is announced by that composition in flight (re-entrant announcements swallow), so the ride-along cleanup cannot run the refresh twice. The application subscribes its whole refresh composition once (`_refresh_after_events_changed` — expiry ride-along, then calendar, tray, manager and an open gallery), so no mutation caller composes "mutate then refresh" itself. The hook keeps the module Qt-free; it must never rebind the dict, and the manager's own edit/delete and the import flow ride it instead of telling the controller separately
- Import is reconciled by visible date: `plan_import()` reports exactly which existing events an import would replace (exact-key overwrites AND same-date cross-representation collisions); `apply_import()` computes merge + replacement + expiry in memory and saves exactly once, so no half-imported file can outlive a failed save
- The read surface is `utils.event_io`'s pure query helpers over the live dict view (`events_for_date`, `events_on_date`, `keys_matching_date`, `events_sorted_by_next_occurrence`) — the same functions the service's mutation paths call; the service exports no delegate methods of its own, and the dict view handed to the calendar is the intentional live-read design
- The controller and the event manager request operations; they never mutate persistence directly

### `src/core/app_controller.py` (SystemTrayIcon)
- Tray icon with dynamic date overlay (red on holidays/Fridays, accent on event days — both floored through `legible_on()` against the nominal taskbar grounds, since the glyph's ground is the taskbar strip, not the app surface; the white/black polarity of the plain day follows `taskbar_uses_light()`, not the palette)
- Context menu: Calendar, Converter («تبدیل تاریخ»), «فاصله دو تاریخ» (distance between two dates), «مدیریت رویدادها» (event manager), «مشاهده تعطیلات» (holiday viewer), «بررسی بروزرسانی» (update check), «تم‌ها» (theme gallery), Autostart toggle, Always-on-top toggle («تقویم همیشه در بالا»), Exit; the four tool-window openers share `_show_or_raise`, which brings an already-open window back to the front (a minimized one still reports visible, so it is restored with `showNormal()` before raise+activate). The menu's composition (row order, separators, the close-then-open deferral for nested dialogs) lives beside the row widgets in `ui/widgets/tray_menu.py` (`build_tray_menu()` + the row helpers + `close_menu_then()`); the `_toggle_*` callbacks keep their controller-side owner, and the builder reaches them like the manager reaches `event_service`. The gallery opener follows the same close-then-open deferral (`_open_theme_gallery`)
- Calendar popup: month navigation, day cells with holiday/event indicators, go-to-date (right-click year), reopens on last-browsed month; left-click tray toggles the whole calendar. Unpinned it is a flyout rather than a pinned tool window: losing activation closes it, and the tray click that dismissed it does not reopen it (its press closed the popup, so its release only finishes the toggle).
- Event management: add/edit/delete with recurrence (`none`/`monthly`/`yearly`), auto-delete (one-time only), expired-event cleanup at startup and at midnight; every store mutation routes through `core/event_service.py` — reached publicly as the `event_service` attribute (the manager's `event_store`), with `user_events` still the live dict view and its load-bearing in-place setter. The wrapper methods remain only the request API the calendar's signals and tests call; the post-save refresh of the calendar, tray and manager hangs off the service's `on_store_changed` hook (`_refresh_after_events_changed`), not off any wrapper. A date can hold several events (they are told apart by key), so the day's menu edits and deletes one event at a time, and adding replaces only the event of the same recurrence
- Right-clicking a day offers «کپی تاریخ» (Jalali / Gregorian / both): the triggered row itself is the feedback — it morphs into «✓ کپی شد» over the shared copy pill (`copied_pill_ground`'s opaque accent wash, caption floored to the success tone, the paint pinned LTR so the checkmark stays left on every locale) while the other copy rows grey out, and after 450 ms both menus close and the rows restore (`CopyDateMenu` intercepts only leaf-row activation, so Qt keeps owning hover, keyboard, RTL mirroring, the arrow and placement); nothing floats over the desktop — the tooltip `flash_copied` remains to the converter window's and the distance window's own copy feedback only
- Right-clicking a day also offers «فاصله تا امروز» in its own group: a themed in-calendar overlay whose box carries the signed day total and direction, the Jalali y/m/d breakdown (omitted under one month, where it would restate the total verbatim - `DateDistance.has_calendar_units`), and the day's own date («تاریخ امروز است.» when the day is today). Measured from the calendar's `current_date`, so it cannot disagree with the grid
- Date converter: Shamsi ↔ Gregorian with copy-to-clipboard and live red border for out-of-range years. Its «فاصله زمانی» line breaks the gap down in **Jalali** via the shared `describe_date_distance()`, so it and the calendar notice cannot disagree, and the line itself is a fifth copy row: a click copies the span alone - no caption, no «مانده/گذشته», the direction-free units the distance window shows - in Latin digits, and nothing when the date is today, whose «تاریخ امروز است.» stamps an empty payload and drops the cursor to the arrow
- Timers: minute tick, midnight rollover (`ms_until_midnight` + 500 ms buffer via `schedule_next_midnight_check`), Windows time-change handling via `TimeChangeEventFilter`
- Update wiring: daily auto-check (throttled), manual check, installer download (sha256-verified) to Downloads, holiday-store refresh; the update popup is a themed `ConfirmDialog` three-way choose (download / ignore / remind later). The installer download shows the themed `DownloadUpdateDialog` (no stock progress dialogs).
- Update reliability: `UpdateChecker.check_concluded(bool)` ends every round — success stamps `Updates/LastCheckMs`, failure schedules an automatic-check retry every 10 minutes (max 3 per session, `AUTO_CHECK_RETRY_DELAY_MS`/`AUTO_CHECK_MAX_RETRIES` in `app_controller.py`). The retry verdict reads the round snapshot `_round_was_manual`, not the live manual flag (already consumed by `round_finished`, which fires first) — a failed manual round reports to the user and stops there.
- Reply hygiene: every `QNetworkReply` is handled once (self-disconnecting `finished` handler), guarded with `isOpen()` before any `readAll()`, and released via `deleteLater()` — reading an aborted TLS transport is what makes Qt print `QIODevice::read (QSslSocket): device not open`. The installer download streams in `readyRead` chunks to a `<name>.exe.part` file (incremental sha256, atomic rename on verify) so the reply is never read post-close and RAM stays flat regardless of installer size.
- Update test hooks (env vars, read at check time): `SHAMSITRAY_DEBUG_DATA_VERSION=<int>` overrides the local holiday-store version (set `0` to force a holiday update), `SHAMSITRAY_HOLIDAYS_URL=<url>` overrides the holiday update endpoint (e.g. a local `python -m http.server`).
- `ConfirmDialog` is draggable from blank surfaces and auto-grows its fixed width so the widest button caption never clips. Its geometry is decided once, at presentation time (`_refit()`): after the width lands on the button captions, the wrapped message AND detail labels are pinned to their real `heightForWidth` at that width and the size is taken from the layout hint — sizing (or re-wording a notice) from pre-polish metrics left the replace/merge ask one line short until the first drag visibly re-flowed the window. Inside the calendar it is replaced by `ConfirmOverlay`: same card, but a non-draggable child widget over the dimmed grid, parented and shown/hidden by the calendar
- Theme: the preference under `Appearance/ThemeChoice` is `system` (follow Windows, the `_theme_choice()` default; the verdict is the injectable `WindowsThemeBackend` (`self.theme_backend`, mirroring the `startup_registry` seam: `tests/fake_theme.py` fakes it; off-Windows and a failed registry read both degrade to dark) reached through `_get_windows_theme()`) or any registry theme key the gallery pins; a legacy `"light"` save resolves onto `SYSTEM_LIGHT_THEME`. A `WM_SETTINGCHANGE/ImmersiveColorSet` broadcast repaints the tray glyph BEFORE its follow gates (`update_tray_icon(force=True)` first in `_handle_system_theme_change`): the glyph's colors judge the taskbar strip (`taskbar_uses_light()`, the shell mode), which arrives on the same broadcast but can move while the app verdict — the only thing the gates argue about — does not, and a skipped repaint would leave the glyph on yesterday's strip. `_apply_theme()` sets the global stylesheet and re-styles every open window. The gallery session is controller state: `_gallery_original_theme` anchors the session (previews revert to it on any non-apply close), `_gallery_pending_theme` remembers the in-flight preview; `_gallery_preview_theme` records without applying, `_gallery_commit_theme` persists + applies + re-baselines the session, `_gallery_restore_theme` is the cancel path (memory-only), and `_favorite_themes`/`_gallery_save_favorites` persist the stars validated against the registry key set (unknown keys dropped, duplicates collapsed)

### `src/core/update_checker.py` (UpdateChecker)
- Compares remote vs local app version; exposes `is_newer_version()`, `digest_hex()`, `DAY_MS`
- GitHub releases API for app updates; raw.githubusercontent for holiday-store updates (`HOLIDAYS_UPDATE_URL`)
- Downloads release installer and verifies SHA-256 checksum before handing off

### `src/ui/windows/`
- `BaseFramelessWindow`: base for all popups — rounded rect paint, draggable top 40px (shared `FramelessDragMixin` from `ui_helpers`, bottom clamp keeps the top 50 px above the taskbar), translucent bg, always-on-top tool window (`WindowTitleBar` + `apply_windows_styles()` helpers + Windows style fixes), and the tray-click hover repair mixed in from `HoverDriverMixin` (the QDialog hosts inherit it too). `set_always_on_top()` flips `WindowStaysOnTopHint` on a window that is already up (a flag change only takes effect on the next show, so it re-shows in place and re-activates), and a window that opts in with `CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED` (the calendar popup) dismisses itself when it loses activation to a foreign window — the dialogs it opened itself are recognised through the parent chain; a form window can also opt in with `CLEAR_FOCUS_ON_BLANK_CLICK` (the distance window), which answers a press landing on a no-focus surface of itself (a label, the result card, blank margins) by clearing the Qt-held field focus — a click there would otherwise never move the `:focus` accent ring away
- `PersianCalendarWidget`: main calendar popup (month grid, nav, today button, gregorian date with format toggle, event context menus, go-to-date overlay, reopens on last-browsed month); signals `event_added`/`event_removed` plus the key-scoped `event_updated_by_key`/`event_removed_by_key`. The editor save carries the key of the event it was opened for (`_edited_target_key` mirrors the store's re-key rule); when that target is occupied it emits nothing and asks, via the merge overlay, whether to fold the two events together. The add editor is opened blank on a date that already holds events, with the modes in use there disabled, and is not offered at all when a date carries all three
- `DateConverterWindow`: Jalali ↔ Gregorian converter (year/month/day combos, an elapsed-time sentence split into caption / span / direction («فاصله زمانی:» / the units / the «مانده-گذشته» word) where only the span is a copy row and the wash covers exactly the glyphs the click copies - span alone on the clipboard, nothing when the date is today (which collapses the sentence back into the single span label); the four date values copy on click, the weekday footnotes are display-only because the long-form payload already carries the weekday - live red border for out-of-range years). The «نوع تبدیل» combo is gone: the input row's calendar is picked by the shared `CalendarSwitch` pill in the caption bar's far edge (same seat as the distance window's), feeding the same mode forks (`_input_is_jalali()` reads the pill) — a flip refills the fields with that calendar's today and the year bounds flip with it; the field row is the three bare columns روز/ماه/سال with no header labels. The results sit side by side as two field cards («ResultCard»: title, numeric form, long form, weekday footnote) — stacked blocks read as one pile, and bare columns were text on the flat fill (the viewer-chip failure again); the weekday keeps its own line because the full long form is too wide for two columns at `WINDOW_WIDTH`, and the date columns read the shared `format_*_long(..., with_weekday=False)` instead of `strftime`, whose names follow the process locale; both numeric displays come from the shared `format_*_numeric` too, so the display shape is the clipboard shape where the digits allow — the Jalali row shows Persian digits and copies Latin, the Gregorian row shows and copies the same Latin slash form; the five copy rows carry one `CopyRow` name with two sheets — a hover wash (the viewer's inert-row recipe, one step stronger, since here the row really is clickable) in a 6px-radius band: the four date rows' wash spans their card's inner width and reads as a row highlight, while the elapsed span stands alone on the open fill between its caption and its direction word: a stretch pair squeezes the sentence row to its sizeHint (the input row's centering pattern), the span's own horizontal padding shapes the wash band's inset around the span text and reads as the word gap at rest, while the row's spacing is the band's clearance to its neighbours on hover (the band paints the pill's whole widget rect, so no in-pill inset can keep its edge off them), so a text change re-measures and re-centers it and a window-wide bar never reads as a second card; «تاریخ امروز است.» opts out through the `copyable` property + re-polish so the wash never promises a copy the click cannot deliver; the results window follows the layout's measured minimum rather than a guessed height
- `DateDistanceWindow`: the gap between two arbitrary dates in either calendar. The caption row's `CalendarSwitch` (شمسی | میلادی) flips a `QStackedWidget` between a Jalali pair of `DateSelectorRow`s and a Gregorian pair (`GregorianDateSelectorRow`, the same row with English months, Latin digits and Gregorian month lengths); the pages do not inherit the app's support span (that stays the event editor's constraint): `DistanceJalaliRow` spans Jalali 1..9377 (`JALALI_YEAR_MIN/MAX`, the last year whose Gregorian twin stays inside `datetime.date`'s 9999) and `DistanceGregorianRow` datetime.date's whole 1..9999 (`GREGORIAN_YEAR_MIN/MAX`); switching carries the two days across (so the day total never changes, only the years/months/days split, since month lengths differ) and a row with no valid date, or one outside the target span, restarts from today - including a date that cannot exist in the target calendar at all (a Gregorian date before Jalali year 1 has no twin: the switch's carry maps the `ValueError` onto the same restart, which is what keeps the Gregorian floor free of the converter's 623 conversion-policy limit). Rows are labelled «از تاریخ» / «تا تاریخ» and built with `ltr_date_order=True` (fields read year, month, day from the left edge, the caption fixed at `LTR_LABEL_WIDTH_PX` and the day field floored at `LTR_DAY_WIDTH_PX`, so day and month share the row's slack in a balanced row; `_equalize_field_widths()` binds both pages' months to the wider of the two fitted minimums, so a per-calendar font-fit difference cannot jump the columns on the flip), `numbered_months=True` («۰۶ - شهریور» like the converter and go-to-date; the Gregorian label carries a leading LRM so «08 - August» is not reordered by the combo's RTL base) and `flag_empty_year=True` (an EMPTY year gets the red border and the range message like a wrong one - the shared mixin deliberately does not, because the editor's form may still be filling in); all three are opt-in, and the event editor opts into `numbered_months` too; what keeps the rows here their own look is `DistanceJalaliRow` / `DistanceGregorianRow`, attribute-only subclasses carrying `DistanceRowMetrics` (the converter's 40px fields and a regular 14px caption) over the shared render path, and the window opts into `CLEAR_FOCUS_ON_BLANK_CLICK`. The measure is direction-agnostic - the numbers are the absolute gap, so row order changes nothing and there is no «مانده/گذشته», no echo of the two dates and no swap button. One result card: the day total is the hero line (the accent nudged by `legible_on()` - shared in `ui_helpers` alongside `contrast_ratio`/`mix_colors` - until it clears 3:1 on the card - the dark accent alone is ~2:1), then under a hairline the breakdown (`format_distance_units()`, only when `has_calendar_units`), the same span in whole months (`format_distance_total_months()`, only when `has_month_total`, i.e. there is a year - otherwise it would repeat the breakdown) and the whole-weeks line (`format_distance_weeks()`, only when `has_full_weeks`), each shown only when it says more than the lines above; every result line is a copy target (`CopyLabel` / `CopyRow` -> `copy_with_flash()`: a click copies the sentence in LATIN digits, the app-wide copy convention, and flashes the app-wide «✓ کپی شد» at the cursor through `CustomTooltip.flash_copied`). The copy lines wear the converter's copy-row hover wash: one band over the whole hero sentence (the row carries the `:hover` and the overlay blocker's `WA_StyledBackground` opt-in — a custom `QWidget` subclass paints no stylesheet background without it, and its child labels stay inert; the band's breathing room around the sentence rides `CopyRow`'s layout margins (the vertical pair deliberately uneven, top 12 / bottom 2, so the pill centers on the ink rather than on a line box that parks it 5px above center — equal margins leave 10px more air under the baseline than over the caps), since QSS padding cannot inset a layout the way it insets a QLabel's text) and standalone pills on the three secondary lines; the message and the year hint copy nothing and never light. The card's top-right corner (the RTL reading-start corner) holds one «کپی همه» glyph (`copy_all_button`, an absolute child `ResultCard` repositions on its resizeEvent over `FAS.FA_COPY` with `COPY_ALL_CORNER_INSET_PX`, a 32px hit square in the caption bar's minimize-button language - transparent rest with a hairline 8px-radius border, `HOVER_BG` hover/pressed wash, accent focus ring and `TabFocus` - and the glyph carries `FONT_AWESOME_FAMILY`, since under Vazirmatn the U+F0C5 fallback walk logs a DirectWrite raster-font failure per candidate): a click fires every line the card currently shows - hero first, hidden ones skipped - as one clipboard block through the same `copy_with_flash`; shown and hidden beside the results (`_recompute`/`_reset_result`), so equality and the range message leave nothing to copy, and it is always parented before any show - a parentless `show()` flashes the glyph as a stray top-level window in the frames before the window opens. Equality answers «دو تاریخ یکسان هستند.» through the engine's own `is_today` verdict, deliberately not the converter's «تاریخ امروز است.» because neither date is asserted to be today. The range message is a window-level label (not a row-owned mixin hint, which two rows would race to hide) that sits in the card where the result would be, at 16px so it outweighs nothing it replaces. The window is a fixed size — and that size must leave the 58px hero line its real Vazirmatn box (90px: ascent 59 + descent 31, probed equal on both font plug-ins): squeezed under the label's rect, the digit tops flat-cut at their own edge, a cut the hover band's top edge rides.
- `EventManagerWindow`: searchable/grouped event list with filters, inline edit overlay (shared `EventInputWidget`, date selector visible in edit mode so an event's date can be changed — prefilled with the event's anchor / next occurrence for recurring), confirmed delete; import/export are the window's own dialog flows (`_import_events_from_dialog` / `_export_events_to_dialog` — `plan_import`/`apply_import` through the event store, the confirmation wording pinned verbatim by tests) that used to live on the controller; syncs with calendar edits. The caption bar IS the header row: its far edge carries the event counter (`count_label`) and the «افزودن رویداد» button, and no in-content headline repeats the window name (the window is titled by the taskbar/Alt-Tab native title and the tray menu row). It is opened fresh each time (`_show_or_raise` rebuilds the window after a close), so `showEvent` only refreshes when the store moved since the snapshot `refresh_list` last recorded (`_built_from`; sound as a shallow copy because store entries are replaced, never mutated in place) — a show-time rebuild of unchanged rows deferred a layout collapse of the scrollbar range to `(0,0)` for a frame, flashing the rail at every reopen. Its add path asks the store for `target_key()` and only reports a collision when THAT key is occupied (an add stacks beside another recurrence); its edit path stays an explicit date-level confirmation, because the store is keyed and an edit must never destroy an event it was not opened for. Each `EventRow` is a title over a date line that already spells the recurrence out («هر سال - ۵ مهر»), so no second badge repeats it; the one thing only the row can say is that a flagged one-time event will delete itself, which rides the date line's `AUTO_DELETE_MARKER` and its themed tooltip. Its actions are FontAwesome glyph buttons (`TooltipButton`, `FA_PEN`/`FA_TRASH`), which is why they carry an explicit accessible name — their own text is a private-use glyph — while the footer stays text-only. The trash button's tooltip is toned `danger` (the palette's holiday red) because deleting is the row's one destructive action and the glyph it explains is that same red; edit stays neutral. The list drops those tooltips on scroll once per gesture (`_on_list_scrolled` runs `_dismiss_row_tooltips` when a gesture starts, ticks inside one gesture only restart the `SCROLL_SETTLE_MS` timer, and the rows come from the `_rows` cache `refresh_list` builds - a per-tick `findChildren` + per-row cancel measured ~9 ms per wheel tick at 150 rows and was the fast-scroll jolt; pending timers need no per-tick cancel anyway, `_show_custom_tooltip`'s cursor check refuses to pop a tooltip over a widget the list has scrolled away; a hover that arms DURING the gesture pops between ticks, where later ticks drop a visible one by its owner through `current_owner()` - O(1) off the shared tooltip, and a «کپی شد» flash is owned by nobody), since a wheel scroll moves a row out from under a stationary cursor without an enter/leave pair. The scrolling viewport is opaque in `BACKGROUND_COLOR` like the viewer's — a transparent one repaints the translucent glass beneath every scrolled row and the motion ghosts
- `HolidayViewerWindow`: read-only holiday browser over badge rows: a day badge (number + full weekday, red-tinted on Fridays), the title with each holiday's optional lunar date split out by `split_lunar_date()` and rendered muted and inline after its own line — the tone shift plus a hairline gap (a tiny-font no-break space, `_LUNAR_GAP_FONT_PX`) separates it from the title, no separator glyph, and `<br>` joins one line per holiday so single- and multi-holiday days share one presentation — hairline month headers with count pills, and a rich summary («N روز تعطیل در سال YYYY | M مورد در جمعه») riding its own bordered chip in the field colour — bare text on the window's flat fill had nothing to read against; its numbers borrow the accent through `legible_on()` (the raw dark accent is a button fill at ~2.5:1 on the chip's own `INPUT_BG_COLOR` fill, the ground the digits actually print on). The caption bar IS the header row: its far edge carries the year stepper (❯ / combo / ❮, older year on the right like the calendar's month arrows), and no in-content headline repeats the window name (the window is titled by the taskbar/Alt-Tab native title and the tray menu row). Only the current year carries `past` state, but `next` can live in a later year: `_find_next_holiday()` searches the cache from today onward, so a spent (or data-less) current year opens the viewer on the year holding the nearest upcoming holiday (`_populate_years()`; nothing upcoming anywhere opens on "now"). The nearest holiday is tinted and tagged «امروز» / «فردا» / «پس‌فردا» / «N روز دیگر» — calendar units like «۱ ماه و ۴ روز دیگر» come from `describe_date_distance()` via `format_countdown()` — and is auto-scrolled onto its month header: `_scroll_to_next` activates the layout and lands on the header's month name, skipping the hairline band (the header's own top margin), rather than a fixed row offset that leaves the previous month's tail above the line. Every upcoming row of the current year carries its countdown as a muted chip (`QLabel#RowTag`, border-grey background / grey text), with only the nearest's tag the filled accent pill; past rows carry no tag and other years tag only their nearest — past rows dim, other years render plainly. A `MONTH_GAP_ABOVE_LINE_PX` spacer above each month's hairline keeps the previous month's last row off the line. Rows share the manager's scroll-chrome speech (the rail hanging out at the glass in an 8px padding band with an 8px gutter inside it, the `SCROLL_BOTTOM_PAD_PX` pair); the scrolling viewport itself is opaque in `BACKGROUND_COLOR`, because a transparent viewport repaints the translucent glass beneath every scrolled row and the moving rows ghost across the window. The empty-year path clears `_summary` too, so a stale summary cannot survive a switch to a year with no data
- `ThemeGalleryWindow`: the theme gallery — the real calendar preview beside the theme picker. The caption bar carries the segmented filter (همه / روشن / تاریک / ★) at its reading end — `PANEL_WIDTH`, as wide as the panel it sits above, with the segments sharing the leftover width equally on every resize (a forced stage widens every stop instead of pocketing air at the mirror end) — and no painted title (the native window title covers the taskbar/Alt-Tab); the left column is the preview and nothing else (`_CalendarShotView` painting one of `CalendarShotRenderer`'s whole-window renders — the actual `PersianCalendarWidget` re-styled into the previewed palette at its own 305×395, so the preview is pixel-for-pixel the tray's popup with the user's month, holidays and events, never a redrawn lookalike) with the «اعمال» button under it; the picker runs the window's full height and lists one mini-calendar card per theme (`ThemeCardDelegate` over the shared `gallery_widgets` art: the calendar abstracted to its silhouette with the theme's name inside the card, wrapped to two balanced lines when long), with a favorite star badge straddling the card corner. The window's own chrome (painted background, caption bar, picker, apply button) stays dressed in the session's baseline theme via `_chrome_palette` + `_painted_palette()` over `BaseFramelessWindow`'s hook and a `_dressed_as()` context manager that swaps the class-level `current_palette` for styling passes — only the calendar panel repaints into the previewed theme, so its colors are judged against a constant stage. Previews follow the click only (hover paints a thin affordance frame, never a preview); the clicked card carries a solid accent frame, the session's baseline a quiet dashed one, both contrast-checked against the stable stage (`frame_accent_color`). «اعمال» commits through the controller (`on_commit`) and re-baselines IN the window (the stage re-dresses, the revert target moves) while the gallery stays open for more browsing; closing without it (✕, Esc) reverts via `on_cancel`. Reopens must not reset: nothing rebuilds at `showEvent` (the catalog and filter cannot change while hidden and a rebuild would scroll the picker away), the grid's current selection is restored with the viewport held (`_PickerGrid.hold_viewport` suppressing the scroll-to-current-item Qt does for every programmatic selection), a pending pick survives minimize only under the active filter (`_ensure_preview_listed` re-derives the first listed card and re-reports `on_preview` when a filter flip or reopen excludes it, so the controller's memory cannot disagree with the panel; an empty favorites grid leaves the selection absent), and `_load_favorites()` re-reads the stars in place (the delegate shares the set). The picker is deliberately calm: one card row per wheel notch (sub-notch touchpad deltas accumulate in `_wheel_remainder`), and while the grid mirrors RTL with the window (cards read right-to-left), its rail stays at the window's right edge: `_PickerGrid` carries a rail of its own — the stock bar force-hidden but kept live (wheel and keyboard still drive it), a child `QScrollBar` synced to its range/page-step/value, `setViewportMargins` reserving the strip once and persistently (rail + gutter — the 8px air the pre-mirror bar kept in front of itself; the mirrored wrap refuses a cell landing exactly on the boundary, so the four-card line carries its remainder at the line's far end, off the rail's side) so the cards never reflow when the rail hides on a non-scrolling list. The divider's flanks are deliberately asymmetric - the calendar column keeps its 16px rhythm, the picker's side is 6px (`DIVIDER_GRID_GAP_PX`) - and `WINDOW_WIDTH` (911) sits exactly on the four-card floor (viewport 529 for 528px of cells + the 1px the strict-inside wrap demands), so the dead band before the cards levels with the rail side's (15px art-rect gap on each side). Favorites persist the moment a star is toggled (bookmarks, not part of the apply/cancel session); unstarring under the favorites filter keeps the card until the filter next changes, so a mis-click is takeable-back
- `TutorialWindow`: first-run guide with welcome.gif (500×365)

### `src/ui/widgets/`
- `CalendarDayCell` (`ClickableLabel`): day cell with `clicked`/`add_event_requested`/`remove_event_requested`/`distance_requested` plus the per-event `edit_event_requested_specific`/`remove_event_requested_specific` (a day with several events gets one row per event, each carrying the event's key), custom tooltip (the shared hover delay, cursor-position truth check), context menu (re-syncs host hover via `normalize_day_hover`); every add/edit/remove/distance row closes the menu and defers its signal through the shared `_emit_after_menu_close(menu, signal, *args)` (a modal must not surface while the menu still holds its grab). Its rows are painted by `CenteredTextMenu` (Qt's own arrow subcontrols are zeroed out in the shared stylesheet, leaving the painted triangle — tucked toward the row's leading edge — as the only submenu indicator; every caption centers on its row's content rect so the column reads as one evenly centered set, and the leading item pad is that arrow's own wider column (26px against the 16px trailing one, mirrored in the painter for LTR) which keeps even a row-filling title like «ویرایش رویداد» ~14px clear of the arrow — QMenu sizes every row to its widest caption, so no padding hands the widest caption slack and a wider gutter is the only way a flush caption's arrow gap can grow; leaf rows keep the same anchor, so their ink uniformly shares the one-centered rhythm; the per-event «ویرایش/حذف رویداد» submenus hairline-separate their rows like the copy submenu; glyphs clip to the content rect, which once sheared «وی» off when a tighter tune still rationed them). Add and edit are separate rows — a date with events keeps a blank «افزودن رویداد» beside the edit/delete rows rather than one row that relabels itself and opens a prefilled editor — and a per-event label is folded onto one line, because a raw multi-line `text` (a merged event) blows the menu out sideways
- `Tooltip` (`CustomTooltip`): singleton tooltip bypassing Qt6 native rendering (border-radius fix on Windows). A widget that wants that tooltip for its own `setToolTip` mixes in `HoverTooltipMixin` (public, like the other mixins) or uses `TooltipButton`/`TooltipLabel`: the text is stored instead of handed to Qt - so `toolTip()` stays empty and the text becomes the widget's accessible description - and shows after `TOOLTIP_DELAY_MS` once the cursor is still inside and the widget is visible. That delay is one module constant both the mixin and `CalendarDayCell` arm their own timers with, so the grid and the event manager cannot drift apart. A tooltip says what it *means* through `TOOLTIP_TONE` (`neutral` / `danger` / `success`), which resolves through `TOOLTIP_TONES` to a palette colour for the border and the text; an unknown tone falls back to neutral, so a typo cannot render an unstyled box, and a toned colour is then floored through `legible_on()` at that tone's `TONE_MIN_CONTRAST` - the success tone is 12px bold, normal text, so it takes 4.5:1 rather than the large-text 3:1 the raw accent lands at. `COPIED_TEXT` is the one copy confirmation: the calendar's «کپی تاریخ» row morphs into it and `flash_copied()` shows it wherever a copy happened - one look (`copied_pill_ground()`'s soft accent wash fill - the menu frame owns the pill's chrome inside the menu, while the floating flash frames itself in the floored accent border, because wash alone reads only where a container defines the shape) and one checkmark side: the pill text leads with LRM (`\u200e`, a strong LTR bidi mark - the paragraph's first-strong auto-detection would otherwise follow «ک» and shove a leading neutral checkmark to the far right in every environment; an inline `<span dir="ltr">` measures as a no-op in Qt rich text, and a widget-level pin cannot reach the label's paragraph base) while the copied row pins its painter LTR. Dismissal is owner-scoped (`hide_if_owned_by`), because one shared window cannot let a widget going away cut short a «کپی شد» flash it does not own; `cancel_pending_tooltip()` is what hosts call when a hover breaks without an enter/leave pair (a wheel scroll). `CalendarDayCell` keeps its own copy of the pattern - it also answers a context menu - so the two are deliberately not one class
- `EventInput` (`EventInputWidget`): RTL event editor overlay with recurrence combo (plain, `fit_combo_width`, modes already used on the date dimmed via `set_disabled_recurrences` — a date holds at most one event per mode), auto-delete checkbox, `DateSelectorRow` (the shared year/month/day picking row — months numbered «۰۶ - شهریور» like the converter and go-to-date; build, day refill, picked-date reading and the year-range clamping/red border live on the row widget; field metrics are class knobs (`FIELD_HEIGHT_PX` / `YEAR_WIDTH_PX` / `ROW_LABEL_SIZE_PX` / `ROW_LABEL_BOLD`, compact editor defaults); the editor composes it twice over by keeping the picker widgets under its own historical attribute names, and layers the recurrence answers on top: the key-dropped dimensions are greyed out and a recurring year falls back to today at save), year-range clamping (1200–1600) + red border hint. The dimmed rows stay listed (the mode is a choice the date has spent, not a hidden one) and the combo never sits on one: both `set_data` and `set_disabled_recurrences` push the selection to the first usable mode, because the add path prefills «بدون تکرار» and that is row 0. The module also owns `recurrence_label` and `delete_confirmation_message(keys)` — the delete ask built from the KEYS the answer removes (a recurring key is asked about as its whole series, a date-level delete counts the day's key set), so the calendar's in-calendar card and the event manager's dialog cannot word it differently
- `GoToDate` (`GoToDateWindow`): jump-to-month widget (Persian year 1200–1600, custom rounded bg)
- `Checkbox` (`CustomCheckbox`, `IconCheckboxActionWidget`): FontAwesome-icon checkboxes
- `ConfirmDialog` (`ConfirmDialog`): themed dialog — `ask` (yes/no), `choose` (three-way), `notify` (single button, optional `detail` line); used by update popup + all confirm flows; draggable, button-fit auto-width, and it inherits `HoverDriverMixin` so a dialog surfaced right after tray interaction (the update popup from a silent auto-check) has live hover before any click. `notify(..., key=...)` opts a notice into single-instance replacement: a newer result of the same key re-words the notice already on screen instead of stacking a second window (the update round uses `UPDATE_CHECK_NOTICE_KEY`)
- `ConfirmCard` (`ConfirmCard` / `ConfirmOverlay`): the shared card half of both surfaces — badge, title, message, detail box, buttons, painting. A **plain mixin**, not a widget base, so one card serves a `QDialog` and a `QWidget` child without giving either two QWidget branches; it sets `WA_TranslucentBackground` and delegates finishing to `_finish_choice()` (accept/reject on the dialog, hide on the overlay). `ConfirmOverlay` is persistent and fixed-*shape* (notice = 1 button, ask = 2), not fixed-content: the delete card raises its description line per question (`set_message`) and keeps the preview box for the event text alone, mirroring the event manager's dialog. Every overlay's `chosen` must be connected by the calendar - an overlay only hides itself, so an unconnected one leaves the dimmer up over a card that is already gone
- `DownloadDialog` (`DownloadUpdateDialog`): themed installer-download progress card (determinate/busy, Persian digit counters, cancel signal wired to `UpdateChecker.cancel_download`; carries the hover driver like every other frameless surface)
- `OverlayBlocker` (`overlay_blocker.py`): the one dimming child behind any in-window overlay — the calendar's confirm surfaces and the manager's event editor both size it to their host on `present()` and raise the card above it; the hosts keep teardown in their own `hideEvent`. It must keep its `WA_StyledBackground` opt-in: a named `QWidget` subclass gets no implicit stylesheet background (the exact-`QWidget` literal it replaced did), so without the attribute the scrim shows, blocks clicks and paints nothing — `tests/test_overlay_blocker.py` pins the painted pixels, not just visibility
- `MenuWidgets` (`HoverWidget`, `MenuActionWidget`): custom tray-menu action widgets with hover states; `CenteredTextMenu`'s chrome strings live once here (`centered_menu_stylesheet()`) and the day menu's submenus attach through `attach_centered_submenu()`, which pins the shared stylesheet and the parent's direction
- `ThemeShot` (`theme_shot.py`) + `GalleryWidgets` (`gallery_widgets.py`): the theme gallery's shared halves — `CalendarShotRenderer` keeps one hidden, polished `PersianCalendarWidget` and re-renders it whole per requested theme (palette swap + `update_styles`, ~10 ms a theme; hidden-render == shown-window pixels is pinned by tests); `gallery_widgets.py` owns the filter catalog (`filtered_catalog` dark/light/favorites), `SegmentedFilter` (one connected control with a sliding highlight; the host's width is the stage and every resize re-shares the leftover equally over the segments, so a forced stage widens every stop instead of pocketing air at the mirror end), the favorite star geometry, and `theme_card_pixmap` (the mini-calendar silhouette card)

### `src/utils/`
- `date_utils.py`: `to_persian_digits()`, `from_persian_digits()`, month/weekday name helpers, leap-year + days-in-month for both calendars, `validate_year_range()` (the converter's completed two-calendar sentences) plus `year_range_hint()` — the one short range template the year pickers share (event editor + go-to-date; the converter's Jalali max reads `APP_CONFIG.SUPPORTED_MAX_YEAR`, its min stays 1 by design so the converter stays open to years the calendar UI never shows), and the date-distance layer — `DateDistance` (frozen dataclass: `years`/`months`/`days` + signed `total_days`, with `is_today` and `has_calendar_units` derived - the latter False exactly when the breakdown would restate the total; both formatters are undefined for today and every caller branches on `is_today` first), `describe_date_distance()`, `format_distance_total()`, `format_distance_breakdown()`, `distance_status_word()` (the «مانده/گذشته» word any distance renderer needs), plus the Gregorian twin `describe_gregorian_distance()` (one shared walk, `_describe_distance`, with each calendar's clamping shifts) and the direction-free `format_distance_units()` / `format_distance_total_months()` / `format_distance_weeks()` (fixed 7-day conversion) with `DateDistance.has_month_total` / `has_full_weeks`, which the distance window reads. `year_range_hint(..., persian_digits=False)` words the range for Gregorian surfaces. The decomposition is largest-unit-first with per-step day clamping, so it is order-dependent and deliberately **not** a fixed conversion of the units into days
- `asset_loader.py`: `verify_assets()`, `load_fonts()`
- `logger.py`: `setup_logging()` — RotatingFileHandler (1MB × 3 backups) + console, millisecond timestamps. `install_qt_message_handler()` mirrors Qt's own diagnostics into that log under `qt.<category>` loggers, drops the benign warnings in `_QT_BENIGN_WARNINGS` by severity (never by text alone), and lets a fatal terminate the process like Qt's default handler
- `native_events.py`: `TimeChangeEventFilter(QAbstractNativeEventFilter)` — handles Windows `WM_TIMECHANGE` (0x001E) as a pure detector (the controller coalesces bursts via `TIME_CHANGE_COALESCE_MS`, so a burst costs one refresh; the raw per-message trace is DEBUG-only) and `WM_SETTINGCHANGE` (0x001A), filtered to the `ImmersiveColorSet` section — which is what lets the app follow the Windows light/dark setting live. The settings-change lParam string is read as a wchar walk capped at 32 chars, so a malformed payload cannot be walked arbitrarily far
- `startup_registry.py`: `StartupRegistry` — autostart `Run`-key access (`read()` / `write()` / `delete()`) plus `RUN_KEY_PATH`. The controller's autostart policy goes through this seam so tests can drive it against an in-memory backend
- `windows_theme.py`: `WindowsThemeBackend` — the winreg reads behind the 'system' theme verdict (`AppsUseLightTheme`, CurrentUser personalization key) and the tray's taskbar ground (`taskbar_uses_light()` over `SystemUsesLightTheme`, the shell mode; a missing shell value falls back to the app value, then dark/False). Off-Windows and a failed read both degrade to dark; the module guards `import winreg` by platform exactly like the read it owns
- `ui_helpers.py`: `create_tray_pixmap()` (DPI-aware), `paint_rounded_card()` + `FramelessDragMixin` (shared frameless drag AND mouse-event routing, with `drag_strip_height` / `drag_bottom_keep_visible` knobs), `HoverDriverMixin` (the tray-click hover repair: per-open bounded poll that cross-checks Qt's button state against Windows, feeds synthetic moves through Qt's mouse pipeline and converges to a stop; hosts arm it by just being shown), `YearRangeValidationMixin` (shared red-border year validation), `combo_stylesheet()` + button/line-edit/scrollbar stylesheets (`global_scrollbar_stylesheet()`, `nav_button_stylesheet()`; `scrollbar_stylesheet(palette, bottom_margin=…)`), `plain_menu_stylesheet()` (the stock-QMenu popup frame the tray menu and the go-to-date popup share, optional divider clause included), `rgba_string()` (the one rgba() builder for stylesheet text; `channel_max` names the alpha notation each stylesheet was tuned with — the calendar's classic 0-255 integers, the holiday viewer's CSS 0-1 floats), `contrast_ratio()`/`legible_on()`/`mix_colors()` (WCAG contrast legibility: a colour nudged until it clears 3:1 on its ground — the distance hero and the viewer's summary numbers borrow the accent through `legible_on()`, because the raw dark accent is ~2:1 on the ground), `on_accent_text_color()` + `palette_on_accent_text()` (the one on-accent label rule: white stays while it clears the tuned 2.4:1 floor — `_ON_ACCENT_MIN_RATIO`, deliberately under the WCAG large-text 3:1 because the labels are big bold captions and 3.0 handed every pastel accent to the near-black — mid-tone accents keep their brand-canonical white, and only the highlighter yellow/lime/mint accents flip to `ON_ACCENT_DARK_CANDIDATE` `#16161a`; a separate dial from `legible_on()`'s 3:1; every surface that paints text ON the accent decides through it — accent buttons, the today pill, combo/line-edit/QTextEdit selections, the calendar switch's checked half, the viewer's next tag, the gallery's action dock, the confirm card's badge), `accent_button_stylesheet()` (the accent-fill button recipe with label polarity and light-accent hover/press direction + a `radius` knob), `copied_pill_ground()` (the one wash behind «✓ کپی شد»: the background blended toward the accent at the copy menu's own tuned fraction `COPIED_WASH_ALPHA`, shared by the morphed row and the floating flash), `fit_combo_width()` (styled combos measure their width against the QSS font, not the default one), `set_popup_pixel_scroll()` (the one scroll-mode pin every styled combo calls at setup: Qt clamps the popup against the screen edge and can cap it to a fractional row count, and the default per-item scrollbar aligns its end position to whole rows, rendering the leftover fraction as a blank band under the last item — the sweet-spot artifact seen in the converter near the screen bottom; pixel scroll clamps to the content instead; `test_every_styled_combo_popup_scrolls_per_pixel` sweeps every surface so a new styled-combo site that skips it fails the suite), `ReservedRailScrollArea` (the event manager's and viewer's list host: the rail column is reserved `ScrollBarAlwaysOn` so the viewport can never reflow by the rail's width when content crosses the scrollability threshold — the twitch seen when a list rebuilds around first paint — while the rail's *paint* follows the scrollbar's range via `rangeChanged`, empty until proven otherwise so a never-scrollable list shows nothing and the per-widget transparent sheet covers the groove fill **and** the handle (an empty range draws the handle across the whole track, so a groove-only override still leaves a full-length pill)), and `SCROLL_BOTTOM_PAD_PX` — one value owning a scrolled list's two bottom insets (content pad + track margin), so the thumb ends level with the last card at max scroll (the event manager's and viewer's row columns both take it)
- `json_settings.py`: `JsonSettings` — QSettings-compatible API over `settings.json` (atomic writes, corrupt-file tolerance); a failed write keeps its keys dirty, so re-setting the same value retries the disk write instead of hitting the equal-value early return
- `settings_migration.py`: `migrate_from_registry()` — one-time, idempotent (via `Migration/RegistryMigratedToJSON`) registry → JSON
- `event_io.py`: `load_user_events()`/`save_user_events()` (versioned v2 store), recurrence-key model (`make_event_key`/`parse_event_key`/`recurrence_of_key`: one-time `YYYY-MM-DD`, yearly `0000-MM-DD`, monthly `0000-00-DD`), `normalize_*` (legacy v1 migration + canonical key validation; load counts and logs same-date key collisions, last write wins, and a clean load re-arms saves), `export_events_to_file()`/`import_events_from_file()` (native file dialogs), import reconciliation (`keys_share_visible_date()`, `build_import_plan()` — the visible-date collision model the EventService uses; entries the store already holds exactly (same canonical key + normalized entry, one normalizer on both sides) land in the plan's `unchanged` field - the fold divides the whole file first (a date's later entry wins), so re-importing an exported file is a zero-work plan that never asks, a store-identical entry folds same-date strays that came before it instead of losing its own copy, and the same text under a different key shape stays a confirmed replace), and `is_expired_one_time()` — the expired-one-time rule stated once: the manager's rows and the next-occurrence sort read the verdict, `clean_expired_keys()` layers the store's auto-delete flag on top; `truncate_preview()` is the one 40-character event-text preview form shared by every themed card that quotes an entry (delete confirm, merge ask, import collision detail); `ask_is_stale()` states the ask-window rule once — an ask re-checks the facts it was shown against the live store before acting, the calendar snapshots a date's key-to-text subjects, the manager the whole store, and each surface keeps its own recovery (drop-or-re-ask vs refuse-and-keep-editor)
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

Every booted `SystemTrayIcon` is disposed between tests by the autouse
`dispose_tray_controllers` fixture: pytest-qt and scheduled callbacks would
otherwise hold every controller (and its pending timers) alive for the whole
run, and a stray timer that fires inside a later test's event loop — one whose
modal work re-enters a foreign dispatch — is what access-violated long runs.
No deferral may use the static `QTimer.singleShot`: it keeps its callback (and
whatever the callback captures) alive past its owner's death and then fires
inside a later event loop. Every deferral — day-menu emission, tray-menu and
go-to-date openers, the viewer's auto-scroll, the prewarm, the update popup —
is a receiver-aware child `QTimer` that dies with its widget. A deferral's
safety is its sender's lifetime: the slot is a bound method of that owner
(receiver-tied — PyQt decomposes a bound-method connection and lets it die
with the receiver, while a plain callable stays pinned by the sender's
connection for the sender's lifetime) and any payload rides the owner, not
the timer.

Test modules (in `tests/`): every module of the app has a dedicated file —
persistence/settings: `json_settings`, `settings_migration`, `event_io`,
`holiday_io`, `event_service`; core: `update_checker` (pure helpers + full
networking over a local HTTP server: check round-trips, streaming installer
download, sha256 verification, cancel, truncated transfers), `app_controller`
(update-flow orchestration, retry logic, tray rendering/tooltips, timers,
theme & startup settings, window lifecycle); UI: `config`,
`ui_helpers` (drag mixin, rounded card, pixmaps, stylesheet builders),
`logger`, `asset_loader`, `native_events`, `windows_theme`, `tooltip`, `window_chrome`,
`checkbox`, `download_dialog`, `go_to_date`, `calendar_day_cell`,
`base_window`, `tutorial_window`, `calendar_window`, `event_input`,
`date_distance_window`, `main`, `theme_gallery` (the registry, the on-accent
solver, the card art, the gallery window and its controller wiring); plus the
app-wide suite — `clock`, `calendar_model`, `converter_window`,
`new_windows` (manager, viewer, converter
and calendar widgets; the import/export dialog flows), `boot_smoke`. (`test_dates` covers the date/calendar
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
- [ ] First-open hover with zero clicks: calendar day cells, nav buttons and themed dialog (Confirm/Download) buttons all react
- [ ] Right-click day → add/edit/delete event (recurrence, auto-delete)
- [ ] Copy a date from a day menu: the copied row morphs to «✓ کپی شد» (accent pill, other rows greyed), the menus hold ~450 ms then close — no tooltip anywhere
- [ ] Tray context menu → Date Converter works both ways
- [ ] «تم‌ها» opens the gallery; previewing a card repaints only the gallery's panel, «اعمال» applies app-wide and stays open, closing without it reverts; stars persist across restart
- [ ] Autostart toggle writes/removes registry `Run` key (via app, not installer)
- [ ] Baseline: fresh machine → settings.json + holidays.json seeded in `%LOCALAPPDATA%\ShamsiTray`
- [ ] Upgrade path: 1.3.1 → current (registry→JSON migration fires; holiday store seeds)
- [ ] Update check: manual «بررسی بروزرسانی» works; event manager import/export works
- [ ] Event manager rows: hover the edit/delete glyphs → themed tooltip (never a square black box) and the row's border lights up; the delete one is red; scroll a long list while hovering → the tooltip goes with the row it belonged to
- [ ] Open the event manager and the holiday viewer with a short list: no rail groove, and the rows do not flinch sideways at first paint; grow the list → the groove appears in the reserved column without the column ever moving
- [ ] Holiday viewer: badge rows with weekday badges (red on Fridays) and lunar sub-lines; the next upcoming holiday is tinted, tagged and auto-scrolled into view, past rows dimmed; at max scroll the thumb ends level with the last row
- [ ] Replace/merge ask with a long event title: the preview box is fully visible the moment the dialog opens (125% scale), no grow-on-drag, no `setGeometry` warning
- [ ] Day menu on a date with events: «ویرایش رویداد» / «حذف رویداد» titles render every glyph and clear the tucked arrow; «کپی تاریخ» keeps its tuned spacing
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
- Current work in progress: `feature/roadmap-hardening` and `feature/themes` (the theme gallery) — both v1.4, unmerged
- **Atomic commits**: one logical change per commit — a fix or feature lands with its tests in the same commit, and any `AGENTS.md`/docs the change makes true ride along with it instead of arriving as a separate `docs:` commit. Every commit leaves the tree in a passing state, so history stays bisectable and revert-friendly.
- Commit subjects follow Conventional Commits and are always scoped: `type(scope): imperative summary` — lowercase, no trailing period, at most 72 characters, English only (name a UI label by what it is, e.g. "Convert button", not by its text)
  - Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style` (`style` is only for purely mechanical diffs; those go in `.git-blame-ignore-revs`)
  - Scopes name the feature area, not the layer: `events`, `calendar`, `converter`, `holidays`, `tray`, `update`, `dialog`, `theme`, `ui` (shared widgets and helpers), `dates`, `settings`, `logging`, `installer`; tooling uses `build`, `deps`, `assets`, `release`; docs use `agents`, `readme`, `comments`; a repo-wide change (suite-wide tests, mechanical formatting) uses `app`
  - Bodies are optional: a few lines on what and why (about six at most, wrapped at 72), no file lists, test inventories or change narration
- `.git-blame-ignore-revs` lists purely mechanical commits so `git blame` skips them (enable locally with `git config blame.ignoreRevsFile .git-blame-ignore-revs`; GitHub reads it automatically). Add a commit only if its whole diff is mechanical, and re-check the hashes after any history rewrite
- Commit bodies state what changed and why in app terms — never local paths or private-project/provenance references
- Use branches for experiments/features: `git switch -c feature/<name>`
- Never copy folders for versions (historical `v0.x`/`v1.x` folders were folded into history)
- The abandoned xNightStar calendar experiment (forked at `v0.1.3`) is preserved on the `archive/experiment-xnightstar` tag
- `assets/images/LogoEvolution/` is git-ignored design work; `build/` configs are tracked
- Installers are never committed: they live in the git-ignored `output/` folder and are attached to GitHub releases