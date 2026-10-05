"""
JSON Settings Store
-------------------

A minimal drop-in replacement for ``QSettings`` backed by a single JSON file
under %LOCALAPPDATA%\\ShamsiTray. It supports the subset of the QSettings API
this application uses (``value`` / ``setValue`` / ``sync``), keeps the same
"Section/Key" string keys, and writes atomically (temp file + os.replace) so a
crash mid-write can never corrupt the store.

A missing or corrupt file degrades to an empty store with a logged warning;
write failures are logged and leave the in-memory state intact - but they are
no longer treated as success: a value whose write failed stays marked dirty, so
setting the SAME value again retries the disk write instead of hitting the
equal-value early return and silently never persisting.
"""
import json
import logging
import os
from typing import Any, Optional, Set

from config import APP_CONFIG

logger = logging.getLogger(__name__)


class JsonSettings:
    """Settings store persisted as a JSON object mapping 'Section/Key' -> value."""

    def __init__(self, file_path: Optional[os.PathLike] = None):
        self._path = file_path if file_path is not None else APP_CONFIG.SETTINGS_FILE_PATH
        self._data: dict = {}
        # Keys whose last setValue could not reach the disk. A failed write
        # leaves the in-memory value live but the file stale; the next
        # successful flush rewrites the WHOLE file, so clearing the whole set
        # on success is correct.
        self._dirty: Set[str] = set()
        self._load()

    # --- QSettings-compatible API ---

    def value(self, key: str, default: Any = None, type: Optional[type] = None) -> Any:
        raw = self._data.get(key, default)
        if type is not None and raw is not None:
            raw = self._coerce(raw, type, key)
        return raw

    def setValue(self, key: str, value: Any):
        if self._data.get(key) == value and not self._dirty:
            return
        # An equal-value write must still be retried while any flush has failed:
        # the early return used to strand the value in memory forever, so a
        # restart silently brought the old value back.
        self._data[key] = value
        if self._flush():
            self._dirty.clear()
        else:
            self._dirty.add(key)

    def sync(self):
        """QSettings API compatibility; writes are already flushed on setValue.

        Also the retry hook for a previously failed flush: the whole file is
        rewritten, so one success heals every dirty key.
        """
        if self._flush():
            self._dirty.clear()

    def contains(self, key: str) -> bool:
        return key in self._data

    # --- internals ---

    @staticmethod
    def _coerce(raw: Any, type_: type, key: str) -> Any:
        try:
            if type_ is bool:
                if isinstance(raw, bool):
                    return raw
                if isinstance(raw, str):
                    return raw.strip().lower() == "true"
                return bool(raw)
            if type_ is int:
                return int(raw)
            if type_ is float:
                return float(raw)
            if type_ is str:
                return str(raw)
        except (TypeError, ValueError):
            logger.warning(f"Could not coerce settings value for {key!r} to {type_.__name__}; using raw value.")
        return raw

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            # ValueError covers JSONDecodeError and UnicodeDecodeError alike: a
            # file that is not valid UTF-8 is no more readable than bad JSON, so
            # both start from an empty store instead of raising out of __init__.
            logger.error(f"Settings file unreadable, starting with an empty store: {e}")
            return
        if isinstance(data, dict):
            self._data = data
        else:
            logger.error(f"Settings file has unexpected root type ({type(data).__name__}); starting empty.")

    def _flush(self) -> bool:
        """Write the store atomically; True only when the file now matches memory."""
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            if not APP_CONFIG.ensure_user_data_dirs():
                logger.error("User data directory unavailable; settings not persisted.")
                return False
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
            return True
        except (OSError, TypeError) as e:
            # OSError: disk/permission trouble. TypeError: a value that cannot
            # be serialized (the app controls its values, so this is a net).
            logger.error(f"Failed to persist settings (in-memory state kept): {e}")
            return False
        finally:
            # An interrupted write must never leave a stale .tmp beside the store.
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
