"""
Event Service (EVT-6)
---------------------

Single owner of the user-event store: the in-memory mapping, every path that
mutates it, and every path that persists it. The controller and the event
manager *request* operations from here and handle only application/UI state
(refreshes, dialogs) — the business rules (which key an edit lands on,
recurrence/expiry semantics, transactional saves) live in one place, so the
store, the calendar and the disk cannot disagree.

Every mutation follows the same shape (EVT-7)::

    snapshot = dict(events)
    mutate events in place
    if not save_user_events(events): restore snapshot in place; fail

The snapshot is restored IN PLACE (``clear()`` + ``update()``) rather than by
rebinding, because the calendar widget holds a live reference to this dict: a
rebinding rollback would restore ``service.events`` while the calendar kept
reading the mutated object.

Persistence failures are reported through ``on_save_error`` (a plain callable
the application points at its themed failure dialog) so this module stays
Qt-free and testable. Interactive mutation paths pass ``notify=True``;
background cleanup passes ``notify=False`` and only logs.
"""
import logging
from typing import Callable, Dict, List, Optional

import jdatetime

from utils.event_io import (
    RECURRENCE_MODES,
    RECURRENCE_NONE,
    ImportPlan,
    build_import_plan,
    clean_expired_keys,
    events_for_date,
    events_sorted_by_next_occurrence,
    keys_matching_date,
    load_user_events,
    make_event_key,
    recurrence_of_key,
    save_user_events,
)

logger = logging.getLogger(__name__)


def _merge_text(existing: str, text: str) -> str:
    """Fold ``text`` into ``existing`` as a new line, never duplicating a line.

    A blank ``existing`` (the target key is gone by the time the merge runs) just
    yields the edited text, so a merge degrades into the plain edit rather than
    writing an empty event.
    """
    incoming = text.strip()
    if not existing:
        return incoming
    if any(line.strip() == incoming for line in existing.splitlines()):
        return existing
    return f"{existing}\n{incoming}"


