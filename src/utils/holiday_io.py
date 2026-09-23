"""
Holiday Store I/O
-----------------

Loading, validation, and resolution for holiday data. The AppData store is the
primary source (seeded from the bundled copy on first run, replaced atomically
by update downloads); the bundled asset is the fallback. Parsing is
fault-isolated per entry so one malformed entry cannot wipe every holiday for
every year.
"""
import json
import logging
import os
import shutil
from typing import Dict, List, Optional, Tuple

from config import APP_CONFIG

logger = logging.getLogger(__name__)


def parse_holidays(raw) -> Tuple[Dict[int, Dict[Tuple[int, int], List[str]]], int]:
    """Parse a raw holidays mapping, skipping malformed entries. Returns (data, skipped)."""
    if not isinstance(raw, dict):
        return {}, 1 if raw is not None else 0
    holidays_data: Dict[int, Dict[Tuple[int, int], List[str]]] = {}
    skipped = 0
    for year_str, events in raw.items():
        try:
            year_int = int(year_str)
        except (ValueError, TypeError):
            skipped += 1
            logger.warning(f"Skipping invalid holiday year key {year_str!r}.")
            continue
        if not isinstance(events, dict):
            skipped += 1
            logger.warning(f"Skipping holiday year {year_str!r}: expected an object of month-day entries, got {type(events).__name__}.")
            continue
        year_holidays: Dict[Tuple[int, int], List[str]] = {}
        for month_day_str, desc in events.items():
            try:
                parts = str(month_day_str).split('-')
                if len(parts) != 2:
                    raise ValueError(f"expected 'MM-DD', got {month_day_str!r}")
                month, day = int(parts[0]), int(parts[1])
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    raise ValueError(f"month/day out of range in {month_day_str!r}")
                if isinstance(desc, str):
                    descriptions = [desc]
                elif isinstance(desc, list) and all(isinstance(d, str) for d in desc):
                    descriptions = desc
                else:
                    raise TypeError(f"description must be a string or a list of strings, got {type(desc).__name__}")
            except (ValueError, TypeError) as e:
                skipped += 1
                logger.warning(f"Skipping invalid holiday entry {year_str!r}/{month_day_str!r}: {e}")
                continue
            year_holidays[(month, day)] = descriptions
        holidays_data[year_int] = year_holidays
    return holidays_data, skipped


def load_holidays_file(path) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
    """Load and parse a holidays file; {} on file-level failure."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load holidays file {path}: {e}")
        return {}
    raw = parsed.get('holidays', {}) if isinstance(parsed, dict) else None
    data, skipped = parse_holidays(raw)
    if skipped:
        logger.warning(
            f"Holidays loaded with {skipped} invalid entr{'y' if skipped == 1 else 'ies'} skipped "
            f"({sum(len(v) for v in data.values())} valid entries kept).")
    return data


def read_version(path) -> int:
    """Read the 'version' field of a holidays file; 0 when missing or unreadable."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.load(f)
        return int(parsed.get('version', 0)) if isinstance(parsed, dict) else 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def read_version_from_payload(payload: bytes) -> int:
    """Read the 'version' field of a downloaded holidays payload; 0 when unusable."""
    try:
        parsed = json.loads(payload.decode('utf-8'))
        return int(parsed.get('version', 0)) if isinstance(parsed, dict) else 0
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return 0


