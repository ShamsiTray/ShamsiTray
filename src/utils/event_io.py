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
 ``keys_matching_date``). Imports honour the same invariant: ``build_import_plan``
 reconciles imported entries against the store by *visible date* rather than by
 key string, so importing can never silently stack two events on one day.

 The last load is tracked as trusted/untrusted: an unreadable store or one
 with malformed entries is never bulldozed with an empty save (see
 ``save_user_events``). The flag clears again on the first successful save, so
 the protection never outlives the state that triggered it.
"""
import json
import logging
import os
from typing import Dict, List, NamedTuple, Optional, Tuple

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


def recurrence_of_key(key: str) -> str:
    """Recurrence mode implied by a store key (the key model's single owner).

    ``YYYY-MM-DD`` is one-time, ``0000-MM-DD`` yearly, ``0000-00-DD`` monthly;
    unparseable keys read as one-time so callers fail closed.
    """
    parsed = parse_event_key(key)
    if parsed is None:
        return RECURRENCE_NONE
    year, month, _day = parsed
    if year is None and month is None:
        return RECURRENCE_MONTHLY
    if year is None:
        return RECURRENCE_YEARLY
    return RECURRENCE_NONE


def key_matches_date(key: str, jdate: jdatetime.date) -> bool:
    """True when the event stored under ``key`` occurs on Jalali date ``jdate``.

    Recurring keys clamp the same way ``next_occurrence_jdate`` does: an anchor
    day that cannot exist in the target month (monthly day 31 in a 30-day
    month, yearly 30 Esfand in a non-leap year) matches the month's last day
    instead. One-time keys stay exact — they were built from a real date and
    can never be impossible.
    """
    parsed = parse_event_key(key)
    if parsed is None:
        return False
    year, month, day = parsed
    if year is not None and year != jdate.year:
        return False
    if month is not None and month != jdate.month:
        return False
    if day == jdate.day:
        return True
    # Only wildcard-dimension keys may slide to the month's last day; a key
    # with both year and month present is always a real date.
    if year is not None and month is not None:
        return False
    return jdate.day == _days_in_jalali_month_safe(jdate.year, jdate.month) and day > jdate.day


def keys_matching_date(events: Dict[str, dict], jdate: jdatetime.date) -> List[str]:
    """All stored keys whose event occurs on ``jdate`` (at most one per mode)."""
    return [key for key in events if key_matches_date(key, jdate)]


def events_on_date(events: Dict[str, dict], jdate: jdatetime.date) -> List[Tuple[str, dict]]:
    """All stored (key, entry) pairs whose event occurs on ``jdate``.

    The returned list may contain multiple recurrence modes (e.g. one-time and
    monthly) on the same date.
    """
    matches = keys_matching_date(events, jdate)
    result: List[Tuple[str, dict]] = []
    for key in matches:
        entry = events.get(key)
        if entry is not None:
            result.append((key, entry))
    return result


def count_events_on_date(events: Dict[str, dict], jdate: jdatetime.date) -> int:
    """Count of events occurring on ``jdate``."""
    return len(keys_matching_date(events, jdate))


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


def events_for_key(events: Dict[str, dict], key: str) -> Optional[dict]:
    """Return entry for a specific key, or None if missing."""
    return events.get(key) if key else None


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

    Both text shapes are trimmed, and a blank text is not an event in either of
    them — the calendar otherwise shows an unnamed event that nothing can
    display. The ``remove_after_finish`` invariant is enforced here too:
    recurring events can never auto-delete, so the flag is forced off for them.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return {"text": text, "recurrence": RECURRENCE_NONE, "remove_after_finish": False}
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


def normalize_event_key(key) -> Optional[str]:
    """Coerce a stored/imported key into the canonical ``YYYY-MM-DD`` form.

    Accepts the canonical one-time/yearly/monthly shapes, normalizes the legacy
    slash-separated format (``1403/07/07`` -> ``1403-07-07``), pads each
    dimension and validates the date parts: month 00-12 (0 = wildcard), day
    1-31, year 0 (wildcard) or 1-9999. A wildcard month needs a wildcard year
    to mean anything — the only recurring shapes are ``0000-MM-DD`` (yearly)
    and ``0000-00-DD`` (monthly) — while ``1403-00-31`` reached jdatetime as
    ``date(1403, None, 31)`` and raised inside ``next_occurrence_jdate``. A
    fully-specified key must form a real Jalali date. Returns None for anything
    else — an invalid key would otherwise become an event that exists in the
    store but is invisible to the calendar.
    """
    text = str(key).strip().replace("/", "-")
    parts = text.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(p) for p in parts)
    except (ValueError, TypeError):
        return None
    if not 1 <= day <= 31:
        return None
    if month != 0 and not 1 <= month <= 12:
        return None
    if year != 0 and not 1 <= year <= 9999:
        return None
    if year != 0 and month == 0:
        return None
    if year != 0 and month != 0:
        try:
            jdatetime.date(year, month, day)
        except ValueError:
            return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _key_for_recurrence(parsed: Tuple[Optional[int], Optional[int], int],
                        recurrence: str) -> Optional[str]:
    """Rebuild a store key from parsed (year, month, day) for a recurrence.

    The recurrence decides which dimensions become wildcards; dimensions the
    parsed key did not carry (already wildcard) stay None. Returns None when the
    recurrence cannot be encoded — a one-time event needs a full date, so a
    wildcard key can never become one.
    """
    year, month, day = parsed
    if recurrence == RECURRENCE_YEARLY:
        if month is None:
            return None
        return f"{_YEARLY_YEAR_SENTINEL}-{month:02d}-{day:02d}"
    if recurrence == RECURRENCE_MONTHLY:
        if day is None:
            return None
        return f"{_YEARLY_YEAR_SENTINEL}-{_MONTHLY_MONTH_SENTINEL}-{day:02d}"
    if recurrence == RECURRENCE_NONE:
        if year is None or month is None:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def normalize_events_mapping(raw) -> Tuple[Dict[str, dict], int]:
    """Normalize a raw events mapping, skipping malformed entries. Returns (events, skipped).

    Every surviving entry has a canonical, parseable key: unparseable keys (and
    legacy slash formats after normalization) go through ``normalize_event_key``,
    so an event can never exist in the store without the calendar being able to
    see it. When a key and its entry disagree about the recurrence the pair is
    reconciled symmetrically from the entry's declared recurrence: a specific key
    on a recurring entry is re-keyed to the recurrence's wildcard shape (the
    legacy v1 case), and a recurring key on a one-time entry gets the entry
    re-flagged when there is no full date to re-key with. Either way the key
    (what matching uses) and the entry (what expiry uses) encode the same mode.
    """
    if not isinstance(raw, dict):
        return {}, 1 if raw is not None else 0
    events: Dict[str, dict] = {}
    skipped = 0
    for key, value in raw.items():
        entry = normalize_event_entry(value)
        canonical_key = normalize_event_key(key) if entry is not None else None
        if entry is None or canonical_key is None:
            skipped += 1
            logger.warning(f"Skipping malformed user event entry {key!r}.")
            continue
        key_recurrence = recurrence_of_key(canonical_key)
        if key_recurrence != entry["recurrence"]:
            parsed = parse_event_key(canonical_key)
            rekeyed = _key_for_recurrence(parsed, entry["recurrence"]) if parsed else None
            if rekeyed is not None:
                canonical_key = rekeyed
            else:
                # The entry's recurrence cannot be encoded as a key (wildcard
                # key, one-time entry): make the entry agree with the key
                # instead, so expiry never silently diverges from matching.
                entry["recurrence"] = key_recurrence
                if key_recurrence != RECURRENCE_NONE:
                    entry["remove_after_finish"] = False
        events[canonical_key] = entry
    return events, skipped


def _parse_store_payload(raw) -> Tuple[Dict[str, dict], int]:
    """Split a loaded JSON payload into (events, skipped) for both store versions."""
    if isinstance(raw, dict) and isinstance(raw.get("events"), dict):
        return normalize_events_mapping(raw.get("events"))
    return normalize_events_mapping(raw)


# --- File I/O ----------------------------------------------------------------

def _write_events(path, events: Dict[str, dict]) -> bool:
    """Atomically write events as versioned JSON; returns success.

    The ``.tmp`` side file is removed in a ``finally`` so an interrupted write
    (disk full, AV lock) never leaves debris next to the store.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": EVENTS_STORE_VERSION, "events": events},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError) as e:
        # TypeError: a non-JSON-serializable value snuck into the store.
        logger.error(f"Failed to write events file {path}: {e}")
        return False
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


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
    except (OSError, ValueError) as e:
        # ValueError covers JSONDecodeError and UnicodeDecodeError: a store that
        # is not valid UTF-8 is unreadable in the same way, so both fall back to
        # an empty set instead of raising out of startup.
        logger.error(f"Events file unreadable, starting with an empty event set: {e}")
        _LAST_LOAD_TRUSTED = False
        return {}
    events, skipped = _parse_store_payload(raw)
    if skipped:
        logger.warning(f"Loaded user events with {skipped} malformed entr{'y' if skipped == 1 else 'ies'} skipped.")
        _LAST_LOAD_TRUSTED = False
    return events


