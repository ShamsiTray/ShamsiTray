"""
User Event I/O
--------------

Persistence for user events as a JSON file under %LOCALAPPDATA%\\ShamsiTray,
plus import/export helpers used by the tray menu and the event manager.

Store format (versioned)
========================
Version 2 (current)::

    {"version": 2, "events": {"<key>": {"text": ..., "recurrence": ...,
                                        "remove_after_finish": ...}}}

Event keys encode the recurrence so a single mapping stays the runtime model:

- ``YYYY-MM-DD``  one-time event on that Jalali date
- ``0000-MM-DD``  yearly recurring event (repeats every year on month/day)
- ``0000-00-DD``  monthly recurring event (repeats every month on day DD)

Version 1 files were a bare ``{key: entry}`` mapping with a ``yearly`` bool
per entry; string entries predate that. ``load_user_events`` /
``normalize_events_mapping`` accept all three shapes, so old stores and old
export files migrate automatically and are rewritten in v2 on the next save.

All entry parsing is fault-isolated: one malformed entry is skipped with a
logged warning and never takes down the whole event set. Save failures are
reported to the caller and logged; the in-memory state stays valid.

There is at most one event per calendar date: saving an event for a date
replaces whichever event previously matched that date (see
``keys_matching_date``).

The last load is tracked as trusted/untrusted: an unreadable store or one
with malformed entries is never bulldozed with an empty save (see
``save_user_events``).
"""
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

import jdatetime

from config import APP_CONFIG

logger = logging.getLogger(__name__)

# --- Store format versioning -----------------------------------------------
EVENTS_STORE_VERSION = 2

# Recurrence modes (stored on every entry; "none" means a one-time event).
RECURRENCE_NONE = "none"
RECURRENCE_MONTHLY = "monthly"
RECURRENCE_YEARLY = "yearly"
RECURRENCE_MODES = (RECURRENCE_NONE, RECURRENCE_MONTHLY, RECURRENCE_YEARLY)

# Key sentinels: "0000" marks an unanchored year (yearly), "00" an
# unanchored month (monthly).
_YEARLY_YEAR_SENTINEL = "0000"
_MONTHLY_MONTH_SENTINEL = "00"

_LAST_LOAD_TRUSTED = True


def make_event_key(jdate: jdatetime.date, recurrence: str = RECURRENCE_NONE) -> str:
    """Build the store key for an event on ``jdate`` with the given recurrence."""
    if recurrence == RECURRENCE_YEARLY:
        return jdate.strftime(f"{_YEARLY_YEAR_SENTINEL}-%m-%d")
    if recurrence == RECURRENCE_MONTHLY:
        return f"{_YEARLY_YEAR_SENTINEL}-{_MONTHLY_MONTH_SENTINEL}-{jdate.day:02d}"
    return jdate.strftime("%Y-%m-%d")


def parse_event_key(key: str) -> Optional[Tuple[Optional[int], Optional[int], int]]:
    """Parse an event key into (year, month, day).

    ``None`` marks the wildcard dimension: ``"1404-05-05"`` -> ``(1404, 5, 5)``,
    ``"0000-05-05"`` -> ``(None, 5, 5)`` (yearly), ``"0000-00-05"`` ->
    ``(None, None, 5)`` (monthly). Returns None for unparseable keys.
    """
    parts = str(key).split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(p) for p in parts)
    except (ValueError, TypeError):
        return None
    if not 1 <= day <= 31:
        return None
    year = None if year == 0 else year
    month = None if month == 0 else month
    if year is not None and not 1 <= year <= 9999:
        return None
    if month is not None and not 1 <= month <= 12:
        return None
    return year, month, day


def key_matches_date(key: str, jdate: jdatetime.date) -> bool:
    """True when the event stored under ``key`` occurs on Jalali date ``jdate``."""
    parsed = parse_event_key(key)
    if parsed is None:
        return False
    year, month, day = parsed
    if year is not None and year != jdate.year:
        return False
    if month is not None and month != jdate.month:
        return False
    return day == jdate.day


def keys_matching_date(events: Dict[str, dict], jdate: jdatetime.date) -> List[str]:
    """All stored keys whose event occurs on ``jdate`` (at most one per mode)."""
    return [key for key in events if key_matches_date(key, jdate)]


