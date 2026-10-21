"""Tests for ui.widgets.calendar_day_cell: the clickable day cell with its
custom tooltip lifecycle and the add/remove-event context menu."""
import jdatetime
import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QAction, QColor, QContextMenuEvent, QCursor, QFontMetrics, QImage
from PyQt6.QtWidgets import QApplication, QMenu, QWidget, QWidgetAction

from config import APP_CONFIG
from tests.qt_mousing import press
from ui.widgets.calendar_day_cell import (ClickableLabel, CopyDateMenu,
                                          DISTANCE_ACTION_TEXT)
from ui.widgets.menu_widgets import (CenteredTextMenu, MENU_ITEM_PADDING_LEAD,
                                     MENU_ITEM_PADDING_TRAIL,
                                     MENU_ITEM_PADDING_V,
                                     centered_menu_stylesheet)
from ui.widgets.tooltip import TOOLTIP_DELAY_MS, CustomTooltip


@pytest.fixture(autouse=True, scope="module")
def _app_fonts(qapp):
    """The production app always starts with its bundled Vazirmatn fonts
    (main.py loads them before any window exists), and this module's row
    geometry / rendered-ink assertions are measured against those metrics.
    Loading is idempotent; without it a lone run of this file depends on the
    accident of test_asset_loader (alphabetically earlier) having loaded
    them. Depends on qapp: QFontDatabase needs the QApplication to exist."""
    from utils.asset_loader import load_fonts
    load_fonts()


@pytest.fixture(autouse=True)
def _reset_tooltip_singleton():
    CustomTooltip._instance = None
    yield
    if CustomTooltip._instance is not None:
        CustomTooltip._instance.hide()
        CustomTooltip._instance = None


@pytest.fixture
def cell(qtbot):
    label = ClickableLabel()
    qtbot.addWidget(label)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    return label


def test_left_click_emits_clicked_with_jalali_date(cell):
    received = []
    cell.clicked.connect(lambda jdate: received.append(jdate))
    cell.mousePressEvent(press(cell))
    assert received == [cell.jalali_date]


def test_right_click_does_not_emit_clicked(cell):
    received = []
    cell.clicked.connect(lambda jdate: received.append(jdate))
    cell.mousePressEvent(press(cell, button=Qt.MouseButton.RightButton))
    assert received == []


def test_settooltip_overrides_native_tooltip(cell):
    cell.setToolTip("custom text")
    # The custom tooltip system stores it; QLabel's dynamic tooltip stays empty.
    assert cell._tooltip_text == "custom text"


def test_enter_starts_timer_only_with_text(qtbot, cell):
    cell.enterEvent(None)
    assert not cell._tooltip_timer.isActive()  # no tooltip text yet
    cell.setToolTip("holiday reason")
    cell.enterEvent(None)
    assert cell._tooltip_timer.isActive()
    # The grid waits the same delay the event manager's tooltips do: one shared
    # value, so the two surfaces cannot drift apart.
    assert cell._tooltip_timer.interval() == TOOLTIP_DELAY_MS


def test_leave_stops_timer_and_hides_shared_tooltip(qtbot, cell):
    cell.setToolTip("text")
    cell.enterEvent(None)
    cell.leaveEvent(None)
    assert not cell._tooltip_timer.isActive()
    assert not CustomTooltip.instance().isVisible()


def test_stale_timer_does_not_pop_tooltip_for_moved_off_cursor(qtbot, cell):
    """Regression guard for the tooltip-over-editor bug: the cursor check must
    veto a tooltip for a cell the cursor is no longer over."""
    cell.setToolTip("stale")
    cell.move(500, 500)  # cursor (offscreen 0,0 region) is far outside
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_tooltip_shows_when_cursor_genuinely_inside(qtbot, cell, monkeypatch):
    cell.setToolTip("real hover")
    cell.resize(35, 35)
    cell.show()  # the visibility guard must see a live cell
    # Pin the cursor to the cell's center (deterministic on every platform).
    monkeypatch.setattr(QCursor, "pos",
                        staticmethod(lambda: cell.mapToGlobal(cell.rect().center())))
    cell._show_custom_tooltip()
    assert CustomTooltip.instance().isVisible()
    assert CustomTooltip.instance()._label.text() == "real hover"


def test_tooltip_skipped_while_context_menu_open(qtbot, cell):
    cell.setToolTip("text")
    cell._context_menu_open = True
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_tooltip_skipped_when_cell_hidden(qtbot, cell):
    cell.setToolTip("text")
    cell.hide()
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_cancel_pending_tooltip_stops_and_hides(qtbot, cell):
    cell.setToolTip("text")
    cell.enterEvent(None)
    cell.cancel_pending_tooltip()
    assert not cell._tooltip_timer.isActive()
    assert not CustomTooltip.instance().isVisible()


def test_context_menu_requires_date_and_text(cell):
    """No jalali date or no label text: the menu must not even open."""
    cell.jalali_date = None
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert cell._context_menu_open is False


def test_context_menu_add_action_emits_after_menu_closes(qtbot, cell, monkeypatch):
    """The full right-click flow, with QMenu.exec stubbed out (offscreen)."""
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)
    cell.setText("۵")  # a non-empty label is required too
    add_requested, remove_requested = [], []
    cell.add_event_requested.connect(lambda j: add_requested.append(j))
    cell.remove_event_requested.connect(lambda j: remove_requested.append(j))

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert cell._context_menu_open is False  # reset after exec returns


def test_context_menu_without_user_event_offers_only_adding(qtbot, cell, open_menu):
    """Nothing to edit or remove yet: the day menu offers just the add row.

    The delete row used to be present-but-greyed here; it is now absent, because
    the store - not the cell's has_user_event hint - is what the menu reads."""
    cell.setText("۵")
    rows = _menu_rows(open_menu(cell))
    assert "افزودن رویداد" in rows
    assert "ویرایش رویداد" not in rows
    assert "حذف رویداد" not in rows


