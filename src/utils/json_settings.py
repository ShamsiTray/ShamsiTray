"""
JSON Settings Store
-------------------

A minimal drop-in replacement for ``QSettings`` backed by a single JSON file
under %LOCALAPPDATA%\\ShamsiTray. It supports the subset of the QSettings API
this application uses (``value`` / ``setValue`` / ``sync``), keeps the same
"Section/Key" string keys, and writes atomically (temp file + os.replace) so a
crash mid-write can never corrupt the store.

A missing file (a first run) degrades to an empty store silently; an
unreadable one is kept aside under the first unused ``<name>.corrupt`` and
reported through ``recovery_backup``, because rebuilding defaults silently
would lose every choice the user made. The move falls back to copying the bytes
when the rename is refused (a file another process holds open), so the bytes
survive either way; when neither path preserves them the store turns read-only
for the session rather than write over the only copy left. Write failures are
logged and leave the in-memory state intact, but are not treated as success: a
value whose write failed stays marked dirty, so setting the SAME value again
retries the disk write instead of hitting the equal-value early return and
silently never persisting.
"""
import json
import logging
import os
import shutil
from typing import Any, Optional, Set

from config import APP_CONFIG

logger = logging.getLogger(__name__)

# How many free names the copy fallback may try. A name claimed between the scan
# and the exclusive open costs one attempt; the rest is slack, and running out is
# reported rather than retried forever.
_MAX_COPY_ATTEMPTS = 3


def _copy_bytes(src: os.PathLike, dst: os.PathLike) -> None:
    """Copy ``src`` onto ``dst`` byte for byte, refusing to overwrite ``dst``.

    The recovery's fallback path, split out as its own seam so a test can make
    both it and the rename fail without a filesystem that refuses everything.
    """
    with open(src, "rb") as source, open(dst, "xb") as target:
        shutil.copyfileobj(source, target)


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
        # Name of the file an unreadable store was kept in, or None when the
        # load was clean (a first run included). The caller reports it: losing
        # preferences is a user-visible reset, not a silent rebuild.
        self.recovery_backup: Optional[str] = None
        # Set when that recovery could not preserve the bytes at all. The
        # unreadable file is then the only copy of them, and writing this store
        # over it is the one thing that would still destroy them.
        self._read_only = False
        self._load()

    @property
    def read_only(self) -> bool:
        """Whether the store refuses writes for the rest of the session.

        True only when an unreadable store could not be preserved at all: the
        file is then the sole copy of its bytes, so every write is refused. The
        caller surfaces it, because the failure is otherwise silent - a
        preference looks saved and is gone at exit.
        """
        return self._read_only

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
        # returning early would leave the value only in memory, and a restart
        # would silently bring the old value back.
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
            # A genuine first run: there is nothing to recover and nothing to
            # report.
            return
        except (OSError, ValueError) as e:
            # ValueError covers JSONDecodeError and UnicodeDecodeError alike: a
            # file that is not valid UTF-8 is no more readable than bad JSON, so
            # both start from an empty store instead of raising out of __init__.
            self._recover_unreadable(f"not readable: {e}")
            return
        if isinstance(data, dict):
            self._data = data
            return
        self._recover_unreadable(f"unexpected root type: {type(data).__name__}")

    def _recover_unreadable(self, reason: str):
        """Set an unreadable store aside and start from defaults, reporting it.

        A bad file is not a first run: silently rebuilding defaults would throw
        away every preference the user chose, and the bytes that explain the
        failure with it. The file lands on the first unused ``<name>.corrupt`` -
        never on the copy an earlier recovery left, which is the only remaining
        record of the preferences from before it - and the name is left in
        ``recovery_backup`` for the caller to surface. When the bytes cannot be
        preserved at all the store stays where it is, reports its own name and
        turns read-only, because a later write is then the one thing that could
        still replace the only copy of them.
        """
        backup = self._preserve_bytes()
        if backup is not None:
            self.recovery_backup = backup.name
            logger.error(f"Settings file {reason}; kept as {backup.name}, starting empty.")
            return
        # Left in place: an unreadable store is still better kept than deleted,
        # and the next launch reads it again.
        self.recovery_backup = self._path.name
        self._read_only = True
        logger.error(f"Settings file {reason}; it could not be kept aside, starting empty "
                     f"and not writing to it again this session.")

    def _unused_backup_path(self) -> os.PathLike:
        """The first ``<name>.corrupt`` that is still free.

        A second corruption must not land on the first one's copy: that file
        holds the preferences from before the first reset, and nothing else
        does.
        """
        backup = self._path.with_suffix(self._path.suffix + ".corrupt")
        if not backup.exists():
            return backup
        # Numbered suffixes side by side, so repeated recoveries accumulate
        # instead of trading one unreadable file for another.
        index = 1
        while True:
            candidate = self._path.with_suffix(f"{self._path.suffix}.corrupt.{index}")
            if not candidate.exists():
                return candidate
            index += 1

    def _preserve_bytes(self) -> Optional[os.PathLike]:
        """Preserve the unreadable store; the name it went to, or None if it failed.

        ``os.replace`` is the primary path - a crash cannot leave it half-moved.
        Windows refuses the rename while another process holds the file open,
        though, and that is the case that matters: the store starts empty and
        the very next write (the tutorial flag, or the registry migration) would
        replace the unreadable original with defaults and take the bytes with
        it. A copy keeps them and needs nothing but read access plus a new file,
        so it succeeds exactly when the rename fails while writing in general
        still works.

        The copy creates its destination exclusively, so a name claimed between
        the name scan and the open costs a retry rather than the bytes - a
        collision is not a reason to give up on preserving them.
        """
        backup = self._unused_backup_path()
        try:
            os.replace(self._path, backup)
            return backup
        except OSError as e:
            logger.warning(f"Settings file could not be moved aside ({e}); copying it instead.")
        for _ in range(_MAX_COPY_ATTEMPTS):
            backup = self._unused_backup_path()
            try:
                _copy_bytes(self._path, backup)
                return backup
            except FileExistsError:
                continue  # the name went to someone else; take the next one
            except OSError as e:
                logger.error(f"Settings file could not be copied aside either ({e}).")
                return None
        logger.error("Settings file could not be copied aside: no free backup name.")
        return None

    def _flush(self) -> bool:
        """Write the store atomically; True only when the file now matches memory."""
        if self._read_only:
            # The unreadable file is the only copy of its bytes left, so nothing
            # may be written over it - not even a temp file beside it.
            logger.error("Settings store is read-only (its unreadable file could not be "
                         "kept aside); settings are not saved to disk this session.")
            return False
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
