"""Boot smoke test: the full controller must come up cleanly, including with
legacy stores, expired events and holiday seeding."""
import datetime
import json

import jdatetime

from config import APP_CONFIG
from utils import event_io
from utils.event_io import make_event_key


def _seed_events_file(payload):
    APP_CONFIG.USER_EVENTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG.USER_EVENTS_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _menu_labels(menu):
    """Extract visible labels from the tray menu (QWidgetActions carry custom widgets)."""
    from PyQt6.QtWidgets import QWidgetAction

    labels = []
    for action in menu.actions():
        if not isinstance(action, QWidgetAction):
            if action.text():
                labels.append(action.text())
            continue
        widget = action.defaultWidget()
        if widget is None:
            continue
        if hasattr(widget, "label"):               # MenuActionWidget / ThemeToggle
            labels.append(widget.label.text())
        elif hasattr(widget, "text_label"):        # IconCheckboxActionWidget
            labels.append(widget.text_label.text())
    return labels


def test_tray_boots_and_builds_menu(tray):
    assert tray.icon() is not None
    menu = tray.contextMenu()
    assert menu is not None
    labels = _menu_labels(menu)
    assert "تبدیل تاریخ" in labels
    assert "مدیریت رویدادها" in labels
    assert "مشاهده تعطیلات" in labels
    assert "بررسی بروزرسانی" in labels
    assert "خروج" in labels


def test_holiday_store_seeded_from_bundle(user_data):
    assert not APP_CONFIG.HOLIDAYS_STORE_PATH.exists()
    icon = tray_boot(user_data)
    try:
        assert APP_CONFIG.HOLIDAYS_STORE_PATH.exists(), "AppData store should be seeded on first run"
    finally:
        remove_tray_event_filter(icon)


def tray_boot(user_data):
    """Boot a tray against an in-memory autostart registry, never the real one.

    The caller MUST hand the returned icon to ``remove_tray_event_filter``
    before the test ends: the filter installs on the application object, which
    outlives the test, so a live filter holding bound callbacks (and the boot
    timer it schedules) would leak into later tests.
    """
    from core.app_controller import SystemTrayIcon
    from tests.fake_registry import FakeStartupRegistry
    from utils.json_settings import JsonSettings
    return SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH),
                          startup_registry=FakeStartupRegistry())


def remove_tray_event_filter(icon):
    """Remove the tray's native event filter from the application object."""
    from PyQt6.QtCore import QCoreApplication
    QCoreApplication.instance().removeNativeEventFilter(icon.event_filter)


def test_boot_with_expired_pending_event_does_not_crash(user_data, monkeypatch):
    """Regression: an expired auto-delete event at startup used to raise
    AttributeError (calendar not yet created) and abort the launch."""
    # timedelta arithmetic, not a replace()-based construction: on 1 Farvardin
    # the month clamp keeps the same year and lands on a FUTURE date, so those
    # tests could flake one day a year.
    past = jdatetime.date.today() - datetime.timedelta(days=1)
    expired_key = make_event_key(past, "none")
    _seed_events_file({
        "version": event_io.EVENTS_STORE_VERSION,
        "events": {expired_key: {"text": "expired", "recurrence": "none", "remove_after_finish": True}},
    })

    tray = tray_boot(user_data)
    try:
        assert expired_key not in tray.user_events
        stored = json.loads(APP_CONFIG.USER_EVENTS_FILE_PATH.read_text(encoding="utf-8"))
        assert expired_key not in stored["events"]
    finally:
        remove_tray_event_filter(tray)


def test_boot_migrates_legacy_v1_store_to_v2_on_save(user_data):
    legacy = {
        "0000-01-01": {"text": "yearly thing", "yearly": True, "remove_after_finish": False},
        "1403-07-07": "plain string event",
    }
    _seed_events_file(legacy)

    tray = tray_boot(user_data)
    try:
        assert tray.user_events["0000-01-01"]["recurrence"] == "yearly"
        assert tray.user_events["1403-07-07"]["recurrence"] == "none"

        # Touch the store: the next save must write the versioned envelope.
        tray.add_user_event(jdatetime.date(1404, 5, 5), "new one", "none", False)
        raw = json.loads(APP_CONFIG.USER_EVENTS_FILE_PATH.read_text(encoding="utf-8"))
        assert raw["version"] == event_io.EVENTS_STORE_VERSION
        assert raw["events"]["1404-05-05"]["text"] == "new one"
    finally:
        remove_tray_event_filter(tray)


def test_add_replace_and_remove_event_flow(tray):
    today = jdatetime.date.today()
    tray.add_user_event(today, "first", "none", True)
    key = today.strftime("%Y-%m-%d")
    assert tray.user_events[key]["text"] == "first"

    # Adding the same recurrence again replaces that event...
    tray.add_user_event(today, "second", "none", True)
    assert tray.user_events[key]["text"] == "second"
    assert len(tray.user_events) == 1

    # ...while a different recurrence is a second, coexisting event on the date.
    tray.add_user_event(today, "third", "yearly", True)
    yearly_key = "0000-%02d-%02d" % (today.month, today.day)
    assert tray.user_events[key]["text"] == "second"
    assert tray.user_events[yearly_key]["text"] == "third"
    assert tray.user_events[yearly_key]["remove_after_finish"] is False  # recurring can't auto-delete

    # Removing by date still clears every variant it covers.
    tray.remove_user_event(today)
    assert key not in tray.user_events
    assert yearly_key not in tray.user_events


def test_import_merges_and_cleans(tray, tmp_path):
    past = jdatetime.date.today() - datetime.timedelta(days=1)
    payload = {
        "version": event_io.EVENTS_STORE_VERSION,
        "events": {
            make_event_key(past, "none"): {"text": "expired", "recurrence": "none", "remove_after_finish": True},
            "0000-00-10": {"text": "monthly", "recurrence": "monthly", "remove_after_finish": False},
        },
    }
    import_file = tmp_path / "import.json"
    import_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = event_io.import_events_from_file(import_file)
    imported, skipped = result
    assert skipped == 0
    tray.user_events.update(imported)
    tray._clean_expired_events()
    assert "0000-00-10" in tray.user_events
    assert make_event_key(past, "none") not in tray.user_events


def test_export_writes_versioned_file(tray, tmp_path):
    today = jdatetime.date.today()
    tray.add_user_event(today, "exported", "none", False)
    out = tmp_path / "out.json"
    assert event_io.export_events_to_file(tray.user_events, out)
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["version"] == event_io.EVENTS_STORE_VERSION
    assert any(entry["text"] == "exported" for entry in raw["events"].values())