class EventService:
    """Owns the user-event store and every mutation/persistence path."""

    def __init__(self):
        self.events: Dict[str, dict] = {}
        # UI hook: called (no arguments) when an interactive save fails and the
        # in-memory state was rolled back. The application points this at its
        # themed failure dialog; tests point it at a recorder.
        self.on_save_error: Optional[Callable[[], None]] = None
        self.reload()

    # --- state ------------------------------------------------------------------

    def reload(self) -> None:
        """(Re)load the store from disk.

        The refresh happens IN PLACE (``clear()`` + ``update()``) for the same
        reason the rollback in ``_commit`` does: the calendar widget holds a live
        reference to this dict, so rebinding would leave the calendar reading a
        stale object that nothing ever mutates again.
        """
        loaded = load_user_events()
        self.events.clear()
        self.events.update(loaded)
        logger.info(f"Loaded {len(self.events)} user events.")

    # --- queries (thin delegates; the key model lives in event_io) --------------

    def keys_matching_date(self, jdate: jdatetime.date) -> List[str]:
        return keys_matching_date(self.events, jdate)

    def events_for_date(self, jdate: jdatetime.date):
        return events_for_date(self.events, jdate)

    def events_sorted_by_next_occurrence(self) -> List[str]:
        return events_sorted_by_next_occurrence(self.events)

    def __len__(self) -> int:
        return len(self.events)

    # --- persistence core -------------------------------------------------------

    def _commit(self, snapshot: Dict[str, dict], *, notify: bool = True) -> bool:
        """Persist the store; on failure restore ``snapshot`` in place and fail.

        The save is the ONLY disk write in every mutation path, so a save either
        leaves the complete new state on disk or the previous state — a
        half-applied file can never exist.
        """
        if save_user_events(self.events):
            return True
        logger.error("Failed to persist user events (in-memory state restored).")
        self.events.clear()
        self.events.update(snapshot)
        if notify and self.on_save_error is not None:
            self.on_save_error()
        return False

    # --- mutations --------------------------------------------------------------

    def target_key(self, jdate: jdatetime.date, recurrence: str) -> str:
        """The key an event with ``recurrence`` takes when added on ``jdate``.

        Reusing an existing key of the SAME recurrence keeps a re-added
        recurring event on its own anchor: ``jdate`` can be a clamped occurrence
        — a day-31 monthly event is shown on the 30th, 30 Esfand on the 29th of
        a non-leap year — and re-deriving the key from it would walk the
        event's anchor one step further away on every save.

        Any other recurrence is a different logical event, so it gets its own
        key: a date may carry a one-time and a monthly event at once, which is
        what the calendar's per-event menus exist for.

        Public because the event manager adds through its own editor and must
        reach the same verdict as ``add()`` - a visible-date match there would
        call every event on the date a duplicate.
        """
        anchor = next((key for key in keys_matching_date(self.events, jdate)
                       if recurrence_of_key(key) == recurrence), None)
        return anchor or make_event_key(jdate, recurrence)

    def add(self, jdate: jdatetime.date, text: str, recurrence: str = RECURRENCE_NONE,
            remove_after_finish: bool = False) -> bool:
        """Add the event for ``jdate``, replacing the same-recurrence one if any.

        Keyed, not date-scoped: an existing event of the SAME recurrence is
        replaced (so re-adding is still an edit, never a duplicate), while
        events of other recurrences stay where they are. Recurring events ignore
        the auto-delete flag because they repeat forever.

        Recurrence is validated HERE, not only in the UI: an arbitrary value
        used to fall through key generation as a one-time key while still being
        stored as its own recurrence — a key/entry mismatch.
        """
        if not jdate:
            return False
        if recurrence not in RECURRENCE_MODES:
            logger.warning(f"Unsupported recurrence {recurrence!r}; storing the event as one-time.")
            recurrence = RECURRENCE_NONE
        if not text or not text.strip():
            logger.warning("Ignoring attempt to add a user event with empty text.")
            return False
        snapshot = dict(self.events)
        key = self.target_key(jdate, recurrence)
        if recurrence != RECURRENCE_NONE:
            remove_after_finish = False
        self.events[key] = {
            "text": text,
            "recurrence": recurrence,
            "remove_after_finish": remove_after_finish,
        }
        return self._commit(snapshot)

    def update_key(self, key: str, jdate: jdatetime.date, text: str,
                   recurrence: str = RECURRENCE_NONE, remove_after_finish: bool = False,
                   merge_into: Optional[str] = None) -> bool:
        """Edit the entry stored at ``key``, leaving every other event alone.

        The key-scoped sibling of :meth:`add`, for editing ONE of the events
        visible on a date. ``jdate`` is the occurrence the user was looking at.

        The target key is ``key`` itself while the recurrence is unchanged:
        ``jdate`` can be a clamped occurrence — a day-31 monthly event is shown
        on the 30th, 30 Esfand on the 29th of a non-leap year — and re-deriving
        the key would walk the anchor one step further away on every edit.

        A changed recurrence is a different logical event, so the entry moves to
        that recurrence's key on ``jdate`` and only ``key`` is removed. If that
        target is already occupied the edit is REFUSED rather than overwriting
        whoever lives there: an edit must never silently destroy another event.
        The caller asks the user first and passes ``merge_into`` to go ahead.

        ``merge_into`` folds the edited text into the entry at that key as a new
        line (skipped when the text is already one of its lines) instead of
        replacing it, so merging never loses either event's text.
        """
        if key not in self.events:
            logger.debug(f"Ignoring edit of unknown event key {key!r}.")
            return False
        if not jdate:
            return False
        if not text or not text.strip():
            logger.warning("Ignoring attempt to save a user event with empty text.")
            return False
        if recurrence not in RECURRENCE_MODES:
            logger.warning(f"Unsupported recurrence {recurrence!r}; storing the event as one-time.")
            recurrence = RECURRENCE_NONE
        target_key = merge_into or (
            key if recurrence_of_key(key) == recurrence else make_event_key(jdate, recurrence))
        if merge_into is None and target_key != key and target_key in self.events:
            logger.warning(
                f"Refusing to edit {key!r} onto the occupied key {target_key!r}; "
                "pass merge_into to fold the events together.")
            return False
        snapshot = dict(self.events)
        if merge_into:
            text = _merge_text(self.events.get(merge_into, {}).get("text", ""), text)
        if target_key != key:
            del self.events[key]
        self.events[target_key] = {
            "text": text,
            "recurrence": recurrence,
            "remove_after_finish": remove_after_finish if recurrence == RECURRENCE_NONE else False,
        }
        return self._commit(snapshot)

    def remove_for_date(self, jdate: jdatetime.date, *, commit: bool = True) -> bool:
        """Remove every event variant matching ``jdate`` (specific, yearly, monthly).

        ``commit=False`` mutates in memory only (no save, no rollback).
        """
        if not jdate:
            return False
        matching = keys_matching_date(self.events, jdate)
        if not matching:
            return False
        snapshot = dict(self.events)
        for key in matching:
            del self.events[key]
        if not commit:
            return True
        return self._commit(snapshot)

    def delete_key(self, key: str) -> bool:
        """Delete one store entry by key (the event manager's delete)."""
        if key not in self.events:
            return False
        snapshot = dict(self.events)
        del self.events[key]
        return self._commit(snapshot)

    def upsert(self, key: str, entry: dict, *, replace_keys=()) -> bool:
        """Insert/replace one entry, first removing ``replace_keys``.

        The event manager's add/edit path: ``replace_keys`` carries the old key
        when an edit moved the event onto a new date (already confirmed by the
        caller when the target was occupied).
        """
        snapshot = dict(self.events)
        for old_key in replace_keys:
            self.events.pop(old_key, None)
        self.events[key] = entry
        return self._commit(snapshot)

    def clean_expired(self, *, notify: bool = False) -> List[str]:
        """Drop expired auto-delete events; returns the removed keys.

        Background cleanup (startup / midnight / time-change / minute tick) runs
        with ``notify=False``: a modal firing from a timer is dialog spam.
        """
        expired = clean_expired_keys(self.events)
        if not expired:
            return []
        logger.info(f"Removing {len(expired)} expired events.")
        snapshot = dict(self.events)
        for key in expired:
            del self.events[key]
        if self._commit(snapshot, notify=notify):
            return expired
        return []

    # --- import (EVT-5) ---------------------------------------------------------

    def plan_import(self, imported: Dict[str, dict]) -> ImportPlan:
        """Reconcile an import against the current store, mutating nothing.

        The returned plan carries the exact set of existing events the import
        would replace (exact-key overwrites AND same-date cross-representation
        collisions), so the UI can confirm before anything is applied.
        """
        return build_import_plan(self.events, imported)

    def apply_import(self, plan: ImportPlan) -> bool:
        """Apply a planned import atomically: ONE in-memory computation, ONE save.

        Replaced existing events are removed, the folded import entries are
        added, and expiry cleanup runs — all in memory first; the complete
        resulting state is then persisted exactly once. The old two-write flow
        (cleanup mid-import, then the import's own save) could leave a
        half-imported file on disk when the second write failed.
        """
        snapshot = dict(self.events)
        for key in plan.replaced_existing:
            self.events.pop(key, None)
        self.events.update(plan.applied)
        for key in clean_expired_keys(self.events):
            self.events.pop(key, None)
        return self._commit(snapshot)