def events_for_date(events: Dict[str, dict], jdate: jdatetime.date) -> Optional[Tuple[str, dict]]:
    """The event shown for ``jdate``, as (key, entry).

    Priority when several recurrence modes collide on one date: the specific
    one-time event wins, then the yearly, then the monthly one.
    """
    matches = keys_matching_date(events, jdate)
    if not matches:
        return None

    def rank(key: str) -> int:
        parsed = parse_event_key(key)
        if parsed is None:
            return 3
        year, month, _day = parsed
        if year is not None:
            return 0  # specific one-time
        if month is not None:
            return 1  # yearly
        return 2      # monthly

    best = min(matches, key=rank)
    return best, events[best]


def next_occurrence_jdate(key: str, today: Optional[jdatetime.date] = None) -> Optional[jdatetime.date]:
    """The next Jalali date on which the event under ``key`` occurs.

    One-time events return their stored date even if it is in the past.
    Yearly/monthly events roll forward to the next occurrence strictly
    today-or-later; day numbers that do not exist in a target month clamp
    down to that month's last day (e.g. monthly day 31 -> 30 in a 30-day
    month).
    """
    parsed = parse_event_key(key)
    if parsed is None:
        return None
    year, month, day = parsed
    today = today or jdatetime.date.today()

    if year is not None:
        try:
            return jdatetime.date(year, month, day)
        except ValueError:
            return None

    if month is not None:  # yearly
        candidate_year = today.year
        if (month, day) < (today.month, today.day):
            candidate_year += 1
        day = min(day, _days_in_jalali_month_safe(candidate_year, month))
        try:
            return jdatetime.date(candidate_year, month, day)
        except ValueError:
            return None

    # monthly: day ``day`` of the current month if not passed yet, else next month
    year_i, month_i = today.year, today.month
    if day < today.day:
        month_i += 1
        if month_i > 12:
            month_i = 1
            year_i += 1
    safe_day = min(day, _days_in_jalali_month_safe(year_i, month_i))
    try:
        return jdatetime.date(year_i, month_i, safe_day)
    except ValueError:
        return None


def _days_in_jalali_month_safe(year: int, month: int) -> int:
    """Days in a Jalali month without range checks (returns 29 on bad input)."""
    from utils.date_utils import days_in_jalali_month

    try:
        return days_in_jalali_month(year, month)
    except (ValueError, TypeError):
        return 29


def events_sorted_by_next_occurrence(events: Dict[str, dict],
                                     today: Optional[jdatetime.date] = None) -> List[str]:
    """Event keys ordered by their next occurrence (soonest first).

    Upcoming events come first; past one-time events (and unparseable keys)
    sort to the end, grouped after everything that can still fire. Used by
    the event manager window so the list reads as "what fires next".
    """
    today = today or jdatetime.date.today()

    def sort_key(key: str):
        next_date = next_occurrence_jdate(key, today)
        if next_date is None:
            return (2, float("inf"), key)
        is_past_one_time = next_date < today
        # Upcoming events first (ordered by date), then past/expired, then junk.
        group = 1 if is_past_one_time else 0
        return (group, next_date.toordinal(), key)

    return sorted(events, key=sort_key)


# --- Entry normalization ----------------------------------------------------

def normalize_recurrence(value, legacy_yearly: bool = False) -> str:
    """Coerce a stored recurrence value to a valid mode.

    Invalid values fall back to ``"none"`` (or ``"yearly"`` when the legacy
    ``yearly`` flag says so) rather than dropping the user's event.
    """
    if value in RECURRENCE_MODES:
        return value
    if legacy_yearly:
        return RECURRENCE_YEARLY
    if value is not None:
        logger.warning(f"Unknown recurrence {value!r}; treating the event as one-time.")
    return RECURRENCE_NONE