def last_load_trusted() -> bool:
    """Whether the most recent load can be overwritten safely (introspection hook)."""
    return _LAST_LOAD_TRUSTED


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
        # The on-disk store now mirrors what we were handed, so whatever made
        # the last load untrusted is healed: without this, one corrupt load
        # would block every future empty save forever.
        _LAST_LOAD_TRUSTED = True
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


# --- Import reconciliation (EVT-5) -------------------------------------------
#
# A store holds at most one event per *visible* calendar date, but different
# store keys can land on the same date: a one-time ``1405-08-01`` and a yearly
# ``0000-08-01`` are distinct keys that both fire on 1405/08/01 (and
# ``events_for_date`` then silently picks a winner while the event manager lists
# both). A flat ``dict.update`` would deduplicate exact keys only, so everything
# below reconciles an import the same way the interactive add path does: by
# visible date, not by key string.

# Years sampled for recurring-vs-recurring collision checks: one leap and one
# non-leap Jalali year. Recurring keys carry no year of their own, so every date
# they can ever match is (month, effective day); month lengths are fixed except
# Esfand, which the pair of sample years covers exactly.
_RECURRING_SAMPLE_YEARS = (1403, 1404)


def _recurring_key_matches_one_time_date(recurring_key: str,
                                         one_time_key: str) -> bool:
    """True when ``recurring_key`` fires on the one-time key's own date."""
    parsed = parse_event_key(one_time_key)
    if parsed is None or parsed[0] is None or parsed[1] is None:
        return False
    year, month, day = parsed
    try:
        date = jdatetime.date(year, month, day)
    except ValueError:
        return False
    return key_matches_date(recurring_key, date)


