import json

import pytest

from config import APP_CONFIG
from utils import event_io
from utils.json_settings import JsonSettings
from utils.settings_migration import (_MIGRATION_FLAG_KEY, migrate_from_registry,
                                      LEGACY_USER_EVENTS_SETTING_KEY)


class FakeLegacy:
    """QSettings stand-in: reads values, records deletions (which must never happen)."""

    def __init__(self, values):
        self.values = dict(values)
        self.deleted = []

    def value(self, key):
        return self.values.get(key)


@pytest.fixture
def events_path(tmp_path, monkeypatch):
    p = tmp_path / "user_events.json"
    monkeypatch.setattr(APP_CONFIG, "USER_EVENTS_FILE_PATH", p)
    return p


def test_first_run_migrates_settings_and_events(events_path, tmp_path):
    legacy = FakeLegacy({
        APP_CONFIG.AUTO_START_SETTING_KEY: "true",
        APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY: "dark",
        APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY: "true",
        LEGACY_USER_EVENTS_SETTING_KEY: {
            "0000-01-01": {"text": "yearly thing", "yearly": True},
        },
    })
    s = JsonSettings(tmp_path / "settings.json")

    migrate_from_registry(s, legacy=legacy)

    assert s.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is True
    assert s.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY) == "dark"
    assert s.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool) is True
    assert event_io.load_user_events() == {
        "0000-01-01": {"text": "yearly thing", "recurrence": "yearly", "remove_after_finish": False},
    }
    # Registry keys must be left in place (rollback safety).
    assert legacy.deleted == []


def test_second_run_is_a_noop(events_path, tmp_path):
    s = JsonSettings(tmp_path / "settings.json")
    migrate_from_registry(s, legacy=FakeLegacy({APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY: "dark"}))

    s.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, "light")
    # Second launch: the (newer) JSON value must not be clobbered by the legacy one.
    migrate_from_registry(s, legacy=FakeLegacy({APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY: "dark"}))
    assert s.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY) == "light"


def test_migrates_serialized_string_event_blob(events_path, tmp_path):
    legacy = FakeLegacy({
        LEGACY_USER_EVENTS_SETTING_KEY: json.dumps({"1403/07/07": {"text": "from string"}}),
    })
    s = JsonSettings(tmp_path / "settings.json")

    migrate_from_registry(s, legacy=legacy)

    # The legacy slash-separated key normalizes to the canonical dash form
    # (EVT-2), so the migrated event is actually visible to the calendar.
    assert event_io.load_user_events() == {
        "1403-07-07": {"text": "from string", "recurrence": "none", "remove_after_finish": False},
    }


def test_event_save_failure_defers_migration_flag(events_path, tmp_path, monkeypatch):
    legacy = FakeLegacy({LEGACY_USER_EVENTS_SETTING_KEY: {"0000-01-01": {"text": "x"}}})
    s = JsonSettings(tmp_path / "settings.json")
    monkeypatch.setattr(event_io, "save_user_events", lambda events: False)

    migrate_from_registry(s, legacy=legacy)

    assert not s.value(_MIGRATION_FLAG_KEY, False, type=bool)
    # Next launch retries and completes.
    monkeypatch.setattr(event_io, "save_user_events", lambda events: True)
    migrate_from_registry(s, legacy=legacy)
    assert s.value(_MIGRATION_FLAG_KEY, False, type=bool)


def test_no_legacy_values_still_sets_flag(events_path, tmp_path):
    s = JsonSettings(tmp_path / "settings.json")
    migrate_from_registry(s, legacy=FakeLegacy({}))
    assert s.value(_MIGRATION_FLAG_KEY, False, type=bool) is True
    assert event_io.load_user_events() == {}


def test_existing_json_events_win_over_legacy_blob(events_path, tmp_path):
    """EVT-4: a valid JSON event store must never be overwritten by migration.

    A beta tester without the migration flag but with real JSON events used to
    have the whole store replaced by the registry blob on the next launch.
    """
    events_path.write_text(json.dumps({
        "1405-02-03": {"text": "json event", "recurrence": "none", "remove_after_finish": False},
    }), encoding="utf-8")
    s = JsonSettings(tmp_path / "settings.json")
    legacy = FakeLegacy({LEGACY_USER_EVENTS_SETTING_KEY: {"0000-01-01": {"text": "legacy thing", "yearly": True}}})

    migrate_from_registry(s, legacy=legacy)

    assert event_io.load_user_events() == {
        "1405-02-03": {"text": "json event", "recurrence": "none", "remove_after_finish": False},
    }
    # Migration is still marked complete: JSON won, nothing is left to do.
    assert s.value(_MIGRATION_FLAG_KEY, False, type=bool) is True
    # The registry blob itself is untouched (rollback safety).
    assert legacy.values[LEGACY_USER_EVENTS_SETTING_KEY]


def test_json_settings_win_on_partial_migration_retry(events_path, tmp_path):
    """EVT-4 (settings half): a retried migration must not clobber newer JSON values."""
    s = JsonSettings(tmp_path / "settings.json")
    s.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, "light")
    legacy = FakeLegacy({APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY: "dark"})

    migrate_from_registry(s, legacy=legacy)

    assert s.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY) == "light"
    assert s.value(_MIGRATION_FLAG_KEY, False, type=bool) is True
