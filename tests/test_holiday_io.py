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


def test_parse_holidays_skips_dates_that_do_not_exist():
    """07-31 and 30 Esfand of a non-leap year pass a range check but are not
    real dates: they used to be stored as holidays that never occur."""
    data, skipped = holiday_io.parse_holidays(
        {'1404': {'07-31': 'no such day', '12-30': 'non-leap year', '01-01': 'ok'}})
    assert data == {1404: {(1, 1): ['ok']}}
    assert skipped == 2


def test_parse_holidays_keeps_esfand_30_of_a_leap_year():
    data, skipped = holiday_io.parse_holidays({'1403': {'12-30': 'leap year'}})
    assert skipped == 0
    assert data[1403][(12, 30)] == ['leap year']


def test_bundled_holidays_are_all_real_dates():
    """The shipped file passes the same validation a downloaded one must."""
    raw = json.loads(APP_CONFIG.HOLIDAYS_FILE_PATH.read_text(encoding='utf-8'))['holidays']
    _data, skipped = holiday_io.parse_holidays(raw)
    assert skipped == 0


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
    # The seed must carry the bundled payload, not merely exist: a seed that
    # wrote nothing usable would push every later launch back into the
    # bundled-fallback branch.
    assert holiday_io.load_holidays_file(store) == data
    assert holiday_io.read_version(store) == 1


