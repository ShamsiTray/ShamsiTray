"""
User Event I/O
--------------

Persistence for user events as a JSON file under %LOCALAPPDATA%\\ShamsiTray,
plus import/export helpers used by the tray menu.

All entry parsing is fault-isolated: one malformed entry is skipped with a
logged warning and never takes down the whole event set. Save failures are
reported to the caller and logged; the in-memory state stays valid.
"""
import json
import logging
import os
from typing import Dict, Optional, Tuple

from config import APP_CONFIG

logger = logging.getLogger(__name__)

ENTRY_KEYS = ("text", "yearly", "remove_after_finish")


def normalize_event_entry(value) -> Optional[dict]:
    """Coerce a stored/imported entry into the canonical dict form, or None if unusable.

    Legacy entries were plain strings; current entries are dicts with text/yearly/
    remove_after_finish. Unknown dict shapes are rejected rather than guessed at.
    """
    if isinstance(value, str):
        return {"text": value, "yearly": False, "remove_after_finish": False}
    if isinstance(value, dict):
        text = value.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return {
            "text": text,
            "yearly": bool(value.get("yearly", False)),
            "remove_after_finish": bool(value.get("remove_after_finish", False)),
        }
    return None


def normalize_events_mapping(raw) -> Tuple[Dict[str, dict], int]:
    """Normalize a raw events mapping, skipping malformed entries. Returns (events, skipped)."""
    if not isinstance(raw, dict):
        return {}, 1 if raw is not None else 0
    events: Dict[str, dict] = {}
    skipped = 0
    for key, value in raw.items():
        entry = normalize_event_entry(value)
        if entry is None:
            skipped += 1
            logger.warning(f"Skipping malformed user event entry {key!r}.")
            continue
        events[str(key)] = entry
    return events, skipped


def _write_events(path, events: Dict[str, dict]) -> bool:
    """Atomically write events as JSON; returns success."""
    try:
        if not APP_CONFIG.ensure_user_data_dirs():
            logger.error("User data directory unavailable; events not persisted.")
            return False
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as e:
        logger.error(f"Failed to write events file {path}: {e}")
        return False


def load_user_events() -> Dict[str, dict]:
    """Load and normalize user events from the store; {} when missing or corrupt."""
    try:
        with open(APP_CONFIG.USER_EVENTS_FILE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Events file unreadable, starting with an empty event set: {e}")
        return {}
    events, skipped = normalize_events_mapping(raw)
    if skipped:
        logger.warning(f"Loaded user events with {skipped} malformed entr{'y' if skipped == 1 else 'ies'} skipped.")
    return events


def save_user_events(events: Dict[str, dict]) -> bool:
    """Persist user events atomically; returns success."""
    ok = _write_events(APP_CONFIG.USER_EVENTS_FILE_PATH, events)
    if ok:
        logger.info(f"Saved {len(events)} user events.")
    return ok


def export_events_to_file(events: Dict[str, dict], path) -> bool:
    """Write a copy of the current events to an arbitrary path (tray-menu export)."""
    return _write_events(path, events)


def import_events_from_file(path) -> Optional[Tuple[Dict[str, dict], int]]:
    """Read events from an arbitrary path with per-entry fault isolation.

    Returns (events, skipped_count), or None when the file itself is unreadable
    or is not a JSON object.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read events file {path}: {e}")
        return None
    if not isinstance(raw, dict):
        logger.error(f"Events file {path} has unexpected root type ({type(raw).__name__}).")
        return None
    events, skipped = normalize_events_mapping(raw)
    return events, skipped
