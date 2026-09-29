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