def test_a_day_with_an_event_can_still_add_a_different_one(qtbot, open_menu):
    """A monthly event must not lock the date against other events: «افزودن
    رویداد» stays available so a one-time event can join it."""
    host = _HostWindow({"0000-00-02": {"text": "Take medication", "recurrence": "monthly",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    rows = _menu_rows(open_menu(label))
    assert "افزودن رویداد" in rows
    # ...alongside the row that edits the one that is already there.
    assert "ویرایش رویداد" in rows
    assert "حذف رویداد" in rows


def test_context_menu_remove_enabled_with_user_event(qtbot, open_menu):
    host = _HostWindow({"1404-05-02": {"text": "Doctor", "recurrence": "none",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    menu = open_menu(label)
    remove_widget = next(a.defaultWidget() for a in menu.actions()
                         if getattr(a, "defaultWidget", lambda: None)() is not None
                         and hasattr(a.defaultWidget(), "label")
                         and a.defaultWidget().label.text() == "حذف رویداد")
    assert remove_widget.isEnabled() is True


def test_add_event_emission_is_delayed_until_menu_gone(cell, qtbot):
    """_emit_after_menu_close closes first, emits via singleShot."""
    received = []
    cell.add_event_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._emit_after_menu_close(menu, cell.add_event_requested, cell.jalali_date)
    assert menu.closed
    assert received == []  # not emitted synchronously
    qtbot.wait(100)  # let the 50ms singleShot fire
    assert received == [cell.jalali_date]


def test_remove_event_emission_is_delayed_until_menu_gone(cell, qtbot):
    received = []
    cell.remove_event_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._emit_after_menu_close(menu, cell.remove_event_requested, cell.jalali_date)
    assert menu.closed
    assert received == []  # not emitted synchronously
    qtbot.wait(100)  # let the 50ms singleShot fire
    assert received == [cell.jalali_date]


def test_context_menu_asks_host_window_to_normalize_hover(qtbot, monkeypatch):
    """After the menu closes, the host calendar re-syncs hover flags."""
    normalized = []

    class HostWindow(QWidget):
        def normalize_day_hover(self):
            normalized.append(1)

    host = HostWindow()
    qtbot.addWidget(host)
    cell = ClickableLabel(host)
    qtbot.addWidget(cell)
    cell.jalali_date = jdatetime.date(1404, 5, 2)
    cell.setText("۵")
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert normalized == [1]


# --- «کپی تاریخ» submenu ------------------------------------------------------------


@pytest.fixture
def open_menu(monkeypatch):
    """Open the day context menu with QMenu.exec stubbed, capturing the menu."""
    captured = []

    def _open(cell):
        monkeypatch.setattr(QMenu, "exec", lambda self, pos: captured.append(self))
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                                  cell.mapToGlobal(QPoint(5, 5)))
        cell.contextMenuEvent(event)
        return captured[-1]

    return _open


def _copy_title_action(menu: QMenu) -> QAction:
    """The «کپی تاریخ» submenu title (the only action carrying a QMenu)."""
    return next(a for a in menu.actions() if a.menu() is not None)


def test_context_menu_builds_copy_date_submenu(qtbot, cell, open_menu):
    """Right-clicking a day offers a PLAIN Qt submenu with the three entries
    (hairline separators between them): a normal QAction/QMenu relationship
    Qt fully owns (hover, keyboard, arrow, RTL, screen edges) — no custom
    widget row in the title."""
    cell.setText("۵")
    menu = open_menu(cell)
    title_action = _copy_title_action(menu)
    assert isinstance(title_action, QAction)
    assert not isinstance(title_action, QWidgetAction)
    assert title_action.text() == "کپی تاریخ"
    copy_menu = title_action.menu()
    rows = copy_menu.actions()
    assert len(rows) == 11  # 6 options, a hairline between every pair
    assert [a.text() for a in rows if a.text()] == [
        "تاریخ شمسی", "تاریخ شمسی کامل", "تاریخ میلادی", "تاریخ میلادی کامل",
        "هر دو", "هر دو کامل",
    ]
    assert all(rows[i].isSeparator() for i in (1, 3, 5, 7, 9))
    for row in rows:
        assert isinstance(row, QAction) and not isinstance(row, QWidgetAction)


def _menu_rows(menu: QMenu):
    """The day menu as the user reads it: separators and rows in order.

    Insertion order is the visual order even though the menu is RTL, so this is
    the one place that can assert the whole layout at once.
    """
    rows = []
    for action in menu.actions():
        if action.isSeparator():
            rows.append("---")
        elif action.menu() is not None:
            rows.append(action.text())          # the plain «کپی تاریخ» submenu
        else:
            rows.append(action.defaultWidget().label.text())
    return rows


def test_context_menu_reads_copy_distance_add_delete(qtbot, cell, open_menu):
    """The day's menu leads with the two ways to read the day - its text, and how
    far off today it is - and only then offers the two that change it. Each row
    sits in its own block, so the distance notice stays separable from the copy
    formats above it."""
    cell.setText("۱")
    rows = _menu_rows(open_menu(cell))
    assert rows == ["کپی تاریخ", "---", DISTANCE_ACTION_TEXT, "---", "افزودن رویداد"]


def test_the_add_row_keeps_its_wording_on_an_event_day(qtbot, open_menu):
    """The row used to double as add-OR-edit and relabelled itself «ویرایش
    رویداد» on an event day, which is what left a recurring day with no way to
    add a second, different event."""
    host = _HostWindow({"0000-00-02": {"text": "Take medication", "recurrence": "monthly",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    assert _menu_rows(open_menu(label))[4] == "افزودن رویداد"


def test_the_add_row_disappears_when_every_mode_is_taken(qtbot, open_menu):
    """A date holds at most one event per mode, so a day carrying all three has
    nothing left to create - and must not open an editor with no usable mode."""
    host = _HostWindow({
        "1404-05-02": {"text": "Doctor", "recurrence": "none", "remove_after_finish": False},
        "0000-00-02": {"text": "Take medication", "recurrence": "monthly",
                       "remove_after_finish": False},
        "0000-05-02": {"text": "Dentist", "recurrence": "yearly", "remove_after_finish": False},
    })
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    rows = _menu_rows(open_menu(label))
    assert "افزودن رویداد" not in rows
    # The three events are still reachable for editing and deleting.
    assert "ویرایش رویداد" in rows and "حذف رویداد" in rows


def test_existing_day_menu_actions_survive_copy_submenu(qtbot, open_menu):
    host = _HostWindow({"1404-05-02": {"text": "Doctor", "recurrence": "none",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    menu = open_menu(label)
    labels = []
    for action in menu.actions():
        widget = action.defaultWidget() if hasattr(action, "defaultWidget") else None
        if widget is not None and hasattr(widget, "label"):
            labels.append(widget.label.text())
    assert "افزودن رویداد" in labels
    assert "حذف رویداد" in labels
    # The copy entry is the plain submenu title (not a widget row).
    assert "کپی تاریخ" in [a.text() for a in menu.actions()]


# --- per-event rows when a day carries several events -------------------------------


class _HostWindow(QWidget):
    """Minimal stand-in for the calendar popup: the cell only reads its events."""

    def __init__(self, events):
        super().__init__()
        self.user_events = events
        self.normalized = 0

    def normalize_day_hover(self):
        self.normalized += 1


class _FakeMenu:
    """Just enough menu for the deferred-emission helpers, which only close it."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _two_event_cell(qtbot):
    """A cell inside a host whose day carries a one-time and a monthly event."""
    host = _HostWindow({
        "1404-05-02": {"text": "Doctor", "recurrence": "none", "remove_after_finish": False},
        "0000-00-02": {"text": "Pay bills", "recurrence": "monthly", "remove_after_finish": False},
    })
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True
    return host, label


def _submenu_rows(menu, title):
    """The text rows of one named submenu, in the order they were added.

    Hairline divider rows carry no text and belong to the spacing, not the
    captions, so callers compare against the visible texts alone.
    """
    action = next(a for a in menu.actions() if a.menu() is not None and a.text() == title)
    return [a.text() for a in action.menu().actions() if a.text()]


def test_a_multi_event_day_offers_one_row_per_event(qtbot, open_menu):
    """With several events on the day there is no single "the" event any more, so
    edit and delete become submenus listing each event with its recurrence."""
    _host, cell = _two_event_cell(qtbot)

    rows = _menu_rows(open_menu(cell))

    # The plain edit/delete rows are gone: a date-level edit would be ambiguous
    # once two events share the date. Adding is not ambiguous - it targets a new
    # key - so its row stays.
    assert rows == ["کپی تاریخ", "---", DISTANCE_ACTION_TEXT, "---", "افزودن رویداد",
                    "---", "ویرایش رویداد", "---", "حذف رویداد"]


def test_multi_event_rows_carry_the_text_and_its_recurrence(qtbot, open_menu):
    _host, cell = _two_event_cell(qtbot)
    menu = open_menu(cell)

    assert _submenu_rows(menu, "ویرایش رویداد") == ["Doctor", "Pay bills (ماهانه)"]
    assert _submenu_rows(menu, "حذف رویداد") == ["Doctor", "Pay bills (ماهانه)"]


def test_multi_event_submenus_hairline_separate_their_rows(qtbot, open_menu):
    """The copy submenu separates its entries with hairline dividers so each
    reads as one distinct option; the per-event rows read the same way - one
    divider between neighbours, none at the list edges."""
    _host, cell = _two_event_cell(qtbot)
    menu = open_menu(cell)

    for title in ("ویرایش رویداد", "حذف رویداد"):
        action = next(a for a in menu.actions()
                      if a.menu() is not None and a.text() == title)
        rows = action.menu().actions()
        texts = [a for a in rows if a.text()]
        assert [a.text() for a in texts] == ["Doctor", "Pay bills (ماهانه)"]
        separators = [a for a in rows if a.isSeparator()]
        assert len(separators) == 1
        assert rows.index(separators[0]) == rows.index(texts[0]) + 1


def test_choosing_an_event_to_edit_emits_that_key(qtbot, open_menu):
    """The row the user picked decides which event the editor opens - not the day."""
    _host, cell = _two_event_cell(qtbot)
    received = []
    cell.edit_event_requested_specific.connect(
        lambda jdate, key, entry: received.append((jdate, key, entry["text"])))
    menu = open_menu(cell)

    edit_menu = next(a.menu() for a in menu.actions() if a.text() == "ویرایش رویداد")
    next(a for a in edit_menu.actions() if a.text() == "Pay bills (ماهانه)").trigger()
    assert received == []  # deferred until the menu is gone
    qtbot.wait(100)

    assert received == [(cell.jalali_date, "0000-00-02", "Pay bills")]


def test_choosing_an_event_to_remove_emits_that_key(qtbot, open_menu):
    """The delete submenu is built by the same row builder as the edit one, and
    its rows must carry the same per-event key."""
    _host, cell = _two_event_cell(qtbot)
    received = []
    cell.remove_event_requested_specific.connect(lambda key: received.append(key))
    menu = open_menu(cell)

    remove_menu = next(a.menu() for a in menu.actions() if a.text() == "حذف رویداد")
    next(a for a in remove_menu.actions() if a.text() == "Pay bills (ماهانه)").trigger()
    assert received == []  # deferred until the menu is gone
    qtbot.wait(100)

    assert received == ["0000-00-02"]


def _merged_cell(qtbot, text="Pay bills\nDoctor appointment", recurrence="monthly"):
    """A cell whose single event carries several text lines (the merge result)."""
    host = _HostWindow({
        "0000-00-02": {"text": text, "recurrence": recurrence, "remove_after_finish": False},
        "1404-05-02": {"text": "Standalone", "recurrence": "none", "remove_after_finish": False},
    })
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True
    return host, label


def test_a_merged_event_stays_one_menu_row(qtbot, open_menu):
    """A merge leaves ONE logical event holding several lines. Qt renders a "\n"
    inside QAction text as a line break, so the raw text would make the row twice
    as tall and push the submenu off the screen."""
    _host, cell = _merged_cell(qtbot)
    menu = open_menu(cell)

    for title in ("ویرایش رویداد", "حذف رویداد"):
        rows = _submenu_rows(menu, title)
        merged = [row for row in rows if "Pay bills" in row]
        assert len(merged) == 1, rows
        assert "\n" not in merged[0]
        # Both halves stay readable, and the recurrence still reads.
        assert "Pay bills" in merged[0] and "Doctor appointment" in merged[0]
        assert "ماهانه" in merged[0]
        # The join is a plain hyphen: the em dash is not a character this menu
        # should ever show.
        assert merged[0] == "Pay bills - Doctor appointment (ماهانه)"


def test_the_menu_label_is_shorter_than_the_stored_text(qtbot, open_menu):
    """Only the presentation shrinks; picking the row still hands the editor the
    full multi-line text."""
    text = "Pay bills\nDoctor appointment"
    _host, cell = _merged_cell(qtbot, text=text)
    received = []
    cell.edit_event_requested_specific.connect(
        lambda jdate, key, entry: received.append((key, entry["text"])))
    menu = open_menu(cell)

    edit_menu = next(a.menu() for a in menu.actions() if a.text() == "ویرایش رویداد")
    merged_row = next(a for a in edit_menu.actions() if "Pay bills" in a.text())
    merged_row.trigger()
    qtbot.wait(100)

    assert received == [("0000-00-02", text)]


def test_a_long_merged_event_is_elided_on_one_line(qtbot, open_menu):
    _host, cell = _merged_cell(qtbot, text="A very long first line indeed\nand a second one too")
    menu = open_menu(cell)

    edit_menu = next(a.menu() for a in menu.actions() if a.text() == "ویرایش رویداد")
    row = next(a for a in edit_menu.actions() if a.text().startswith("A very long"))
    assert "\n" not in row.text()
    assert row.text().endswith("… (ماهانه)")
    assert len(row.text()) < len("A very long first line indeed\nand a second one too")


def test_a_merged_event_presents_exactly_like_its_single_line_form(qtbot, open_menu):
    """The geometry invariant behind the fix: folding the lines back must leave
    the submenu indistinguishable from a text that was written on one line.

    Qt does not wrap an embedded newline - it lays it out as one very wide row
    (the submenu more than doubled in width), which is what pushed it past the
    screen edge."""
    def submenu_hint(lines, separator="\n"):
        text = separator.join(lines)
        _host, cell = _merged_cell(qtbot, text=text)
        menu = open_menu(cell)
        edit_menu = next(a.menu() for a in menu.actions() if a.text() == "ویرایش رویداد")
        return edit_menu.sizeHint(), [a.text() for a in edit_menu.actions()]

    joined_hint, joined_rows = submenu_hint(["Pay bills", "Doctor appointment"])
    one_line_hint, one_line_rows = submenu_hint(["Pay bills - Doctor appointment"], "")

    assert joined_rows == one_line_rows
    assert joined_hint == one_line_hint

    # Rows stay uniform no matter how many lines the text carries.
    _host, three = _merged_cell(qtbot, text="Pay bills\nDoctor appointment\nAnd a third")
    edit_menu = next(a.menu() for a in open_menu(three).actions() if a.text() == "ویرایش رویداد")
    assert edit_menu.sizeHint().height() == joined_hint.height()


def test_choosing_an_event_to_delete_emits_that_key(cell, qtbot):
    """Deleting one event of a several-event day takes only that one."""
    received = []
    cell.remove_event_requested_specific.connect(lambda key: received.append(key))
    cell._emit_after_menu_close(_FakeMenu(), cell.remove_event_requested_specific, "0000-00-02")

    assert received == []  # deferred until the menu is gone
    qtbot.wait(100)
    assert received == ["0000-00-02"]


def test_a_single_event_day_keeps_its_plain_rows(qtbot, open_menu):
    """One event on the day: add, then the plain edit/delete pair."""
    host = _HostWindow({"1404-05-02": {"text": "Doctor", "recurrence": "none",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True

    rows = _menu_rows(open_menu(label))

    assert rows == ["کپی تاریخ", "---", DISTANCE_ACTION_TEXT, "---", "افزودن رویداد",
                    "---", "ویرایش رویداد", "---", "حذف رویداد"]


def test_the_single_event_edit_row_emits_that_events_key(qtbot, open_menu):
    """The plain edit row edits the one event that is there, by key - the same
    key-scoped path the multi-event submenu rows use."""
    host = _HostWindow({"0000-00-02": {"text": "Take medication", "recurrence": "monthly",
                                       "remove_after_finish": False}})
    qtbot.addWidget(host)
    label = ClickableLabel(host)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    label.setText("۲")
    label.has_user_event = True
    received = []
    label.edit_event_requested_specific.connect(
        lambda jdate, key, entry: received.append((jdate, key)))

    menu = open_menu(label)
    edit_widget = next(a.defaultWidget() for a in menu.actions()
                       if getattr(a, "defaultWidget", lambda: None)() is not None
                       and hasattr(a.defaultWidget(), "label")
                       and a.defaultWidget().label.text() == "ویرایش رویداد")
    edit_widget.triggered.emit()
    qtbot.wait(100)

    assert received == [(label.jalali_date, "0000-00-02")]


@pytest.mark.parametrize("jy,jm,jd", [
    (1404, 5, 2),    # a normal in-month day
    (1404, 10, 15),  # Gregorian year differs from the Jalali year
    (1400, 12, 29),  # different month/year pair
    (1200, 1, 1),    # near the supported range start
    (1600, 3, 30),   # near the supported range end
])
def test_copy_actions_put_the_right_clicked_day_on_clipboard(qtbot, cell, open_menu, jy, jm, jd):
    """Every entry copies the RIGHT-CLICKED day, not today; formats follow the
    app's shared numeric convention (1405/07/01 · 2026/09/23)."""
    from utils.date_utils import (format_gregorian_long, format_gregorian_numeric,
                                   format_jalali_long, format_jalali_numeric)

    cell.setText("۵")
    cell.jalali_date = jdatetime.date(jy, jm, jd)
    clipboard = QApplication.clipboard()
    jalali_text = format_jalali_numeric(cell.jalali_date)
    gregorian_text = format_gregorian_numeric(cell.jalali_date)
    jalali_full = format_jalali_long(cell.jalali_date, persian_digits=False)
    gregorian_full = format_gregorian_long(cell.jalali_date.togregorian(),
                                           persian_digits=False)
    expected = {
        "تاریخ شمسی": jalali_text,
        "تاریخ شمسی کامل": jalali_full,
        "تاریخ میلادی": gregorian_text,
        "تاریخ میلادی کامل": gregorian_full,
        "هر دو": f"{jalali_text}\n{gregorian_text}",
        "هر دو کامل": f"{jalali_full}\n{gregorian_full}",
    }
    # One menu per mode: a copy morphs its row and greys the others until
    # _finish_copy ends the hold, so every mode needs its own fresh menu.
    for label, payload in expected.items():
        menu = open_menu(cell)
        copy_menu = _copy_title_action(menu).menu()
        action = next(action for action in copy_menu.actions()
                      if action.text() == label)
        action.trigger()
        assert clipboard.text() == payload
        copy_menu._finish_copy()


def test_copied_feedback_shows_immediately(qtbot, cell, open_menu):
    """The triggered row morphs the instant it fires — no timer, no waiting
    for the menu teardown (clipboard first, morph at once) — and no tooltip
    flash appears anywhere in the copy path."""
    cell.setText("۵")
    menu = open_menu(cell)
    copy_menu = _copy_title_action(menu).menu()
    tooltip = CustomTooltip.instance()
    assert not tooltip.isVisible()
    action = copy_menu.actions()[0]
    action.trigger()
    # No qtbot.wait anywhere before this assert: synchronous visibility.
    assert action.text() == "✓ کپی شد"
    assert action.data() == "copy_done"
    assert all(not other.isEnabled()
               for other in copy_menu.actions() if other is not action
               and not other.isSeparator())
    assert not tooltip.isVisible()
    copy_menu._finish_copy()


def test_copied_row_paints_the_accent_pill(qtbot, dark_palette):
    """The morph must show up in ink, not only in action data: the copied row
    gains an accent pill reaching its full row (past the content rect, into
    the arrow gutter), its caption core flips to ACCENT_COLOR while the other
    copy rows grey out."""
    palette = dark_palette
    parent = QMenu()
    qtbot.addWidget(parent)
    m = CopyDateMenu(parent)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    copied = m.add_copy_action("تاریخ شمسی", "jalali")
    m.addSeparator()
    other = m.add_copy_action("هر دو", "both")
    qtbot.addWidget(m)

    bg = palette["BACKGROUND_COLOR"]
    gutters = []
    for action in (copied, other):
        geo = m.actionGeometry(action)
        # x = 8 sits inside the pill's 2px inset but before the content rect
        # (26px lead pad): pill territory no caption can reach.
        gutters.append(QPoint(geo.left() + 8, geo.center().y()))
    base = _grab(m)
    for point in gutters:
        assert _close(base.pixelColor(point.x(), point.y()), QColor(bg), tol=4), \
            "pre-morph gutter is not flat background"

    m.show_copied_row(copied)
    img = _grab(m)
    geo = m.actionGeometry(copied)
    content = _content_rect(geo)
    # the expected blend of the pill over the flat background (alpha 36/255)
    accent = QColor(palette["ACCENT_COLOR"])
    bgc = QColor(bg)
    alpha = 36 / 255
    expected = QColor(
        int(bgc.red() + (accent.red() - bgc.red()) * alpha),
        int(bgc.green() + (accent.green() - bgc.green()) * alpha),
        int(bgc.blue() + (accent.blue() - bgc.blue()) * alpha))
    probe = img.pixelColor(gutters[0].x(), gutters[0].y())
    assert _close(probe, expected, tol=4), \
        f"the copied row's pill is missing at its gutter: {probe.name()} vs {expected.name()}"
    # caption core flips to accent...
    ink = _ink_bbox(img, content, bg)
    assert ink is not None, "no caption after the morph"
    assert _close(_lightest_pixel(img, ink), accent)
    # ...and a non-copied row keeps the plain caption color with no pill
    other_content = _content_rect(m.actionGeometry(other))
    probe2 = img.pixelColor(gutters[1].x(), gutters[1].y())
    assert _close(probe2, QColor(bg), tol=4), \
        "the untouched row grew a pill"
    ink2 = _ink_bbox(img, other_content, bg)
    assert ink2 is not None, "no caption on the untouched row"
    # greyed out while the hold runs - that is "the other copy rows grey out"
    assert _close(_lightest_pixel(img, ink2), QColor(palette["GREY_COLOR"]))
    m._finish_copy()


def test_copy_submenu_uses_the_shared_menu_styling(qtbot, cell, open_menu):
    """Qt owns the row behavior, but the popup keeps the app's custom QMenu
    stylesheet — and the item rules mirror MenuActionWidget's own look so
    the native copy rows match the custom add/remove rows: same Vazirmatn
    14px bold text, same 15px/6px inner box, same rounded MENU_HOVER_COLOR
    hover, and the hairline separator rule for the option dividers. The
    arrow subcontrols ARE zeroed out: bare rules alone proved invisible
    under some Windows styles, so CenteredTextMenu paints the indicator
    itself, and a primitive Qt still drew would land beside that triangle.
    Direction is the app's RTL."""
    from config import APP_CONFIG

    cell.setText("۵")
    menu = open_menu(cell)
    copy_menu = _copy_title_action(menu).menu()
    palette = APP_CONFIG.get_current_palette()
    hover = palette["MENU_HOVER_COLOR"]
    hover_css = f"rgba({hover[0]}, {hover[1]}, {hover[2]}, {hover[3]})"
    for styled_menu in (menu, copy_menu):
        ss = styled_menu.styleSheet()
        assert f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}" in ss
        assert "border-radius: 8px" in ss
        # font: same family / size / weight as MenuActionWidget's label
        assert f"font-family: '{APP_CONFIG.FONT_FAMILY}'" in ss
        assert "font-size: 14px" in ss
        assert "font-weight: bold" in ss
        # item box: same padding as MenuActionWidget's layout margins, built
        # from the same constants CenteredTextMenu's painter uses — and the
        # item text is transparent there because QSS cannot center QMenu::item
        # text (no text-align support): CenteredTextMenu paints the glyphs.
        assert (f"QMenu::item {{ padding: {MENU_ITEM_PADDING_V}px "
                f"{MENU_ITEM_PADDING_TRAIL}px {MENU_ITEM_PADDING_V}px "
                f"{MENU_ITEM_PADDING_LEAD}px; color: transparent; }}") in ss
        assert "QMenu::item:disabled { color: transparent; }" in ss
        # hover: same color and rounded shape as HoverWidget paints
        assert f"QMenu::item:selected {{ background-color: {hover_css}; border-radius: 6px; }}" in ss
        # the arrow subcontrols are suppressed at the source: the painter owns
        # the only indicator (bare rules alone rendered nothing visible on
        # Windows builds)
        assert ("QMenu::left-arrow, QMenu::right-arrow "
                "{ image: none; width: 0px; height: 0px; }") in ss
        # the option dividers use the shared hairline separator rule
        assert "QMenu::separator" in ss
        # RTL app: parent menu and submenu share the direction
        assert styled_menu.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert copy_menu.layoutDirection() == menu.layoutDirection()


def test_native_copy_rows_match_the_widget_row_geometry(qtbot, cell, open_menu):
    """The styling match must be real, not just stylesheet text: with the
    item box mirroring MenuActionWidget's margins, the native «کپی تاریخ»
    title row and the leaf rows are exactly as tall as the custom
    add/remove-event rows."""
    cell.setText("۵")
    menu = open_menu(cell)
    menu.popup(QPoint(10, 10))  # force the menu to lay its rows out
    title = _copy_title_action(menu)
    # Matched by type, not by position: the plain submenu title is a QAction with
    # no defaultWidget at all, so probing that attribute row by row would raise
    # on it the moment it is not last.
    widget_row = next(a for a in menu.actions() if isinstance(a, QWidgetAction))
    widget_height = menu.actionGeometry(widget_row).height()
    title_height = menu.actionGeometry(title).height()
    copy_menu = title.menu()
    copy_menu.popup(QPoint(80, 10))
    leaf_height = copy_menu.actionGeometry(copy_menu.actions()[0]).height()
    menu.close()
    copy_menu.close()
    assert widget_height > 0
    assert title_height == widget_height
    assert leaf_height == widget_height


def test_day_menu_and_copy_submenu_are_centered_text_menus(qtbot, cell, open_menu):
    """Both popups are CenteredTextMenu (a QMenu subclass that only relocates
    the item glyphs after the native paint) — no behavior class, no custom
    rows: the title row is still a plain QAction Qt owns."""
    cell.setText("۵")
    menu = open_menu(cell)
    assert isinstance(menu, CenteredTextMenu)
    title_action = _copy_title_action(menu)
    assert isinstance(title_action, QAction)
    assert not isinstance(title_action, QWidgetAction)
    copy_menu = title_action.menu()
    assert isinstance(copy_menu, CenteredTextMenu)
    for row in copy_menu.actions():
        assert isinstance(row, QAction) and not isinstance(row, QWidgetAction)


def _ink_bbox(image: QImage, rect: QRect, bg: str, tol: int = 10) -> QRect | None:
    """Bounding box of pixels inside `rect` that differ from the flat menu
    background color (antialiased glyphs, hover fill and arrows all differ).
    None when the region is uniformly background."""
    bg = QColor(bg)
    min_x = min_y = 10 ** 9
    max_x = max_y = -1
    top = max(0, rect.top())
    bottom = min(image.height() - 1, rect.bottom())
    left = max(0, rect.left())
    right = min(image.width() - 1, rect.right())
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            c = image.pixelColor(x, y)
            if (abs(c.red() - bg.red()) > tol or abs(c.green() - bg.green()) > tol
                    or abs(c.blue() - bg.blue()) > tol):
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < 0:
        return None
    return QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


@pytest.fixture
def dark_palette():
    """Select the dark theme and hand back its palette.

    The ink probe below finds the lightest pixel in a glyph box, which only
    locates the ink on a dark ground (see ``_lightest_pixel``): these assertions
    are about the dark palette by definition. Selecting it explicitly keeps them
    off the host's Windows setting; the suite-wide ``restore_active_palette``
    fixture puts the palette back afterwards.
    """
    APP_CONFIG.set_theme(APP_CONFIG.Theme.DARK)
    return APP_CONFIG.get_current_palette()


def _lightest_pixel(image: QImage, rect: QRect) -> QColor:
    """The closest-to-white pixel in `rect` — the core of light glyph ink on
    a dark background (dark-theme TEXT_COLOR)."""
    best = QColor("black")
    best_sum = -1
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(rect.left(), rect.right() + 1):
            c = image.pixelColor(x, y)
            s = c.red() + c.green() + c.blue()
            if s > best_sum:
                best_sum, best = s, c
    return best


def _close(a: QColor, b: QColor, tol: int = 8) -> bool:
    return (abs(a.red() - b.red()) <= tol and abs(a.green() - b.green()) <= tol
            and abs(a.blue() - b.blue()) <= tol)


def _grab(menu: QMenu) -> QImage:
    """Render the popup offscreen: QWidget.grab() paints synchronously, so no
    event-loop wait is needed."""
    menu.popup(QPoint(30, 30))
    image = menu.grab().toImage()
    menu.close()
    return image


def _content_rect(row: QRect, rtl: bool = True) -> QRect:
    """A day-menu row's content box, read direction-aware from the shared
    pads: the wider arrow column is the leading pad (physical left under
    RTL), the mirrored side under LTR."""
    lead = MENU_ITEM_PADDING_LEAD if rtl else MENU_ITEM_PADDING_TRAIL
    trail = MENU_ITEM_PADDING_TRAIL if rtl else MENU_ITEM_PADDING_LEAD
    return row.adjusted(lead, MENU_ITEM_PADDING_V, -trail, -MENU_ITEM_PADDING_V)


def test_qss_item_text_is_transparent_so_the_painter_never_doubles_it(qtbot):
    """The production stylesheet must draw NO item glyphs itself — otherwise
    CenteredTextMenu's centered glyphs would land on top of QSS's left-
    aligned ones. A plain QMenu with the shared stylesheet renders empty
    item rows; the same rows under CenteredTextMenu render ink."""
    palette = APP_CONFIG.get_current_palette()
    texts = ["تاریخ شمسی", "تاریخ میلادی", "هر دو"]

    def build(menu_cls):
        m = menu_cls()
        m.setStyleSheet(centered_menu_stylesheet(palette))
        m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        for t in texts:
            m.addAction(t)
        return m

    plain = build(QMenu)
    qtbot.addWidget(plain)
    plain_img = _grab(plain)
    for action in plain.actions():
        geo = plain.actionGeometry(action)
        assert _ink_bbox(plain_img, geo, palette["BACKGROUND_COLOR"]) is None, \
            "QSS still draws item text — the painter would double it"

    centered = build(CenteredTextMenu)
    qtbot.addWidget(centered)
    centered_img = _grab(centered)
    for action in centered.actions():
        geo = centered.actionGeometry(action)
        assert _ink_bbox(centered_img, geo, palette["BACKGROUND_COLOR"]) is not None


def test_native_copy_rows_render_centered_text(qtbot, dark_palette, cell, open_menu):
    """THE requirement: the three «کپی تاریخ» entries and the title row render
    with visually centered text. Leaf rows: ink centered in the content rect.
    Title row: centered there too - one anchor for the whole column - never
    overlapping the self-painted arrow, which the tuck keeps clear of even a
    flush caption. Glyph color is the palette text color. (The old QSS
    rendering drew all of these left-aligned at the padding edge.)"""
    cell.setText("۵")
    palette = dark_palette
    bg = palette["BACKGROUND_COLOR"]
    menu = open_menu(cell)
    menu.popup(QPoint(10, 10))
    copy_menu = _copy_title_action(menu).menu()
    copy_menu.popup(QPoint(80, 10))

    # The painter inherits the QSS-applied menu font (applied at polish time,
    # i.e. once the popup is shown).
    assert menu.font().family() == APP_CONFIG.FONT_FAMILY
    assert menu.font().pixelSize() == 14
    assert menu.font().bold()

    img_copy = copy_menu.grab().toImage()
    for row in copy_menu.actions():
        if not row.text():
            continue  # the hairline separators; their QSS line is checked elsewhere
        geo = copy_menu.actionGeometry(row)
        # The pads deliberately differ (the leading one is the arrow column's
        # width), so the content rect - not the row - is the anchor: centered
        # ink sits half that pad difference right of the row's own centre,
        # uniformly for every row in the menu.
        content = _content_rect(geo)
        band = QRect(content.left(), geo.top(), content.width(), geo.height())
        ink = _ink_bbox(img_copy, band, bg)
        assert ink is not None, f"no text rendered for {row.text()}"
        assert abs(ink.center().x() - content.center().x()) <= 3, \
            f"{row.text()} not centered in the content rect: ink={ink} content={content}"
        assert ink.left() >= content.left() - 1 and ink.right() <= content.right() + 1, \
            f"{row.text()} left its content rect: ink={ink} content={content}"
        # vertical band unchanged vs the QSS-drawn text (same content box)
        assert abs(ink.center().y() - geo.center().y()) <= 3
        # glyph core is the palette TEXT_COLOR, not an invented color
        assert _close(_lightest_pixel(img_copy, ink), QColor(palette["TEXT_COLOR"]))

    # title row in the parent menu: text centers in the FULL content rect,
    # and the self-painted arrow sits clear of it in the leading padding
    # gutter (under RTL the arrow lives left of the content rect)
    img_menu = menu.grab().toImage()
    title_geo = menu.actionGeometry(_copy_title_action(menu))
    content = _content_rect(title_geo)
    gutter = QRect(title_geo.left(), title_geo.top(),
                   content.left() - title_geo.left(), title_geo.height())
    arrow = _ink_bbox(img_menu, gutter, bg)
    assert arrow is not None, "the self-painted submenu arrow vanished"
    text_zone_img = QRect(content.left(), title_geo.top(),
                          content.width(), title_geo.height())
    ink = _ink_bbox(img_menu, text_zone_img, bg)
    assert ink is not None, "title text did not render"
    assert ink.left() > arrow.right(), "title text overlaps the submenu arrow"
    assert abs(ink.center().x() - content.center().x()) <= 5, \
        f"title text not centered in the content rect: ink={ink} content={content}"
    menu.close()
    copy_menu.close()


def test_qt_own_submenu_indicator_stays_suppressed(qtbot, cell, open_menu):
    """The shared stylesheet zeroes Qt's own arrow subcontrols, so the row's
    only indicator is the tucked painted triangle. Left alone, the primitive
    lands in the strip right after it - inside the content rect, as a dark
    blob the palette does not own, beside the caption's ink."""
    cell.setText("۵")
    palette = APP_CONFIG.get_current_palette()
    bg = palette["BACKGROUND_COLOR"]
    menu = open_menu(cell)
    menu.popup(QPoint(10, 10))
    img_menu = menu.grab().toImage()

    title_geo = menu.actionGeometry(_copy_title_action(menu))
    content = _content_rect(title_geo)
    gutter = QRect(title_geo.left(), title_geo.top(),
                   content.left() - title_geo.left(), title_geo.height())
    arrow = _ink_bbox(img_menu, gutter, bg)
    assert arrow is not None, "the self-painted submenu arrow vanished"
    # The strip between the tucked arrow and the content edge - where a
    # revived primitive would land - must stay background.
    gap = QRect(arrow.right() + 1, title_geo.top(),
                content.left() - arrow.right() - 1, title_geo.height())
    assert gap.width() > 0, f"test setup: the arrow must clear the content edge: {gap}"
    assert _ink_bbox(img_menu, gap, bg) is None, "Qt's own submenu indicator is back"
    menu.close()


def test_hover_background_still_paints_under_centered_text(qtbot, cell, open_menu):
    """Hover is still the QSS rounded MENU_HOVER_COLOR fill — the painter only
    adds glyphs, so the hover composite must be pixel-identical to the
    QSS-only menu."""
    palette = APP_CONFIG.get_current_palette()
    hover = palette["MENU_HOVER_COLOR"]
    bg = QColor(palette["BACKGROUND_COLOR"])
    expected = QColor(
        round(hover[0] * hover[3] / 255 + bg.red() * (1 - hover[3] / 255)),
        round(hover[1] * hover[3] / 255 + bg.green() * (1 - hover[3] / 255)),
        round(hover[2] * hover[3] / 255 + bg.blue() * (1 - hover[3] / 255)))

    cell.setText("۵")
    menu = open_menu(cell)
    menu.popup(QPoint(10, 10))
    copy_menu = _copy_title_action(menu).menu()
    copy_menu.popup(QPoint(80, 10))
    copy_menu.setActiveAction(copy_menu.actions()[0])
    img = copy_menu.grab().toImage()
    menu.close()
    copy_menu.close()

    geo = copy_menu.actionGeometry(copy_menu.actions()[0])
    sample = img.pixelColor(geo.center().x(), geo.top() + 2)  # inside the fill, above glyphs
    assert _close(sample, expected, tol=6), \
        f"hover fill changed: {sample.name()} vs {expected.name()}"


def test_disabled_rows_still_render_visible_grey_text(qtbot, dark_palette):
    """QSS item text is transparent even for disabled rows, so the painter
    must supply the grey there — a disabled row stays visible, never blank."""
    palette = dark_palette
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    disabled = m.addAction("خاموش")
    disabled.setEnabled(False)
    img = _grab(m)
    geo = m.actionGeometry(disabled)
    ink = _ink_bbox(img, geo, palette["BACKGROUND_COLOR"])
    assert ink is not None, "disabled row rendered blank"
    assert _close(_lightest_pixel(img, ink), QColor(palette["GREY_COLOR"]))


def test_centered_painter_paints_the_arrow_in_the_gutter_ltr_too(qtbot, dark_palette):
    """Direction-aware indicator handling: under LTR the self-painted arrow
    sits in the trailing padding gutter (right of the content rect), its ink
    never touches the caption, and the caption keeps all of its glyphs inside
    the content rect.

    Centering itself is direction-agnostic - every caption centers on its
    content rect - so this test pins what direction must not change: the arrow
    is drawn in the trailing gutter in the row's text color, it costs the
    caption neither its box nor its glyphs, and Qt's own suppressed indicator
    does not come back beside it."""
    palette = dark_palette
    bg = palette["BACKGROUND_COLOR"]
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    sub = m.addMenu("کپی تاریخ")
    sub.addAction("هر دو")
    # Room for the caption inside its content rect. Without it this row
    # slides into the clipped overhang path, which has its own test.
    m.setMinimumWidth(200)
    img = _grab(m)

    title_geo = m.actionGeometry(next(a for a in m.actions() if a.menu() is not None))
    content = _content_rect(title_geo, rtl=False)
    # The arrow lives in the trailing padding gutter (right of the content
    # rect under LTR); the text must stay inside the content rect.
    gutter = QRect(content.right() + 1, title_geo.top(),
                   title_geo.right() - content.right(), title_geo.height())
    arrow = _ink_bbox(img, gutter, bg)
    assert arrow is not None, "LTR submenu arrow vanished"
    text_zone_img = QRect(content.left(), title_geo.top(),
                          content.width(), title_geo.height())
    ink = _ink_bbox(img, text_zone_img, bg)
    assert ink is not None, "title text did not render"
    assert ink.right() < arrow.left(), "LTR title text overlaps the submenu arrow"
    assert ink.left() >= content.left() and ink.right() <= content.right(), \
        f"LTR caption left its content rect: ink={ink} content={content}"
    # Not clipped: the ink covers the caption's own advance (the ink box is a
    # couple of pixels narrower than it), so no glyph fell off the row.
    advance = QFontMetrics(m.font()).horizontalAdvance(sub.title())
    assert advance - ink.width() <= 4, \
        f"LTR caption is clipped: advance={advance} ink={ink}"
    # With Qt's own indicator suppressed by the shared stylesheet, the strip
    # between the content rect and the painted arrow holds no ink.
    gap = QRect(content.right() + 1, title_geo.top(),
                arrow.left() - content.right() - 1, title_geo.height())
    assert gap.width() > 0, f"test setup: the arrow must clear the content edge: {gap}"
    assert _ink_bbox(img, gap, bg) is None, "Qt's own submenu indicator is back"
    # the indicator uses the row's own text color, not an invented one
    assert _close(_lightest_pixel(img, arrow), QColor(palette["TEXT_COLOR"]))


def test_row_filling_submenu_title_renders_complete(qtbot, dark_palette):
    """The reported regression: a submenu title whose caption exactly fills
    its row («ویرایش رویداد» on a multi-event day) must render EVERY glyph.
    Such a caption is centered on its content rect and rides flush by
    construction - an earlier clip to a 14px-tighter zone once cut it down to
    «رایش». QMenu sizes a row to its own caption, so the real day menu
    reliably produces this exact-width shape offscreen too."""
    palette = dark_palette
    bg = palette["BACKGROUND_COLOR"]
    caption = "ویرایش رویداد"
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    sub = m.addMenu(caption)
    sub.addAction("رویداد یک")
    m.popup(QPoint(30, 30))
    img = m.grab().toImage()
    m.close()

    title_geo = m.actionGeometry(next(a for a in m.actions() if a.menu() is not None))
    content = _content_rect(title_geo)
    # The arrow still lives in the leading padding gutter (RTL).
    gutter = QRect(title_geo.left(), title_geo.top(),
                   content.left() - title_geo.left(), title_geo.height())
    arrow = _ink_bbox(img, gutter, bg)
    assert arrow is not None, "the self-painted submenu arrow vanished"
    text_zone_img = QRect(content.left(), title_geo.top(),
                          content.width(), title_geo.height())
    ink = _ink_bbox(img, text_zone_img, bg)
    assert ink is not None, "title text did not render"
    advance = QFontMetrics(m.font()).horizontalAdvance(caption)
    # Complete: the ink covers the caption's own advance (tolerated bearings),
    # flush against the content edges and uncut.
    assert advance - ink.width() <= 4, \
        f"row-filling title is clipped: advance={advance} ink={ink}"
    assert abs(ink.center().x() - content.center().x()) <= 5, \
        f"title not centered on the content anchor: ink={ink} content={content}"
    # Content-clipped, so no glyph can reach the arrow's gutter.
    assert ink.left() >= content.left() - 1, f"ink escaped the content rect: {ink}"


def test_row_filling_title_clears_the_tucked_arrow(qtbot, dark_palette):
    """The cramped feel came from geometry QMenu leaves no control over: the
    widest caption defines its row, so its ink rides flush against the content
    edge every time. The arrow leans inside its own leading column now - a 26px
    leading pad against the 16px trailing one - so that flush ink keeps the
    column's slack: the arrow's ink ends short of the column's middle and the
    content edge waits beyond it."""
    palette = dark_palette
    bg = palette["BACKGROUND_COLOR"]
    caption = "ویرایش رویداد"
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    sub = m.addMenu(caption)
    sub.addAction("رویداد یک")
    m.popup(QPoint(30, 30))
    img = m.grab().toImage()
    m.close()

    title_geo = m.actionGeometry(next(a for a in m.actions() if a.menu() is not None))
    content = _content_rect(title_geo)
    advance = QFontMetrics(m.font()).horizontalAdvance(caption)
    assert content.width() == advance, \
        f"test setup: the title must fill its row: content={content} advance={advance}"
    gutter = QRect(title_geo.left(), title_geo.top(),
                   content.left() - title_geo.left(), title_geo.height())
    arrow = _ink_bbox(img, gutter, bg)
    assert arrow is not None, "the self-painted submenu arrow vanished"
    text_zone_img = QRect(content.left(), title_geo.top(),
                          content.width(), title_geo.height())
    ink = _ink_bbox(img, text_zone_img, bg)
    assert ink is not None, "title text did not render"
    # The ride-flush-caption clearance the arrow column exists to provide: a
    # row-filling title comfortably clears the indicator and true spare-width
    # titles clear it by far more.
    gap = ink.left() - arrow.right()
    assert gap >= 10, \
        f"the arrow column failed to keep a flush title clear: gap={gap}"


def test_overlong_title_clips_to_the_content_rect(qtbot, monkeypatch):
    """Safety net for captions genuinely wider than their row: the glyphs are
    centered on and clipped to the FULL content rect - the plain rows' own
    target - so they can never run under the tucked indicator, and the
    overhang sheds only what the row cannot hold. Natural menus always size
    their rows past their captions, so the too-narrow row is injected through
    the geometry query - the only way to pin this painter branch
    deterministically."""
    palette = APP_CONFIG.get_current_palette()
    bg = palette["BACKGROUND_COLOR"]
    caption = "کپی تاریخ و زمان"
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(centered_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    sub = m.addMenu(caption)
    sub.addAction("هر دو")
    m.popup(QPoint(30, 30))

    real_geometry = QMenu.actionGeometry  # unbound; the fake delegates to it

    def narrowed(self, action):
        rect = real_geometry(self, action)
        if action.menu() is not None:
            rect.setRight(rect.right() - 40)  # a row far narrower than its caption
        return rect

    monkeypatch.setattr(QMenu, "actionGeometry", narrowed)
    img = m.grab().toImage()
    m.close()

    title_geo = m.actionGeometry(next(a for a in m.actions() if a.menu() is not None))
    content = _content_rect(title_geo, rtl=False)
    advance = QFontMetrics(m.font()).horizontalAdvance(caption)
    assert advance > content.width(), "test setup: the injected row must overflow"
    gutter = QRect(content.right() + 1, title_geo.top(),
                   title_geo.right() - content.right(), title_geo.height())
    arrow = _ink_bbox(img, gutter, bg)
    assert arrow is not None, "LTR submenu arrow vanished"
    text_zone_img = QRect(content.left(), title_geo.top(),
                          content.width(), title_geo.height())
    ink = _ink_bbox(img, text_zone_img, bg)
    assert ink is not None, "overflow title text did not render"
    assert ink.right() < arrow.left(), "overflow glyphs reached the arrow gutter"
    # The clip anchors on the content rect (the plain rows' rule): the
    # tuned trims only place captions that fit them, they never ration glyphs.
    assert abs(ink.center().x() - content.center().x()) <= 5, \
        f"overflow text not centered in the content rect: ink={ink} content={content}"


def test_copy_submenu_has_no_custom_mouse_intercepting_widget(qtbot, cell, open_menu):
    """Regression guard: the title row and every submenu row are plain QActions
    — no widget that intercepts mouse events, and no click-fallback path."""
    cell.setText("۵")
    menu = open_menu(cell)
    title_action = _copy_title_action(menu)
    assert not isinstance(title_action, QWidgetAction)
    assert title_action.menu() is not None  # Qt's own submenu hook
    for row in title_action.menu().actions():
        assert not isinstance(row, QWidgetAction)
        assert row.menu() is None
    # The manual hover/click fallback is gone from the widget's API.
    assert not hasattr(cell, "_show_copy_submenu_fallback")


def test_copy_requires_a_jalali_date(qtbot, cell):
    """Defensive guard: without a date the copy path is a no-op, not a crash."""
    cell.setText("۵")
    cell.jalali_date = None
    menu = QMenu()
    qtbot.addWidget(menu)
    action = menu.addAction("تاریخ شمسی")
    clipboard = QApplication.clipboard()
    before = clipboard.text()
    cell._copy_date_and_close(menu, "jalali", action)
    assert clipboard.text() == before
    assert not menu.isVisible()  # the menu is still closed first


# --- فاصله تا امروز ------------------------------------------------------------------


def _distance_action(menu: QMenu):
    """The «فاصله تا امروز» row, which is a custom-widget action like the event rows."""
    return next(a for a in menu.actions()
                if hasattr(a, "defaultWidget") and a.defaultWidget() is not None
                and hasattr(a.defaultWidget(), "label")
                and a.defaultWidget().label.text() == DISTANCE_ACTION_TEXT)


def _distance_widget(menu: QMenu):
    return _distance_action(menu).defaultWidget()


def test_context_menu_offers_the_distance_action_in_its_own_group(qtbot, cell, open_menu):
    """The row reads as a separate kind of row rather than another copy format:
    a separator on each side keeps it off the «کپی تاریخ» submenu even though the
    two now sit next to each other in the reading order."""
    cell.setText("۱")
    menu = open_menu(cell)
    rows = menu.actions()
    distance = _distance_action(menu)
    assert isinstance(distance, QWidgetAction)
    index = rows.index(distance)
    assert rows[index - 1].isSeparator()
    assert rows[index + 1].isSeparator()
    # The copy submenu is the row directly above that first separator.
    assert rows[index - 2] is _copy_title_action(menu)


def test_distance_action_is_enabled_even_without_a_user_event(qtbot, cell, open_menu):
    """Asking how far away a day is has nothing to do with whether it has an
    event, so this row stays live on a plain day."""
    cell.setText("۵")
    cell.has_user_event = False
    menu = open_menu(cell)
    assert _distance_widget(menu).isEnabled() is True


def test_distance_action_emits_the_right_clicked_day(qtbot, cell, open_menu):
    cell.setText("۵")
    received = []
    cell.distance_requested.connect(lambda j: received.append(j))
    menu = open_menu(cell)
    _distance_widget(menu).triggered.emit()
    qtbot.wait(100)  # the deferred singleShot
    assert received == [cell.jalali_date]


def test_distance_emission_is_delayed_until_menu_gone(cell, qtbot):
    """The notice opens a modal dialog, which must not appear while the menu
    still holds its mouse grab."""
    received = []
    cell.distance_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._emit_after_menu_close(menu, cell.distance_requested, cell.jalali_date)
    assert menu.closed
    assert received == []
    qtbot.wait(100)
    assert received == [cell.jalali_date]
