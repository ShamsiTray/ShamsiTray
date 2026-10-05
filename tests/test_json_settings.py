import json
import logging
import os

from utils.json_settings import JsonSettings


def test_missing_file_returns_defaults(tmp_path):
    s = JsonSettings(tmp_path / "settings.json")
    assert s.value("General/OpenAtLogin", False, type=bool) is False
    assert s.value("Missing/Key") is None


def test_set_get_roundtrip_persists_to_disk(tmp_path):
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    s.setValue("Appearance/ThemeChoice", "dark")
    s.setValue("General/OpenAtLogin", True)

    fresh = JsonSettings(p)
    assert fresh.value("Appearance/ThemeChoice") == "dark"
    assert fresh.value("General/OpenAtLogin", False, type=bool) is True


def test_bool_coercion_from_string(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"Tutorial/HasShown": "true"}), encoding="utf-8")
    s = JsonSettings(p)
    assert s.value("Tutorial/HasShown", False, type=bool) is True


def test_corrupt_file_starts_empty_and_warns(tmp_path, caplog):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        s = JsonSettings(p)
    assert s.value("anything") is None
    assert any("unreadable" in r.message for r in caplog.records)


def test_invalid_utf8_file_starts_empty_and_warns(tmp_path, caplog):
    """A file that is not valid UTF-8 is unreadable in exactly the way bad JSON
    is; it used to raise out of the constructor and take startup with it."""
    p = tmp_path / "settings.json"
    p.write_bytes(b"\xff\xfe{")
    with caplog.at_level(logging.ERROR):
        s = JsonSettings(p)
    assert s.value("anything", "dflt") == "dflt"
    assert any("unreadable" in r.message for r in caplog.records)


def test_non_dict_root_starts_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2]", encoding="utf-8")
    s = JsonSettings(p)
    assert s.value("x") is None


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    s.setValue("A/B", 1)
    assert p.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_failure_keeps_in_memory_state(tmp_path, monkeypatch, caplog):
    p = tmp_path / "settings.json"
    s = JsonSettings(p)

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with caplog.at_level(logging.ERROR):
        s.setValue("A/B", 5)
    assert s.value("A/B") == 5
    assert any("Failed to persist settings" in r.message for r in caplog.records)


def test_setvalue_with_same_value_does_not_rewrite(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    s.setValue("A/B", 1)
    calls = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: calls.append(1) or real_replace(a, b))
    s.setValue("A/B", 1)
    assert calls == []


# --- failed writes must stay retryable -----------------------------------------


def test_same_value_after_failed_write_is_retried_and_persisted(tmp_path, monkeypatch):
    """The failure sequence that matters: a write fails, the value lives only
    in memory, the filesystem recovers, the SAME value is set again - and the
    write must actually happen this time instead of being swallowed by the
    equal-value early return."""
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    real_replace = os.replace  # captured before any monkeypatching

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    s.setValue("Updates/LastCheckMs", 12345)          # write fails -> dirty
    assert s.value("Updates/LastCheckMs") == 12345    # in-memory state live
    assert not p.exists()                             # disk still stale

    # Restore the real os.replace for the retry.
    monkeypatch.setattr(os, "replace", real_replace)
    s.setValue("Updates/LastCheckMs", 12345)          # same value: must RETRY
    assert p.exists(), "a dirty same-value setValue must hit the disk again"
    fresh = JsonSettings(p)
    assert fresh.value("Updates/LastCheckMs", 0, type=int) == 12345
    # The dirty bookkeeping cleared: another same-value write is skipped again.
    calls = []
    monkeypatch.setattr(os, "replace", lambda a, b: calls.append(1) or real_replace(a, b))
    s.setValue("Updates/LastCheckMs", 12345)
    assert calls == []


def test_dirty_key_is_healed_by_a_successful_write_of_any_key(tmp_path, monkeypatch):
    """One flush rewrites the WHOLE file, so a later success clears every
    pending dirty key, not just its own."""
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    s.setValue("A/B", 1)
    real_replace = os.replace

    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("disk full")))
    s.setValue("A/B", 2)      # fails -> dirty
    assert s._dirty

    monkeypatch.setattr(os, "replace", real_replace)
    s.setValue("C/D", 3)      # different key, write succeeds
    assert not s._dirty
    fresh = JsonSettings(p)
    assert fresh.value("A/B") == 2 and fresh.value("C/D") == 3


def test_sync_retries_a_failed_flush(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    s = JsonSettings(p)
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("disk full")))
    s.setValue("A/B", 7)
    assert not p.exists()
    monkeypatch.setattr(os, "replace", real_replace)
    s.sync()
    assert JsonSettings(p).value("A/B") == 7
