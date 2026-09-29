import json
import logging

import pytest

from config import APP_CONFIG
from utils import holiday_io


@pytest.fixture
def paths(tmp_path, monkeypatch):
    store = tmp_path / 'holidays_store.json'
    bundled = tmp_path / 'holidays_bundled.json'
    monkeypatch.setattr(APP_CONFIG, 'HOLIDAYS_STORE_PATH', store)
    monkeypatch.setattr(APP_CONFIG, 'HOLIDAYS_FILE_PATH', bundled)
    return store, bundled


def bundled_payload(version=1):
    return {
        'version': version,
        'holidays': {
            '1403': {'1-1': 'Nowruz', 'bad-key': 'x', '13-40': 'y', '2-2': ['a', 'b']},
        },
    }


def test_parse_holidays_isolates_bad_entries():
    data, skipped = holiday_io.parse_holidays(bundled_payload()['holidays'])
    assert data == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    assert skipped == 2


def test_parse_holidays_non_dict_root():
    assert holiday_io.parse_holidays(None) == ({}, 0)
    assert holiday_io.parse_holidays([1]) == ({}, 1)
    assert holiday_io.parse_holidays('x') == ({}, 1)


def test_load_holidays_file_corrupt_returns_empty(paths, caplog):
    store, _ = paths
    store.write_text('{bad', encoding='utf-8')
    with caplog.at_level(logging.ERROR):
        assert holiday_io.load_holidays_file(store) == {}
    assert any('Failed to load holidays file' in r.message for r in caplog.records)


def test_load_holidays_file_invalid_utf8_returns_empty(paths, caplog):
    store, _ = paths
    store.write_bytes(b"\xff\xfe{")
    with caplog.at_level(logging.ERROR):
        assert holiday_io.load_holidays_file(store) == {}
    assert holiday_io.read_version(store) == 0


def test_read_version_variants(paths):
    store, _ = paths
    store.write_text(json.dumps({'version': 3}), encoding='utf-8')
    assert holiday_io.read_version(store) == 3
    store.write_text('[]', encoding='utf-8')
    assert holiday_io.read_version(store) == 0
    assert holiday_io.read_version(store.with_suffix('.missing')) == 0


def test_read_version_from_payload():
    payload = json.dumps({'version': 7, 'holidays': {}}).encode('utf-8')
    assert holiday_io.read_version_from_payload(payload) == 7
    assert holiday_io.read_version_from_payload(b'{bad') == 0
    assert holiday_io.read_version_from_payload(b'[1]') == 0


def test_resolve_seeds_store_from_bundled_when_missing(paths):
    store, bundled = paths
    bundled.write_text(json.dumps(bundled_payload()), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    assert store.exists(), 'store seeded from bundled copy'


def test_resolve_prefers_existing_store(paths):
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=2)), encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data  # parsed from the store, not the older bundled file
    assert holiday_io.read_version(store) == 2


def test_resolve_falls_back_to_bundled_when_store_corrupt(paths, caplog):
    store, bundled = paths
    store.write_text('{corrupt', encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload()), encoding='utf-8')
    with caplog.at_level(logging.WARNING):
        data = holiday_io.resolve_holidays_store()
    assert data == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    assert any('repairing' in r.message for r in caplog.records)
    # HOL-3: the repair actually rewrites the broken store, so the next
    # launch reads the store directly instead of re-falling back forever.
    assert holiday_io.load_holidays_file(store) == data


def test_validate_payload_accepts_only_fully_valid_payloads():
    """HOL-2: version comparison must never see an unvalidated payload."""
    good = json.dumps({"version": 5, "holidays": {"1403": {"01-01": ["Nowruz"]}}}).encode()
    parsed = holiday_io.validate_payload(good)
    assert parsed is not None and parsed[1] == 5
    # Invalid states read as version 0 and previously looked like "nothing newer":
    assert holiday_io.validate_payload(b"{bad json") is None
    assert holiday_io.validate_payload(b"[1,2]") is None
    assert holiday_io.validate_payload(json.dumps({"holidays": {}}).encode()) is None
    assert holiday_io.validate_payload(json.dumps({"version": 0, "holidays": {"1403": {"01-01": "x"}}}).encode()) is None
    assert holiday_io.validate_payload(json.dumps({"version": "abc", "holidays": {}}).encode()) is None
    assert holiday_io.validate_payload(json.dumps({"version": 5, "holidays": {"1403": {"01-01": 42}}}).encode()) is None


def test_resolve_returns_empty_when_nothing_exists(paths, caplog):
    with caplog.at_level(logging.ERROR):
        assert holiday_io.resolve_holidays_store() == {}
    assert any('No usable holiday data' in r.message for r in caplog.records)


def test_replace_store_validates_and_swaps_atomically(paths):
    store, _ = paths
    payload = json.dumps({'version': 5, 'holidays': {'1404': {'1-1': 'X'}}}).encode('utf-8')
    assert holiday_io.replace_store(payload)
    assert holiday_io.read_version(store) == 5
    assert holiday_io.load_holidays_file(store) == {1404: {(1, 1): ['X']}}
    assert list(store.parent.glob('*.tmp')) == []


def test_replace_store_rejects_empty_and_corrupt(paths, caplog):
    store, _ = paths
    assert not holiday_io.replace_store(b'{bad json')
    assert not holiday_io.replace_store(json.dumps({'version': 9, 'holidays': {'x': 'y'}}).encode('utf-8'))
    assert not store.exists()
    assert any('keeping the current store' in r.message for r in caplog.records)


# --- .tmp side-file cleanup (#4) -----------------------------------------------------------


def test_replace_store_cleans_tmp_when_replace_fails(paths, monkeypatch):
    """A failed os.replace (disk full, AV lock) used to strand holidays.json.tmp
    next to the store forever; the debris must be cleaned up."""
    store, _bundled = paths
    payload = json.dumps(bundled_payload(version=2)).encode('utf-8')

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(holiday_io.os, 'replace', failing_replace)
    assert holiday_io.replace_store(payload) is False
    assert not store.with_suffix('.json.tmp').exists()
    assert not store.exists()  # the real store was never touched


def test_repair_store_cleans_tmp_when_replace_fails(paths, monkeypatch):
    """Same debris rule for the self-repair path: a failed swap must not
    leave the .tmp side file behind."""
    store, bundled = paths
    bundled.write_text(json.dumps(bundled_payload(version=2)), encoding='utf-8')

    real_replace = holiday_io.os.replace

    def failing_replace(src, dst):
        if str(dst).endswith('.json.tmp'):
            raise OSError("disk full")
        # the corrupt-store backup rename still works
        real_replace(src, dst)

    monkeypatch.setattr(holiday_io.os, 'replace', failing_replace)
    holiday_io._repair_store_from_bundled(store, bundled)
    assert not store.with_suffix('.json.tmp').exists()

