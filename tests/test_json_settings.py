import json
import logging
import os

from utils.json_settings import JsonSettings, _copy_bytes


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
    assert any("unreadable" in r.message or "not readable" in r.message for r in caplog.records)


def test_corrupt_file_is_kept_aside_so_the_reset_can_be_reported(tmp_path):
    """Rebuilding defaults silently would lose every stored preference, so the
    bad file is preserved and its name handed back to the caller."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")

    s = JsonSettings(p)

    assert s.recovery_backup == "settings.json.corrupt"
    assert not p.exists()
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not json"
    # The recovered store is usable and writes a fresh file.
    s.setValue("Appearance/ThemeChoice", "dark")
    assert json.loads(p.read_text(encoding="utf-8")) == {"Appearance/ThemeChoice": "dark"}


def test_invalid_utf8_file_starts_empty_and_warns(tmp_path, caplog):
    """A file that is not valid UTF-8 is unreadable in exactly the way bad JSON
    is; it used to raise out of the constructor and take startup with it."""
    p = tmp_path / "settings.json"
    p.write_bytes(b"\xff\xfe{")
    with caplog.at_level(logging.ERROR):
        s = JsonSettings(p)
    assert s.value("anything", "dflt") == "dflt"
    assert any("unreadable" in r.message or "not readable" in r.message for r in caplog.records)
    assert s.recovery_backup == "settings.json.corrupt"
    assert (tmp_path / "settings.json.corrupt").read_bytes() == b"\xff\xfe{"


def test_unreadable_file_that_cannot_be_set_aside_is_still_reported(tmp_path, monkeypatch):
    """The recovery is still user-visible when neither path works: the store is
    left where it is, its own name is what the caller reports, and the store goes
    read-only - the unreadable file is all that is left of its bytes."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("utils.json_settings.os.replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr("utils.json_settings._copy_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))

    s = JsonSettings(p)

    assert s.recovery_backup == "settings.json"
    assert s.read_only is True
    assert p.exists()          # never deleted to recover from it
    assert s.value("anything") is None


def test_read_only_verdict_is_public(tmp_path, monkeypatch):
    """The verdict belongs to the caller - main() words its startup notice from
    it - so it is read through a public property, not the private flag."""
    p = tmp_path / "settings.json"
    assert JsonSettings(p).read_only is False  # nothing to recover: writes are fine

    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("utils.json_settings.os.replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr("utils.json_settings._copy_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))

    assert JsonSettings(p).read_only is True


def test_read_only_store_never_writes_over_the_unreadable_file(tmp_path, monkeypatch, caplog):
    """Neither path preserved the bytes, so the store holds the only copy left:
    every later write must be refused before any temp file is even created."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr("utils.json_settings._copy_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))

    s = JsonSettings(p)
    with caplog.at_level(logging.ERROR):
        s.setValue("Appearance/ThemeChoice", "dark")
        s.sync()

    assert p.read_text(encoding="utf-8") == "{not json"   # untouched
    assert list(tmp_path.glob("*.tmp")) == []             # not even a temp file
    assert s.value("Appearance/ThemeChoice") == "dark"    # in-memory state kept
    assert s._dirty                                       # and still marked unsaved
    assert any("read-only" in r.message for r in caplog.records), [r.message for r in caplog.records]


def test_copy_retries_the_next_name_when_one_is_taken(tmp_path, monkeypatch):
    """Exclusive creation can lose the name between the scan and the open. That
    must cost a retry, not the bytes - and not a read-only store either."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    real_copy = _copy_bytes
    attempted = []

    def steal_the_first_name(src, dst):
        attempted.append(dst.name)
        if len(attempted) == 1:
            dst.write_text("{someone else", encoding="utf-8")  # the name is gone
            raise FileExistsError(dst)
        real_copy(src, dst)

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr("utils.json_settings._copy_bytes", steal_the_first_name)

    s = JsonSettings(p)

    assert attempted == ["settings.json.corrupt", "settings.json.corrupt.1"]
    assert s.recovery_backup == "settings.json.corrupt.1"
    assert s.read_only is False
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{someone else"
    assert (tmp_path / "settings.json.corrupt.1").read_text(encoding="utf-8") == "{not json"


def test_copy_gives_up_after_the_attempts_are_used_up(tmp_path, monkeypatch):
    """A name that keeps being taken is a failure to preserve, not an infinite
    loop: the store reports itself (never a phantom backup name) and goes
    read-only."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    attempted = []

    def always_taken(src, dst):
        attempted.append(dst.name)
        raise FileExistsError(dst)

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr("utils.json_settings._copy_bytes", always_taken)

    s = JsonSettings(p)

    assert len(attempted) == 3
    assert s.recovery_backup == "settings.json"
    assert s.read_only is True
    assert p.read_text(encoding="utf-8") == "{not json"


def test_move_refusal_still_preserves_the_bytes(tmp_path, monkeypatch):
    """A rename is refused while another process holds the file open, but the
    bytes are still readable - and the store is free to write over the original
    afterwards, which is only safe because the copy exists."""
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    real_replace = os.replace

    def refuse_only_the_recovery(src, dst):
        if src == p:
            raise OSError("held open")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", refuse_only_the_recovery)

    s = JsonSettings(p)

    assert s.recovery_backup == "settings.json.corrupt"
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not json"
    s.setValue("Appearance/ThemeChoice", "dark")
    assert json.loads(p.read_text(encoding="utf-8")) == {"Appearance/ThemeChoice": "dark"}
    # Overwriting the original lost nothing: the bytes live in the backup.
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not json"


def test_second_corruption_does_not_overwrite_the_first_backup(tmp_path):
    """The first ``.corrupt`` file holds the preferences from before the first
    reset - the only copy of them left - so a later corruption must land beside
    it instead of trading one unreadable file for another."""
    p = tmp_path / "settings.json"
    first = tmp_path / "settings.json.corrupt"
    first.write_text("{first corruption", encoding="utf-8")
    p.write_text("{second json", encoding="utf-8")

    s = JsonSettings(p)

    assert s.recovery_backup == "settings.json.corrupt.1"
    assert first.read_text(encoding="utf-8") == "{first corruption"
    assert (tmp_path / "settings.json.corrupt.1").read_text(encoding="utf-8") == "{second json"
    assert not p.exists()


def test_first_run_reports_nothing(tmp_path):
    s = JsonSettings(tmp_path / "settings.json")
    assert s.recovery_backup is None


def test_non_dict_root_starts_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2]", encoding="utf-8")
    s = JsonSettings(p)
    assert s.value("x") is None
    assert s.recovery_backup == "settings.json.corrupt"


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
