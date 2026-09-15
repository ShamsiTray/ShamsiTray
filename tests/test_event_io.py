import json
import logging

import pytest

from config import APP_CONFIG
from utils import event_io


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    p = tmp_path / "user_events.json"
    monkeypatch.setattr(APP_CONFIG, "USER_EVENTS_FILE_PATH", p)
    return p


def test_load_missing_file_returns_empty(store_path):
    assert event_io.load_user_events() == {}


def test_save_load_roundtrip(store_path):
    events = {
        "0000-03-21": {"text": "Nowruz", "recurrence": "yearly", "remove_after_finish": False},
        "1405-05-05": {"text": "one-off", "recurrence": "none", "remove_after_finish": True},
    }
    assert event_io.save_user_events(events)
    assert event_io.load_user_events() == events


def test_save_writes_versioned_store(store_path):
    events = {"1405-05-05": {"text": "one-off", "recurrence": "none", "remove_after_finish": True}}
    assert event_io.save_user_events(events)
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["version"] == event_io.EVENTS_STORE_VERSION
    assert raw["events"] == events


def test_load_v1_store_auto_migrates_yearly_flag(store_path):
    """A legacy bare-mapping store loads fine and is rewritten as v2 on save."""
    store_path.write_text(json.dumps({
        "0000-03-21": {"text": "Nowruz", "yearly": True, "remove_after_finish": False},
        "1405-05-05": "plain one-off",
    }), encoding="utf-8")
    events = event_io.load_user_events()
    assert events["0000-03-21"] == {"text": "Nowruz", "recurrence": "yearly", "remove_after_finish": False}
    assert events["1405-05-05"] == {"text": "plain one-off", "recurrence": "none", "remove_after_finish": False}
    # Next save upgrades the on-disk format to the versioned envelope.
    assert event_io.save_user_events(events)
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["version"] == event_io.EVENTS_STORE_VERSION


def test_recurring_events_never_auto_delete():
    entry = event_io.normalize_event_entry({"text": "anniversary", "yearly": True, "remove_after_finish": True})
    assert entry["recurrence"] == "yearly"
    assert entry["remove_after_finish"] is False


def test_load_corrupt_file_returns_empty(store_path, caplog):
    store_path.write_text("{bad json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert event_io.load_user_events() == {}
    assert any("unreadable" in r.message for r in caplog.records)


def test_load_skips_malformed_entries_and_migrates_strings(store_path):
    store_path.write_text(json.dumps({
        "1403-01-01": {"text": "ok"},
        "broken": {"no_text": True},
        "legacy": "plain string event",
        "junk": 42,
    }), encoding="utf-8")
    events = event_io.load_user_events()
    assert set(events) == {"1403-01-01", "legacy"}
    assert events["legacy"] == {"text": "plain string event", "recurrence": "none", "remove_after_finish": False}


def test_normalize_rejects_empty_text():
    assert event_io.normalize_event_entry({"text": "   "}) is None
    assert event_io.normalize_event_entry(42) is None
    assert event_io.normalize_event_entry("ok") is not None


def test_normalize_coerces_unknown_recurrence_to_none():
    entry = event_io.normalize_event_entry({"text": "x", "recurrence": "weekly"})
    assert entry["recurrence"] == "none"


def test_save_failure_reports_false(store_path, monkeypatch):
    import os

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    assert event_io.save_user_events({"k": {"text": "x"}}) is False


def test_export_import_roundtrip(tmp_path):
    events = {"1403-05-05": {"text": "meeting", "recurrence": "none", "remove_after_finish": True}}
    out = tmp_path / "export.json"
    assert event_io.export_events_to_file(events, out)
    imported, skipped = event_io.import_events_from_file(out)
    assert imported == events
    assert skipped == 0


def test_import_counts_malformed_entries(tmp_path):
    p = tmp_path / "import.json"
    p.write_text(json.dumps({
        "a": {"text": "x"},
        "b": 123,
        "c": None,
    }), encoding="utf-8")
    result = event_io.import_events_from_file(p)
    assert result is not None
    imported, skipped = result
    assert imported == {"a": {"text": "x", "recurrence": "none", "remove_after_finish": False}}
    assert skipped == 2


def test_import_unreadable_or_invalid_root_returns_none(tmp_path):
    assert event_io.import_events_from_file(tmp_path / "missing.json") is None
    p = tmp_path / "list.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert event_io.import_events_from_file(p) is None


def test_save_empty_allowed_after_trusted_empty_load(store_path):
    assert event_io.load_user_events() == {}
    assert event_io.save_user_events({}) is True


def test_save_empty_refused_after_unreadable_load(store_path, caplog):
    store_path.write_text("{bad json", encoding="utf-8")
    with caplog.at_level(logging.CRITICAL):
        assert event_io.load_user_events() == {}
        assert event_io.save_user_events({}) is False
    assert any("Refusing to persist" in r.message for r in caplog.records)
    assert store_path.read_text(encoding="utf-8") == "{bad json"


def test_save_empty_refused_after_foreign_format_load(store_path):
    # A v2 envelope whose payload yields zero trusted events must not be
    # bulldozed with an empty save.
    store_path.write_text(json.dumps({"version": 2, "events": [1, 2]}), encoding="utf-8")
    assert event_io.load_user_events() == {}
    assert event_io.save_user_events({}) is False
    assert json.loads(store_path.read_text(encoding="utf-8"))["version"] == 2


def test_save_nonempty_allowed_even_after_untrusted_load(store_path):
    store_path.write_text("{bad json", encoding="utf-8")
    event_io.load_user_events()
    assert event_io.save_user_events({"k": {"text": "x", "recurrence": "none", "remove_after_finish": False}}) is True
    assert event_io.load_user_events()["k"]["text"] == "x"