def validate_payload(payload: bytes) -> Optional[Tuple[dict, int]]:
    """Fully validate a downloaded holidays payload BEFORE any version comparison.

    Returns (parsed_root, version) when the payload is JSON, carries a positive
    integer version, and its entries parse to at least one valid entry; None
    otherwise. Comparing versions before this gate let a corrupt or unversioned
    remote (version reads as 0) look exactly like "nothing newer" — an invalid
    payload and a genuinely-old payload must be separate states, and only the
    latter may silently end the check.
    """
    try:
        parsed = json.loads(payload.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Holiday payload is not valid JSON: {e}")
        return None
    if not isinstance(parsed, dict):
        logger.error(f"Holiday payload root is {type(parsed).__name__}, expected an object.")
        return None
    try:
        version = int(parsed.get('version', 0))
    except (TypeError, ValueError):
        logger.error("Holiday payload has a non-numeric 'version' field.")
        return None
    if version <= 0:
        logger.error("Holiday payload is missing a positive 'version' field; refusing to compare or apply it.")
        return None
    data, _skipped = parse_holidays(parsed.get('holidays'))
    # parse_holidays keeps a year key even when every entry under it was
    # skipped, so "any data" must mean at least one surviving (month, day).
    if not any(entries for entries in data.values()):
        logger.error("Holiday payload has no valid entries; refusing to apply it.")
        return None
    return parsed, version


def resolve_holidays_store() -> Dict[int, Dict[Tuple[int, int], List[str]]]:
    """Resolve the holiday data source: the AppData store first, the bundled asset
    as seed (store missing) and fallback (store corrupt/empty).

    A store that exists but yields nothing is repaired from the bundled file, so
    the fallback does not have to re-recover on every single launch.
    """
    store = APP_CONFIG.HOLIDAYS_STORE_PATH
    bundled = APP_CONFIG.HOLIDAYS_FILE_PATH

    if store.exists():
        data = load_holidays_file(store)
        if data:
            return data
        logger.warning("AppData holiday store is empty or unreadable; repairing it from the bundled file.")
        if bundled.exists():
            data = load_holidays_file(bundled)
            if data:
                _repair_store_from_bundled(store, bundled)
                return data
    elif bundled.exists():
        _seed_store_from_bundled(store, bundled)
        data = load_holidays_file(store)
        if data:
            return data

    if bundled.exists():
        data = load_holidays_file(bundled)
        if data:
            return data
    logger.error("No usable holiday data found; continuing without holidays.")
    return {}


def _seed_store_from_bundled(store, bundled) -> None:
    """Copy the bundled holidays file to the AppData store so updates replace one file."""
    try:
        if not APP_CONFIG.ensure_user_data_dirs():
            return
        shutil.copyfile(bundled, store)
        logger.info("Seeded the AppData holiday store from the bundled file.")
    except OSError as e:
        logger.error(f"Could not seed the AppData holiday store: {e}")


def _repair_store_from_bundled(store, bundled) -> None:
    """Replace a corrupt/unreadable AppData store with the bundled data (atomically).

    The corrupt file is renamed to ``holidays.json.bak`` first (best-effort,
    replacing any previous backup): the store being replaced may have been AHEAD
    of the bundled data (updated via a live holiday download) before some
    unrelated disk hiccup corrupted it, and silently regressing the user to older
    data with the evidence destroyed is worse than keeping a backup around. A
    failure here leaves the broken store in place — the caller already has the
    bundled data, so the app still works either way.
    """
    try:
        if not APP_CONFIG.ensure_user_data_dirs():
            return
        backup = store.with_suffix('.json.bak')
        try:
            os.replace(store, backup)
            logger.warning(f"Corrupt holiday store preserved as {backup.name}.")
        except OSError as e:
            logger.error(f"Could not back up the corrupt holiday store: {e}")
        tmp = store.with_suffix('.json.tmp')
        shutil.copyfile(bundled, tmp)
        os.replace(tmp, store)
        logger.info("Repaired the AppData holiday store from the bundled file.")
    except OSError as e:
        logger.error(f"Could not repair the AppData holiday store: {e}")
        # Same debris rule as replace_store: a failed copy/replace must not
        # strand the .tmp side file next to the (still corrupt) store.
        try:
            if tmp.exists():
                tmp.unlink()
        except (OSError, NameError):
            pass


def replace_store(payload: bytes) -> bool:
    """Validate a downloaded holidays payload and atomically replace the AppData store."""
    try:
        parsed = json.loads(payload.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Downloaded holiday payload is not valid JSON: {e}")
        return False
    data, skipped = parse_holidays(parsed.get('holidays') if isinstance(parsed, dict) else None)
    if not data:
        logger.error("Downloaded holiday payload has no valid entries; keeping the current store.")
        return False
    if skipped:
        logger.warning(f"Downloaded holiday payload had {skipped} invalid entr{'y' if skipped == 1 else 'ies'} (still applying).")
    tmp = None
    try:
        if not APP_CONFIG.ensure_user_data_dirs():
            return False
        tmp = APP_CONFIG.HOLIDAYS_STORE_PATH.with_suffix('.json.tmp')
        with open(tmp, 'wb') as f:
            f.write(payload)
        os.replace(tmp, APP_CONFIG.HOLIDAYS_STORE_PATH)
        tmp = None  # renamed into place: nothing left to clean up
        logger.info(f"Holiday store replaced ({sum(len(v) for v in data.values())} entries).")
        return True
    except OSError as e:
        logger.error(f"Failed to write the holiday store: {e}")
        return False
    finally:
        # A failed os.replace (disk full, AV lock) used to strand the .tmp side
        # file next to the store forever; the real store was untouched, but the
        # debris accumulated on every failed update attempt.
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