def normalize_event_entry(value) -> Optional[dict]:
    """Coerce a stored/imported entry into the canonical v2 dict form, or None if unusable.

    Accepted shapes:
    - plain string (oldest form) -> one-time event
    - v1 dict: text/yearly/remove_after_finish
    - v2 dict: text/recurrence/remove_after_finish (unknown recurrence falls
      back to the legacy ``yearly`` flag, then to ``"none"``)

    The ``remove_after_finish`` invariant is enforced here: recurring events
    can never auto-delete, so the flag is forced off for them.
    """
    if isinstance(value, str):
        return {"text": value, "recurrence": RECURRENCE_NONE, "remove_after_finish": False}
    if isinstance(value, dict):
        text = value.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        legacy_yearly = bool(value.get("yearly", False))
        recurrence = normalize_recurrence(value.get("recurrence"), legacy_yearly)
        remove_after_finish = bool(value.get("remove_after_finish", False))
        if recurrence != RECURRENCE_NONE:
            remove_after_finish = False
        return {
            "text": text,
            "recurrence": recurrence,
            "remove_after_finish": remove_after_finish,
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


def _parse_store_payload(raw) -> Tuple[Dict[str, dict], int]:
    """Split a loaded JSON payload into (events, skipped) for both store versions."""
    if isinstance(raw, dict) and isinstance(raw.get("events"), dict):
        # v2 versioned envelope.
        return normalize_events_mapping(raw.get("events"))
    # v1 / legacy bare mapping.
    return normalize_events_mapping(raw)


# --- File I/O ----------------------------------------------------------------

def _write_events(path, events: Dict[str, dict]) -> bool:
    """Atomically write events as versioned JSON; returns success."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": EVENTS_STORE_VERSION, "events": events},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as e:
        logger.error(f"Failed to write events file {path}: {e}")
        return False


def load_user_events() -> Dict[str, dict]:
    """Load and normalize user events from the store; {} when missing or corrupt.

    Also records how trustworthy the load was: a missing or clean file is
    trusted; an unreadable one, or one with malformed entries skipped, is not
    (so ``save_user_events`` refuses to bulldoze it with an empty set).
    """
    global _LAST_LOAD_TRUSTED
    try:
        with open(APP_CONFIG.USER_EVENTS_FILE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        _LAST_LOAD_TRUSTED = True
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Events file unreadable, starting with an empty event set: {e}")
        _LAST_LOAD_TRUSTED = False
        return {}
    events, skipped = _parse_store_payload(raw)
    if skipped:
        logger.warning(f"Loaded user events with {skipped} malformed entr{'y' if skipped == 1 else 'ies'} skipped.")
        _LAST_LOAD_TRUSTED = False
    return events


def save_user_events(events: Dict[str, dict]) -> bool:
    """Persist user events atomically in the versioned format; returns success.

    Refuses to write an empty set when the last load was untrusted (foreign
    format, unreadable, or malformed entries skipped) so an unreadable store
    is never bulldozed with {}.
    """
    global _LAST_LOAD_TRUSTED
    if not events and not _LAST_LOAD_TRUSTED:
        logger.critical("Refusing to persist an empty event set after an untrusted load; events file left untouched.")
        return False
    if not APP_CONFIG.ensure_user_data_dirs():
        logger.error("User data directory unavailable; events not persisted.")
        return False
    ok = _write_events(APP_CONFIG.USER_EVENTS_FILE_PATH, events)
    if ok:
        logger.info(f"Saved {len(events)} user events (store v{EVENTS_STORE_VERSION}).")
    return ok


def export_events_to_file(events: Dict[str, dict], path) -> bool:
    """Write a copy of the current events to an arbitrary path (tray-menu export).

    Exports use the current versioned format; imports still accept legacy
    files so events can round-trip through older app versions.
    """
    return _write_events(path, events)


def import_events_from_file(path) -> Optional[Tuple[Dict[str, dict], int]]:
    """Read events from an arbitrary path with per-entry fault isolation.

    Accepts both the versioned v2 envelope and legacy bare-mapping files.
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
    return _parse_store_payload(raw)


def clean_expired_keys(events: Dict[str, dict],
                       today: Optional[jdatetime.date] = None) -> List[str]:
    """Keys of expired auto-delete events inside ``events`` (not mutated).

    Only one-time events with ``remove_after_finish`` whose date is strictly
    before ``today`` expire; recurring events never auto-delete.
    """
    today = today or jdatetime.date.today()
    expired: List[str] = []
    for key, entry in events.items():
        if entry.get("recurrence", RECURRENCE_NONE) != RECURRENCE_NONE:
            continue
        if not entry.get("remove_after_finish", False):
            continue
        parsed = parse_event_key(key)
        if parsed is None or parsed[0] is None:
            continue
        event_date = next_occurrence_jdate(key, today=today)
        if event_date is not None and event_date < today:
            expired.append(key)
    return expired