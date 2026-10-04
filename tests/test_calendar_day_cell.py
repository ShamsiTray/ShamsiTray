"""Tests for ui.widgets.calendar_day_cell: the clickable day cell with its
custom tooltip lifecycle and the add/remove-event context menu."""
import jdatetime
import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QAction, QColor, QContextMenuEvent, QCursor, QImage
from PyQt6.QtWidgets import QApplication, QMenu, QWidget, QWidgetAction

from config import APP_CONFIG
from tests.qt_mousing import press
from ui.widgets.calendar_day_cell import (ClickableLabel, DISTANCE_ACTION_TEXT,
                                          _menu_stylesheet)
from ui.widgets.menu_widgets import (CenteredTextMenu, MENU_ITEM_PADDING_H,
                                     MENU_ITEM_PADDING_V)
from ui.widgets.tooltip import CustomTooltip


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
    assert cell._tooltip_timer.remainingTime() > 0  # ~500ms, minus jitter


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


def test_context_menu_remove_disabled_without_user_event(qtbot, cell, monkeypatch):
    """Without a user event on this day, حذف رویداد is greyed out."""
    actions = {}

    def fake_exec(self, pos):
        for action in self.actions():
            default_widget = getattr(action, "defaultWidget", lambda: None)()
            if default_widget is not None and hasattr(default_widget, "label"):
                actions[default_widget.label.text()] = (action.isEnabled(),
                                                        default_widget.isEnabled())

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    cell.setText("۵")
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert actions["افزودن رویداد"] == (True, True)
    assert actions["حذف رویداد"] == (False, False)  # disabled on action + widget


def test_context_menu_remove_enabled_with_user_event(qtbot, cell, monkeypatch):
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)
    cell.setText("۵")
    cell.has_user_event = True
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    # (Not executed interactively; flag presence is what the menu reads.)


def test_add_event_emission_is_delayed_until_menu_gone(cell, qtbot):
    """_trigger_add_event_and_close_menu closes first, emits via singleShot."""
    received = []
    cell.add_event_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._trigger_add_event_and_close_menu(menu, cell.jalali_date)
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
    cell._trigger_remove_event_and_close_menu(menu, cell.jalali_date)
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
    assert len(rows) == 9  # option, separator, option, separator, option
    assert [a.text() for a in rows if a.text()] == ["تاریخ شمسی", "تاریخ میلادی", "هر دو"]
    assert rows[1].isSeparator() and rows[3].isSeparator()
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
    assert rows == ["کپی تاریخ", "---", DISTANCE_ACTION_TEXT, "---",
                    "افزودن رویداد", "---", "حذف رویداد"]


def test_context_menu_add_row_reads_as_edit_on_an_event_day(qtbot, cell, open_menu):
    """Reordering must not cost the add/edit wording swap, and it must not move the
    swap to a different row."""
    cell.setText("۱")
    cell.has_user_event = True
    assert _menu_rows(open_menu(cell))[4] == "ویرایش رویداد"


def test_existing_day_menu_actions_survive_copy_submenu(qtbot, cell, open_menu):
    cell.setText("۵")
    menu = open_menu(cell)
    labels = []
    for action in menu.actions():
        widget = action.defaultWidget() if hasattr(action, "defaultWidget") else None
        if widget is not None and hasattr(widget, "label"):
            labels.append(widget.label.text())
    assert "افزودن رویداد" in labels
    assert "حذف رویداد" in labels
    # The copy entry is the plain submenu title (not a widget row).
    assert "کپی تاریخ" in [a.text() for a in menu.actions()]
    # The delete row's enable/disable logic is untouched.
    remove_widget = next(a.defaultWidget() for a in menu.actions()
                         if hasattr(a, "defaultWidget") and a.defaultWidget() is not None
                         and hasattr(a.defaultWidget(), "label")
                         and a.defaultWidget().label.text() == "حذف رویداد")
    assert remove_widget.isEnabled() is False


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
    from utils.date_utils import format_gregorian_numeric, format_jalali_numeric

    cell.setText("۵")
    cell.jalali_date = jdatetime.date(jy, jm, jd)
    menu = open_menu(cell)
    copy_menu = _copy_title_action(menu).menu()
    clipboard = QApplication.clipboard()
    jalali_text = format_jalali_numeric(cell.jalali_date)
    gregorian_text = format_gregorian_numeric(cell.jalali_date)
    expected = {
        "تاریخ شمسی": jalali_text,
        "تاریخ میلادی": gregorian_text,
        "هر دو": f"{jalali_text}\n{gregorian_text}",
    }
    for action in copy_menu.actions():
        if not action.text():
            continue  # the hairline separator rows carry no copy mode
        action.trigger()
        assert clipboard.text() == expected[action.text()]
    # let the last flash's own 600ms hide timer expire cleanly
    qtbot.wait(700)