def test_resolve_prefers_existing_store(paths):
    store, bundled = paths
    # Different MAPPINGS, not just different versions: with both files holding
    # the same holidays, returning the bundled mapping would pass.
    store.write_text(json.dumps(
        {'version': 2, 'holidays': {'1404': {'3-3': 'Store Only'}}}), encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data == {1404: {(3, 3): ['Store Only']}}  # the store's mapping
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


def test_replace_store_failure_keeps_the_previous_store(paths, monkeypatch):
    """The swap is atomic end to end: when the rename cannot land, the store
    that was there before keeps serving - writing straight to the destination
    would have destroyed it the moment the write failed."""
    store, _bundled = paths
    assert holiday_io.replace_store(json.dumps(bundled_payload(version=2)).encode('utf-8'))
    new_payload = json.dumps({'version': 5, 'holidays': {'1404': {'1-1': 'X'}}}).encode('utf-8')

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(holiday_io.os, 'replace', failing_replace)
    assert holiday_io.replace_store(new_payload) is False
    assert holiday_io.read_version(store) == 2  # previous store intact
    assert list(store.parent.glob('*.tmp')) == []  # no debris


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
    leave the .tmp side file behind, and the swap really must fail."""
    store, bundled = paths
    bundled.write_text(json.dumps(bundled_payload(version=2)), encoding='utf-8')
    store.write_text('{corrupt', encoding='utf-8')

    real_replace = holiday_io.os.replace

    def failing_replace(src, dst):
        # The staged .tmp file is the SOURCE of the publish rename - the
        # destination is the store itself, whose name never ends in .tmp - so
        # the guard has to match the source for the failure to happen at all.
        if str(src) == str(store.with_suffix('.json.tmp')):
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(holiday_io.os, 'replace', failing_replace)
    holiday_io._repair_store_from_bundled(store, bundled)
    assert not store.with_suffix('.json.tmp').exists()
    # The publish really failed: the store is still the broken file the repair
    # wanted to replace, and the corrupt evidence was kept as the backup.
    assert holiday_io.load_holidays_file(store) == {}
    assert store.with_suffix('.json.bak').read_text(encoding='utf-8') == '{corrupt'


# --- store upgrade from a newer bundled file ---------------------------------------


def test_resolve_upgrades_a_store_older_than_the_bundled_file(paths):
    """The installer seeds with onlyifdoesntexist, so an upgrade that ships
    newer holiday data never reached an existing install until the GitHub
    update fired - and never at all when GitHub was unreachable."""
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 4, 'holidays': {'1405': {'1-1': 'Fresh'}}}), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data == {1405: {(1, 1): ['Fresh']}}
    assert holiday_io.read_version(store) == 4


def test_resolve_does_not_downgrade_a_store_ahead_of_the_bundled_file(paths):
    store, bundled = paths
    store.write_text(json.dumps(
        {'version': 9, 'holidays': {'1405': {'1-1': 'Live'}}}), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 2, 'holidays': {'1404': {'1-1': 'Old'}}}), encoding='utf-8')
    assert holiday_io.resolve_holidays_store() == {1405: {(1, 1): ['Live']}}
    assert holiday_io.read_version(store) == 9


def test_resolve_upgrade_failure_keeps_serving_the_old_store(paths, monkeypatch, caplog):
    """A swap that cannot land (permissions, AV lock) must not cost the user
    their holidays - the older store still parses."""
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 4, 'holidays': {'1405': {'1-1': 'Fresh'}}}), encoding='utf-8')

    def failing_publish(src, dst):
        # The publish is the rename ONTO the store; the backup rename lands on
        # the .bak file, so this leaves the backup path exercised too.
        if dst == store:
            raise OSError("access denied")
        real_replace(src, dst)

    real_replace = holiday_io.os.replace
    monkeypatch.setattr(holiday_io.os, 'replace', failing_publish)
    with caplog.at_level(logging.WARNING):
        data = holiday_io.resolve_holidays_store()
    assert data == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    assert any('Could not upgrade the AppData holiday store' in r.message
               for r in caplog.records)
    assert not store.with_suffix('.json.tmp').exists()


def test_upgrade_publish_failure_leaves_the_store_on_disk(paths, monkeypatch):
    """The backup must COPY the store, never move it: a publish failure after a
    successful backup used to leave NO store on disk, so the next launch
    silently reseeded it from the bundled file."""
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 4, 'holidays': {'1405': {'1-1': 'Fresh'}}}), encoding='utf-8')
    real_replace = holiday_io.os.replace

    def failing_publish(src, dst):
        if dst == store:
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(holiday_io.os, 'replace', failing_publish)
    holiday_io._upgrade_store_from_bundled(store, bundled)

    assert store.exists()  # still the store the app was serving
    assert holiday_io.read_version(store) == 1
    assert holiday_io.load_holidays_file(store) == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    # ... and the backup taken before the failed publish holds the same data.
    assert holiday_io.load_holidays_file(store.with_suffix('.json.bak')) \
        == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}
    assert list(store.parent.glob('*.tmp')) == []


def test_upgrade_without_a_backup_leaves_the_store_alone(paths, monkeypatch, caplog):
    """When the backup cannot even be taken, nothing may be replaced:
    overwriting the only on-disk copy of data that may be newer than the
    bundled file is the worst outcome this path can produce."""
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 4, 'holidays': {'1405': {'1-1': 'Fresh'}}}), encoding='utf-8')

    def failing_copy2(src, dst):
        raise OSError("access denied")

    monkeypatch.setattr(holiday_io.shutil, 'copy2', failing_copy2)
    with caplog.at_level(logging.ERROR):
        holiday_io._upgrade_store_from_bundled(store, bundled)
    assert any('Could not back up the holiday store' in r.message for r in caplog.records)
    assert holiday_io.read_version(store) == 1  # store untouched
    assert not store.with_suffix('.json.bak').exists()  # no half-written backup
    assert list(store.parent.glob('*.tmp')) == []  # nothing was staged


def test_resolve_repairs_a_store_whose_entries_all_were_skipped(paths):
    """parse_holidays keeps the YEAR key when every entry under it was skipped,
    so {1405: {}} is truthy with zero usable holidays - it must not count as a
    working store and block the bundled fallback forever."""
    store, bundled = paths
    store.write_text(json.dumps(
        {'version': 3, 'holidays': {'1405': {'99-99': 'nonsense'}}}), encoding='utf-8')
    bundled.write_text(json.dumps(
        {'version': 3, 'holidays': {'1405': {'1-1': 'Nowruz'}}}), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data == {1405: {(1, 1): ['Nowruz']}}


def test_resolve_unversioned_store_is_upgraded_from_versioned_bundled(paths):
    """An unversioned store reads as version 0, so a versioned bundled file
    wins - a seeded store missing its version field cannot block upgrades."""
    store, bundled = paths
    store.write_text(json.dumps({'holidays': {'1403': {'1-1': 'Old'}}}), encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload(version=140500)), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert holiday_io.read_version(store) == 140500
    assert data[1403][(1, 1)] == ['Nowruz']


def test_resolve_falls_back_when_store_year_maps_are_empty(paths):
    """Year keys that hold no entries at all parse truthy but carry no
    holidays - they must not block the bundled fallback either."""
    store, bundled = paths
    store.write_text(json.dumps({
        'version': 900,
        'holidays': {'1404': {}, '1405': {}},
    }), encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload(version=1)), encoding='utf-8')
    data = holiday_io.resolve_holidays_store()
    assert data == {1403: {(1, 1): ['Nowruz'], (2, 2): ['a', 'b']}}


def test_resolve_keeps_store_equal_to_bundled_version(paths):
    """Equal versions mean nothing to gain from the bundled file: the store is
    served as is, with no rewrite (and so no backup) behind the user's back."""
    store, bundled = paths
    store.write_text(json.dumps(bundled_payload(version=140500)), encoding='utf-8')
    bundled.write_text(json.dumps(bundled_payload(version=140500)), encoding='utf-8')
    holiday_io.resolve_holidays_store()
    assert holiday_io.read_version(store) == 140500
    assert not store.with_suffix('.json.bak').exists()


def test_replace_store_accepts_the_already_validated_payload(paths):
    """validate_payload already parsed the exact bytes; the update path hands
    that result over so the payload is not parsed a second time."""
    store, _ = paths
    payload = json.dumps({'version': 6, 'holidays': {'1404': {'1-1': 'X'}}}).encode('utf-8')
    validated = holiday_io.validate_payload(payload)
    assert validated is not None
    assert holiday_io.replace_store(payload, validated=validated)
    assert holiday_io.read_version(store) == 6


def test_replace_store_validated_argument_is_not_trusted_blind(paths):
    """A caller must not be able to install entries validation rejected."""
    store, _ = paths
    payload = json.dumps({'version': 7, 'holidays': {'x': 'y'}}).encode('utf-8')
    assert holiday_io.validate_payload(payload) is None
    assert not holiday_io.replace_store(payload, validated=({'holidays': {'x': 'y'}}, 7))
    assert not store.exists()