def _recurring_keys_share_date(key_a: str, key_b: str) -> bool:
    """True when two recurring keys fire on at least one common date."""
    for year in _RECURRING_SAMPLE_YEARS:
        for month in range(1, 13):
            for day in range(1, 32):
                try:
                    date = jdatetime.date(year, month, day)
                except ValueError:
                    continue
                if key_matches_date(key_a, date) and key_matches_date(key_b, date):
                    return True
    return False


def keys_share_visible_date(key_a: str, key_b: str) -> bool:
    """True when the two store keys land on at least one common Jalali date.

    Identical keys trivially share every occurrence. One-time keys only ever
    match their own exact date, so a one-time/recurring pair collides exactly
    when the recurring key matches that date (clamping included: yearly
    ``0000-12-30`` collides with one-time Esfand 29 of a non-leap year). Two
    different one-time keys never collide — they are different real dates.
    """
    if key_a == key_b:
        return True
    rec_a, rec_b = recurrence_of_key(key_a), recurrence_of_key(key_b)
    if rec_a == RECURRENCE_NONE and rec_b == RECURRENCE_NONE:
        return False
    if rec_a == RECURRENCE_NONE:
        return _recurring_key_matches_one_time_date(key_b, key_a)
    if rec_b == RECURRENCE_NONE:
        return _recurring_key_matches_one_time_date(key_a, key_b)
    return _recurring_keys_share_date(key_a, key_b)


def dedupe_events_by_visible_date(events: Dict[str, dict]) -> Tuple[Dict[str, dict], int]:
    """Fold an events mapping so no two entries share a visible date.

    Later entries replace earlier ones landing on the same date — the same
    "last write wins" rule ``dict.update`` applies to exact keys, extended to
    same-date cross-representation collisions. Returns (deduped, replaced).
    """
    result: Dict[str, dict] = {}
    replaced = 0
    for key, entry in events.items():
        shadowed = [k for k in result if keys_share_visible_date(k, key)]
        for old_key in shadowed:
            del result[old_key]
            replaced += 1
        result[key] = entry
    return result, replaced


class ImportPlan(NamedTuple):
    """What applying an import will do to the store, computed BEFORE any
    mutation so the UI can confirm it (EVT-5).

    ``applied``            entries that will enter the store (already folded so
                           no two of them share a visible date; later entries
                           won internal collisions)
    ``replaced_existing``  existing entries that will be removed because an
                           imported event takes over their date (exact-key
                           overwrites and same-date collisions alike)
    ``internal_replaced``  import-internal same-date duplicates folded into
                           ``applied`` (later entry won)
    """
    applied: Dict[str, dict]
    replaced_existing: Dict[str, dict]
    internal_replaced: int


def build_import_plan(existing: Dict[str, dict],
                      imported: Dict[str, dict]) -> ImportPlan:
    """Reconcile an import against the current store without mutating either.

    Every entry in ``replaced_existing`` is an event the user currently has that
    would no longer show (or exist) after the import — the exact count the
    confirm dialog promises to replace.
    """
    applied, internal_replaced = dedupe_events_by_visible_date(imported)
    replaced_existing: Dict[str, dict] = {}
    for new_key in applied:
        for existing_key, entry in existing.items():
            if keys_share_visible_date(existing_key, new_key):
                replaced_existing[existing_key] = entry
    return ImportPlan(applied=applied,
                      replaced_existing=replaced_existing,
                      internal_replaced=internal_replaced)


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