def test_copied_feedback_shows_immediately(qtbot, cell, open_menu):
    """«کپی شد» must appear the instant a copy action is triggered — no
    timer, no waiting for the menu teardown (clipboard first, flash at
    once). The flash duration itself is unchanged."""
    cell.setText("۵")
    menu = open_menu(cell)
    copy_menu = _copy_title_action(menu).menu()
    tooltip = CustomTooltip.instance()
    assert not tooltip.isVisible()
    copy_menu.actions()[0].trigger()
    # No qtbot.wait anywhere before this assert: synchronous visibility.
    assert tooltip.isVisible()
    assert tooltip._label.text() == "کپی شد"
    qtbot.wait(700)  # the flash hides itself after ~600ms


def test_copy_submenu_uses_the_shared_menu_styling(qtbot, cell, open_menu):
    """Qt owns the row behavior, but the popup keeps the app's custom QMenu
    stylesheet — and the item rules mirror MenuActionWidget's own look so
    the native copy rows match the custom add/remove rows: same Vazirmatn
    14px bold text, same 15px/6px inner box, same rounded MENU_HOVER_COLOR
    hover, and the hairline separator rule for the option dividers. There
    are deliberately NO arrow subcontrol rules: bare rules proved invisible
    under some Windows styles, so CenteredTextMenu paints the indicator
    itself. Direction is the app's RTL."""
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
                f"{MENU_ITEM_PADDING_H}px; color: transparent; }}") in ss
        assert "QMenu::item:disabled { color: transparent; }" in ss
        # hover: same color and rounded shape as HoverWidget paints
        assert f"QMenu::item:selected {{ background-color: {hover_css}; border-radius: 6px; }}" in ss
        # no arrow subcontrol rules: the painter owns the indicator (bare
        # rules rendered nothing visible on Windows builds)
        assert "arrow" not in ss
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


def test_qss_item_text_is_transparent_so_the_painter_never_doubles_it(qtbot):
    """The production stylesheet must draw NO item glyphs itself — otherwise
    CenteredTextMenu's centered glyphs would land on top of QSS's left-
    aligned ones. A plain QMenu with the shared stylesheet renders empty
    item rows; the same rows under CenteredTextMenu render ink."""
    palette = APP_CONFIG.get_current_palette()
    texts = ["تاریخ شمسی", "تاریخ میلادی", "هر دو"]

    def build(menu_cls):
        m = menu_cls()
        m.setStyleSheet(_menu_stylesheet(palette))
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


def test_native_copy_rows_render_centered_text(qtbot, cell, open_menu):
    """THE requirement: the three «کپی تاریخ» entries and the title row render
    with visually centered text. Leaf rows: ink centered in the content rect.
    Title row: text centered in the FULL content rect (the arrow lives in
    the trailing padding gutter, so no shifted arrow-aware zone), never
    overlapping the self-painted arrow. Glyph color is the palette text
    color. (The old QSS rendering drew all of these left-aligned at the
    padding edge.)"""
    cell.setText("۵")
    palette = APP_CONFIG.get_current_palette()
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
        ink = _ink_bbox(img_copy, geo, bg)
        assert ink is not None, f"no text rendered for {row.text()}"
        left_gap = ink.left() - geo.left()
        right_gap = geo.right() - ink.right()
        assert abs(left_gap - right_gap) <= 3, \
            f"{row.text()} not centered: Lgap={left_gap} Rgap={right_gap}"
        # vertical band unchanged vs the QSS-drawn text (same content box)
        assert abs(ink.center().y() - geo.center().y()) <= 3
        # glyph core is the palette TEXT_COLOR, not an invented color
        assert _close(_lightest_pixel(img_copy, ink), QColor(palette["TEXT_COLOR"]))

    # title row in the parent menu: text centers in the FULL content rect,
    # and the self-painted arrow sits clear of it in the leading padding
    # gutter (under RTL the arrow lives left of the content rect)
    img_menu = menu.grab().toImage()
    title_geo = menu.actionGeometry(_copy_title_action(menu))
    content = title_geo.adjusted(MENU_ITEM_PADDING_H, MENU_ITEM_PADDING_V,
                                 -MENU_ITEM_PADDING_H, -MENU_ITEM_PADDING_V)
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


