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
    assert any('falling back' in r.message for r in caplog.records)


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
