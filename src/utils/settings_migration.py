"""
Settings Migration
------------------

One-time migration of settings and user events from the legacy QSettings
registry store (HKCU\\Software\\ShamsiTray) to the JSON files under
%LOCALAPPDATA%\\ShamsiTray.

The registry keys are deliberately left in place so an upgrade can always be
rolled back to an older app version without data loss.
"""
import logging
from pathlib import Path

from config import APP_CONFIG
from utils.json_settings import JsonSettings

logger = logging.getLogger(__name__)

_MIGRATION_FLAG_KEY = "Migration/RegistryMigratedToJSON"

# Registry-era key the old builds stored the event blob under. Events moved to
# user_events.json, but the string is still needed to READ the legacy blob, so
# it lives here next to its only user instead of in config.py.
LEGACY_USER_EVENTS_SETTING_KEY = "UserData/Events"

_SETTING_KEYS = (
    APP_CONFIG.AUTO_START_SETTING_KEY,
    APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY,
    APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY,
)


def migrate_from_registry(settings: JsonSettings, legacy=None) -> None:
    """Copy legacy registry values into the JSON stores once, then flag completion.

    Idempotent: skipped entirely when the flag is already set. JSON values win if
    both stores hold data (i.e. the app already ran on the new store): a setting
    is only copied when the JSON store does not have that key yet, and the event
    store is only written when it does not exist yet. On failure the flag is not
    set, so the next launch retries. ``legacy`` may be injected (anything with
    ``.value(key)``); it defaults to QSettings.
    """
    if settings.value(_MIGRATION_FLAG_KEY, False, type=bool):
        return

    if legacy is None:
        from PyQt6.QtCore import QSettings
        legacy = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)

    migrated: list = []
    try:
        for key in _SETTING_KEYS:
            value = legacy.value(key)
            # JSON wins: a key already living in the JSON store (the app ran
            # on the new store before, or a partial migration retried) must
            # never be clobbered by the stale registry copy. Presence is what
            # counts, so a key holding an explicit null still wins.
            if value is not None and not settings.contains(key):
                settings.setValue(key, value)
                migrated.append(key)
    except Exception as e:
        logger.error(f"Registry settings migration failed (will retry on next launch): {e}")
        return

    if not _migrate_user_events(legacy):
        logger.error("User events migration failed (will retry on next launch).")
        return

    settings.setValue(_MIGRATION_FLAG_KEY, True)
    if migrated:
        logger.info(f"Migrated {len(migrated)} setting(s) from registry to JSON: {', '.join(migrated)}")
    else:
        logger.info("No legacy registry settings found; migration flag set.")


def _migrate_user_events(legacy) -> bool:
    """Move the legacy registry events blob into the events file. Returns success.

    The migration only ever CREATES the events file: when a JSON store already
    exists it wins and the registry blob is left untouched (the registry is never
    deleted, so the old app version keeps working). Writing the blob over an
    existing store would bulldoze events the user created on the new store.
    """
    import json

    from utils import event_io

    events_path = Path(APP_CONFIG.USER_EVENTS_FILE_PATH)
    if events_path.exists():
        logger.info("A JSON event store already exists; skipping registry event migration (JSON wins).")
        return True

    try:
        raw = legacy.value(LEGACY_USER_EVENTS_SETTING_KEY)
    except Exception as e:
        logger.error(f"Could not read legacy user events: {e}")
        return False
    if raw is None:
        return True
    if isinstance(raw, str):
        # Older builds could store the whole mapping as a serialized string.
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Legacy user events blob is not valid JSON; nothing to migrate.")
            return True

    events, skipped = event_io.normalize_events_mapping(raw)
    if skipped:
        logger.warning(f"Registry user events had {skipped} malformed entr{'y' if skipped == 1 else 'ies'} skipped during migration.")
    if not event_io.save_user_events(events):
        return False
    if events:
        logger.info(f"Migrated {len(events)} user event(s) from registry to JSON.")
    return True