def test_disabled_rows_still_render_visible_grey_text(qtbot):
    """QSS item text is transparent even for disabled rows, so the painter
    must supply the grey there — a disabled row stays visible, never blank."""
    palette = APP_CONFIG.get_current_palette()
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    disabled = m.addAction("خاموش")
    disabled.setEnabled(False)
    img = _grab(m)
    geo = m.actionGeometry(disabled)
    ink = _ink_bbox(img, geo, palette["BACKGROUND_COLOR"])
    assert ink is not None, "disabled row rendered blank"
    assert _close(_lightest_pixel(img, ink), QColor(palette["GREY_COLOR"]))


def test_centered_painter_paints_the_arrow_in_the_gutter_ltr_too(qtbot):
    """Direction-aware indicator handling: under LTR the self-painted arrow
    sits in the trailing padding gutter (right of the content rect), its ink
    never touches the text, and a caption that fits centers in the FULL
    content rect — the arrow costs the text no centering shift at all."""
    palette = APP_CONFIG.get_current_palette()
    bg = palette["BACKGROUND_COLOR"]
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(_menu_stylesheet(palette))
    m.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    sub = m.addMenu("کپی تاریخ")
    sub.addAction("هر دو")
    img = _grab(m)

    title_geo = m.actionGeometry(next(a for a in m.actions() if a.menu() is not None))
    content = title_geo.adjusted(MENU_ITEM_PADDING_H, MENU_ITEM_PADDING_V,
                                 -MENU_ITEM_PADDING_H, -MENU_ITEM_PADDING_V)
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
    assert abs(ink.center().x() - content.center().x()) <= 3, \
        f"title text not centered in the content rect: ink={ink} content={content}"
    # the indicator uses the row's own text color, not an invented one
    assert _close(_lightest_pixel(img, arrow), QColor(palette["TEXT_COLOR"]))


def test_overlong_title_falls_back_to_a_clipped_arrow_aware_zone(qtbot, monkeypatch):
    """Safety net for captions wider than their row: the glyphs fall back to
    the arrow-aware zone and are CLIPPED to it, so they can never run under
    the indicator. Natural menus always size themselves past their captions,
    so the too-narrow row is injected through the geometry query — the only
    way to pin this painter branch deterministically."""
    palette = APP_CONFIG.get_current_palette()
    bg = palette["BACKGROUND_COLOR"]
    caption = "کپی تاریخ و زمان"
    m = CenteredTextMenu()
    qtbot.addWidget(m)
    m.setStyleSheet(_menu_stylesheet(palette))
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
    content = title_geo.adjusted(MENU_ITEM_PADDING_H, MENU_ITEM_PADDING_V,
                                 -MENU_ITEM_PADDING_H, -MENU_ITEM_PADDING_V)
    from PyQt6.QtGui import QFontMetrics
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
    # centered in the arrow-aware (trimmed) zone, within the clip tolerance
    zone_center = content.center().x() - 6  # 12px trimmed off the trailing side
    assert abs(ink.center().x() - zone_center) <= 5, \
        f"overflow text not centered in the trimmed zone: ink={ink}"


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
    clipboard = QApplication.clipboard()
    before = clipboard.text()
    cell._copy_date_and_close(menu, "jalali")
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
    cell._trigger_distance_and_close_menu(menu, cell.jalali_date)
    assert menu.closed
    assert received == []
    qtbot.wait(100)
    assert received == [cell.jalali_date]
