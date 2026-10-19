"""Tests for utils.ui_helpers: rounded-card painting, the frameless drag
mixin (shared by every frameless surface), tray pixmaps, combo fitting and
the shared stylesheet builders."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import QComboBox, QWidget

from config import APP_CONFIG
from tests.qt_mousing import press, release
from utils.ui_helpers import (MENU_EDGE_MARGIN, DigitsFirstCombo, FramelessDragMixin,
                              accent_button_stylesheet, center_combo_items,
                              clamp_popup_to_work_area, combo_stylesheet,
                              create_tray_pixmap, danger_button_stylesheet,
                              error_line_edit_stylesheet, fit_combo_width,
                              ghost_button_stylesheet, line_edit_stylesheet,
                              nudge_popup_inside_work_area, paint_rounded_card,
                              scrollbar_stylesheet,
                              window_title_button_stylesheets)


@pytest.fixture
def palette():
    return APP_CONFIG.get_current_palette()


# --- paint_rounded_card -------------------------------------------------------

def test_paint_rounded_card_returns_inset_path(qtbot):
    from PyQt6.QtGui import QPainter
    pixmap = QPixmap(60, 40)
    pixmap.fill(Qt.GlobalColor.white)
    painter = QPainter(pixmap)
    path = paint_rounded_card(painter, pixmap.rect(), "#2c2c2c", "#3B3B3B", 8)
    painter.end()
    assert not path.isEmpty()
    # The card is inset by 1px on each side so the border is never clipped.
    # (Qt6 QRectF.right() == left + width.)
    assert path.boundingRect().left() == 1.0
    assert path.boundingRect().top() == 1.0
    assert path.boundingRect().width() == 58.0
    assert path.boundingRect().height() == 38.0


# --- FramelessDragMixin ---------------------------------------------------------

class DragSurface(FramelessDragMixin, QWidget):
    """Minimal mixin host: whole-surface draggable, fully keep-visible clamp."""


def _surface(qtbot) -> DragSurface:
    surface = DragSurface()
    surface.resize(120, 80)
    qtbot.addWidget(surface)
    surface.show()
    surface.move(200, 200)
    return surface


def _pin_screen(monkeypatch, virtual, available):
    """Pin the screen lookup to a known desktop/work area, so the clamp maths is
    assertable (and the taskbar strip is 40px wherever CI runs).

    ``virtualGeometry`` is the whole desktop, taskbar strip included;
    ``availableVirtualGeometry`` is the work area the dialog clamp respects.
    """
    from PyQt6.QtWidgets import QApplication

    class FakeScreen:
        def virtualGeometry(self):
            return virtual

        def availableVirtualGeometry(self):
            return available

    monkeypatch.setattr(QApplication, "primaryScreen", staticmethod(lambda: FakeScreen()))


def test_drag_press_ignores_non_left_button(qtbot):
    surface = _surface(qtbot)
    event = press(surface, button=Qt.MouseButton.RightButton)
    assert surface.handle_drag_press(event) is False
    assert surface._drag_position is None


def test_drag_press_starts_drag_on_left_button(qtbot):
    surface = _surface(qtbot)
    event = press(surface, local=(10, 10))
    assert surface.handle_drag_press(event) is True
    assert surface._drag_position is not None
    assert event.isAccepted()


def test_drag_move_without_press_is_ignored(qtbot):
    surface = _surface(qtbot)
    event = press(surface)
    assert surface.handle_drag_move(event) is False


def test_drag_move_shifts_window_by_cursor_delta(qtbot):
    surface = _surface(qtbot)
    start = QPoint(surface.x(), surface.y())
    surface.handle_drag_press(press(surface, local=(10, 10)))
    # Move the cursor 30px right / 20px down from where the press landed.
    press_global = surface.mapToGlobal(QPoint(10, 10))
    target_global = press_global + QPoint(30, 20)
    event = press(surface, local=(10, 10), global_pos=target_global)
    event = type(event)(  # rebuild as a genuine move event
        __import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent.Type.MouseMove,
        QPointF(10, 10), QPointF(target_global),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    assert surface.handle_drag_move(event) is True
    assert QPoint(surface.x(), surface.y()) == start + QPoint(30, 20)


def test_drag_move_clamps_inside_screen(qtbot):
    """The dragged window is clamped to the desktop while it is pushed past the
    edge; on the single-screen offscreen desktop that is the geometry the
    primary screen reports, available area included."""
    from PyQt6.QtWidgets import QApplication
    surface = _surface(qtbot)
    surface.handle_drag_press(press(surface, local=(10, 10)))
    geo = QApplication.primaryScreen().availableGeometry()
    # Cursor near the screen's bottom-right, still on screen; the window
    # (120x80) follows it and must be clamped fully inside.
    cursor = QPoint(geo.right() - 5, geo.bottom() - 5)
    event = press(surface, local=(10, 10), global_pos=cursor)
    event = type(event)(
        __import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent.Type.MouseMove,
        QPointF(10, 10), QPointF(cursor),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    surface.handle_drag_move(event)
    assert surface.x() <= geo.right() - surface.width()
    assert surface.y() == geo.bottom() - surface.height()  # keep_visible=None


def test_drag_move_clamps_against_the_whole_desktop(qtbot, monkeypatch):
    """The clamp anchored on the screen under the cursor, so the moment the
    cursor crossed into the next monitor the window teleported to that screen's
    left edge even while the window itself was still mostly on the first one.
    It must span the virtual desktop instead."""
    from PyQt6.QtCore import QEvent, QRect

    desktop = QRect(0, 0, 3000, 1000)
    _pin_screen(monkeypatch, desktop, desktop)

    surface = _surface(qtbot)
    surface.handle_drag_press(press(surface, local=(10, 10)))
    # Far to the right of the single real screen: the desktop, not the screen
    # under the cursor, decides where the window may land.
    cursor = QPoint(5000, 500)
    event = type(press(surface, local=(10, 10), global_pos=cursor))(
        QEvent.Type.MouseMove, QPointF(10, 10), QPointF(cursor),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    surface.handle_drag_move(event)

    assert surface.x() == 2999 - surface.width()  # desktop right() is inclusive


def test_drag_move_keeps_a_dialog_above_the_taskbar(qtbot, monkeypatch):
    """``virtualGeometry`` includes the taskbar strip, so a dialog clamped
    "fully on screen" could still come to rest with its bottom buttons behind
    the taskbar. The work area is where fully visible has to stop."""
    from PyQt6.QtCore import QEvent, QRect

    # A 1000x800 desktop with a 40px taskbar along its bottom edge.
    _pin_screen(monkeypatch, QRect(0, 0, 1000, 800), QRect(0, 0, 1000, 760))

    surface = _surface(qtbot)          # drag_bottom_keep_visible is None
    surface.handle_drag_press(press(surface, local=(10, 10)))
    cursor = QPoint(500, 9999)
    event = type(press(surface, local=(10, 10), global_pos=cursor))(
        QEvent.Type.MouseMove, QPointF(10, 10), QPointF(cursor),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    surface.handle_drag_move(event)

    assert surface.y() == 759 - surface.height()  # the work area's bottom, not 799


def test_drag_move_leaves_the_tool_window_clamp_on_the_desktop(qtbot, monkeypatch):
    """The tool windows may hang below the bottom edge on purpose - only their
    top 50px must stay reachable - so the taskbar strip is theirs to use and
    their clamp keeps the whole desktop."""
    from PyQt6.QtCore import QEvent, QRect

    class ToolWindow(DragSurface):
        drag_bottom_keep_visible = 50

    _pin_screen(monkeypatch, QRect(0, 0, 1000, 800), QRect(0, 0, 1000, 760))

    surface = ToolWindow()
    qtbot.addWidget(surface)
    surface.resize(300, 400)
    surface.show()
    surface.move(200, 200)
    surface.handle_drag_press(press(surface, local=(10, 10)))
    cursor = QPoint(500, 9999)
    event = type(press(surface, local=(10, 10), global_pos=cursor))(
        QEvent.Type.MouseMove, QPointF(10, 10), QPointF(cursor),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    surface.handle_drag_move(event)

    assert surface.y() == 799 - 50  # the desktop's bottom edge, not the work area's


def test_drag_release_ends_drag(qtbot):
    surface = _surface(qtbot)
    surface.handle_drag_press(press(surface))
    assert surface.handle_drag_release(release(surface)) is True
    assert surface._drag_position is None
    assert surface.handle_drag_move(press(surface)) is False  # no longer dragging


def test_drag_strip_height_restricted_to_top_band(qtbot):
    class StripWindow(DragSurface):
        drag_strip_height = 40

    surface = StripWindow()
    qtbot.addWidget(surface)
    surface.resize(200, 300)
    surface.show()
    # Press below the 40px strip: not a drag.
    below = press(surface, local=(100, 60))
    assert surface.handle_drag_press(below) is False
    # Press inside the strip: drag starts.
    inside = press(surface, local=(100, 20))
    assert surface.handle_drag_press(inside) is True


def test_base_window_keep_visible_clamp_holds_top_visible(qtbot):
    """The tool-window rule: only the top 50px must stay on screen."""
    from PyQt6.QtCore import QEvent
    from ui.windows.base_window import BaseFramelessWindow

    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.resize(300, 400)
    window.show()
    window.move(200, 200)
    geo = window.screen().availableGeometry()
    window.handle_drag_press(press(window, local=(10, 10)))
    # Cursor stays on screen near the bottom edge; the 400px-tall window
    # chasing it is clamped so its top 50px remain visible.
    cursor = QPoint(geo.center().x(), geo.bottom() - 2)
    event = press(window, local=(10, 10), global_pos=cursor)
    event = type(event)(
        QEvent.Type.MouseMove, QPointF(10, 10), QPointF(cursor),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    window.handle_drag_move(event)
    # y_max = geo.bottom() - keep_visible(50): the top 50px stay visible.
    assert window.y() == geo.bottom() - 50


# --- create_tray_pixmap ---------------------------------------------------------

def test_create_tray_pixmap_draws_day_text():
    pixmap = create_tray_pixmap("۱۴", "#FFFFFF")
    assert not pixmap.isNull()
    assert pixmap.width() in (36, 38)  # DPI-dependent icon size
    image = pixmap.toImage()
    painted = 0
    for x in range(0, image.width(), 2):
        for y in range(0, image.height(), 2):
            if (image.pixel(x, y) >> 24) & 0xFF > 0:  # QRgb alpha byte
                painted += 1
    assert painted > 0, "the day number must be painted onto the pixmap"


# --- combo helpers ---------------------------------------------------------------

def test_center_combo_items_sets_alignment_role():
    combo = QComboBox()
    for item in ("a", "b", "c"):
        combo.addItem(item)
    center_combo_items(combo)
    role = Qt.ItemDataRole.TextAlignmentRole
    expected = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    for i in range(combo.count()):
        assert int(combo.itemData(i, role)) == expected


def test_center_combo_items_empty_combo_is_noop():
    combo = QComboBox()
    center_combo_items(combo)  # must not raise


def test_digits_first_combo_pins_popup_to_rtl():
    combo = DigitsFirstCombo()
    combo.addItem("۰۶ - شهریور")
    combo.showPopup()
    assert combo.view().layoutDirection() == Qt.LayoutDirection.RightToLeft
    combo.hidePopup()


def test_digits_first_combo_paints_offscreen(qtbot):
    combo = DigitsFirstCombo()
    combo.addItem("۰۶ - شهریور")
    qtbot.addWidget(combo)
    combo.resize(120, 30)
    pixmap = combo.grab()
    assert not pixmap.isNull()


def test_fit_combo_width_enforces_widest_item():
    combo = QComboBox()
    items = ["۱۲۳۴", "کلمه‌ی-بلند-برای-سنجش", "x"]
    for item in items:
        combo.addItem(item)
    font = QFont(APP_CONFIG.FONT_FAMILY)
    font.setPixelSize(14)
    metrics = QFontMetrics(font)
    widest = max(metrics.horizontalAdvance(t) for t in items)
    fit_combo_width(combo, font_size=14)
    assert combo.minimumWidth() == int(widest * 1.12) + 46
    assert combo.view().minimumWidth() == combo.minimumWidth()


def test_fit_combo_width_empty_combo_untouched():
    combo = QComboBox()
    fit_combo_width(combo)
    assert combo.minimumWidth() == 0  # default untouched


# --- stylesheet builders ----------------------------------------------------------

def test_accent_button_stylesheet_states(palette):
    style = accent_button_stylesheet(palette, font_size=16)
    base = QColor(palette["ACCENT_COLOR"])
    assert base.name() in style
    assert base.lighter(110).name() in style   # hover
    assert base.darker(120).name() in style    # pressed
    assert "QPushButton:disabled" in style
    assert "font-size: 16px" in style
    assert APP_CONFIG.FONT_FAMILY in style


def test_ghost_button_stylesheet_outline_with_accent_hover(palette):
    style = ghost_button_stylesheet(palette)
    assert "background-color: transparent" in style
    assert palette["CALENDAR_BORDER_COLOR"] in style
    assert palette["ACCENT_COLOR"] in style


def test_danger_button_stylesheet_uses_holiday_color(palette):
    style = danger_button_stylesheet(palette)
    base = QColor(palette["HOLIDAY_COLOR"])
    assert base.darker(120).name() in style  # base fill
    assert base.darker(110).name() in style  # hover


def test_scrollbar_stylesheet_shape_and_hover(palette):
    style = scrollbar_stylesheet(palette)
    assert "QScrollBar:vertical" in style
    assert "width: 10px" in style
    assert "min-height: 24px" in style
    assert palette["ACCENT_COLOR"] in style  # hover/press accent
    assert "add-line" in style  # arrow buttons removed


def test_scrollbar_stylesheet_bottom_margin_is_caller_driven(palette):
    """The shared rules default to a full track; a caller with a content pad
    passes the pad in and both bottoms shorten together."""
    from utils.ui_helpers import global_scrollbar_stylesheet
    assert "margin: 0px 0px 0px 0px" in global_scrollbar_stylesheet(palette)
    assert "margin: 0px 0px 10px 0px" in scrollbar_stylesheet(palette, bottom_margin=10)


def test_line_edit_stylesheet_variants(palette):
    plain = line_edit_stylesheet(palette)
    assert "QLineEdit:hover" in plain
    assert "QLineEdit:disabled" in plain
    assert "text-align: center" not in plain
    centered = line_edit_stylesheet(palette, center_text=True, placeholder_color="#808080")
    assert "text-align: center" in centered
    # A `QLineEdit::placeholder { color: ... }` block never matches in a Qt
    # style sheet; the property the parser honours is `placeholder-text-color`.
    assert "QLineEdit { placeholder-text-color: #808080; }" in centered


def test_line_edit_placeholder_rule_actually_recolors_the_glyphs(qtbot, palette):
    """The rule must reach the widget, not just the string: after polish the
    PlaceholderText palette role carries the requested color."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QLineEdit

    widget = QLineEdit()
    widget.setPlaceholderText("سال")
    qtbot.addWidget(widget)
    widget.setStyleSheet(line_edit_stylesheet(palette, placeholder_color="#123456"))
    widget.ensurePolished()
    color = widget.palette().color(QPalette.ColorRole.PlaceholderText)
    assert color.name().upper() == "#123456"


def test_error_line_edit_stylesheet_extends_plain_with_red(palette):
    plain = line_edit_stylesheet(palette)
    error = error_line_edit_stylesheet(palette)
    assert plain in error  # appended over the shared style
    # The red override is embedded verbatim from the palette (raw case).
    assert palette["HOLIDAY_COLOR"] in error
    assert "QLineEdit:hover, QLineEdit:focus" in error  # stays red on hover/focus


def test_window_title_button_stylesheets_pair(palette):
    close_style, minimize_style = window_title_button_stylesheets(palette)
    assert "#E81123" in close_style  # Windows-red close hover
    assert palette["HOVER_BG"] in minimize_style
    assert "border-radius: 8px" in close_style and "border-radius: 8px" in minimize_style


def test_combo_stylesheet_dropdown_variants(palette):
    zeroed = combo_stylesheet(palette)
    assert "drop-down" in zeroed
    assert "border: 0px; width: 0px; height: 0px;" in zeroed
    custom = combo_stylesheet(palette, dropdown_bg="#123456",
                              dropdown_border_key="MENU_BORDER_COLOR",
                              zero_drop_down=False, center_text=True)
    assert "#123456" in custom
    assert palette["MENU_BORDER_COLOR"] in custom
    assert "text-align: center" in custom
    # The popup scrollbar shares the round-pill rules with its own selector.
    assert "QAbstractItemView::verticalScrollBar" in custom


# --- mouse-event routing lives on the mixin itself (REF-7) -------------------------


def test_mixin_mouse_press_starts_drag_without_per_host_wrappers(qtbot):
    """REF-7: BaseFramelessWindow / ConfirmDialog / DownloadUpdateDialog used
    to repeat identical mousePressEvent/mouseMoveEvent/mouseReleaseEvent
    wrappers around the handle_drag_* helpers; the routing is now part of the
    mixin, so a plain host gets full drag behaviour with zero extra code."""
    from tests.qt_mousing import press as raw_press
    surface = _surface(qtbot)
    event = raw_press(surface, local=(10, 10))
    surface.mousePressEvent(event)  # inherited from FramelessDragMixin
    assert surface._drag_position is not None
    assert event.isAccepted()


def test_mixin_mouse_release_ends_drag_without_per_host_wrappers(qtbot):
    from tests.qt_mousing import press as raw_press, release
    surface = _surface(qtbot)
    surface.mousePressEvent(raw_press(surface, local=(10, 10)))
    surface.mouseReleaseEvent(release(surface))
    assert surface._drag_position is None


# --- centralized stylesheets (REF-4) -------------------------------------------------


def test_global_scrollbar_stylesheet_uses_shared_rules(palette):
    from utils.ui_helpers import global_scrollbar_stylesheet
    qss = global_scrollbar_stylesheet(palette)
    assert "QScrollBar:vertical" in qss
    assert palette['SCROLLBAR_GROOVE_COLOR'] in qss
    assert palette['SCROLLBAR_HANDLE_COLOR'] in qss
    assert palette['ACCENT_COLOR'] in qss  # hover reaction


def test_controller_global_stylesheet_delegates_to_ui_helpers(palette):
    """The controller must not re-inline scrollbar rules (REF-4)."""
    from core.app_controller import SystemTrayIcon
    from utils.ui_helpers import global_scrollbar_stylesheet
    from config import APP_CONFIG
    assert SystemTrayIcon._build_global_stylesheet() == \
        global_scrollbar_stylesheet(APP_CONFIG.get_current_palette())


def test_nav_button_stylesheet_variants(palette):
    from utils.ui_helpers import nav_button_stylesheet
    ghost = nav_button_stylesheet(palette, "transparent")
    assert "background-color: transparent" in ghost
    assert palette['HOVER_BG'] in ghost  # hover fill for the arrows
    today = nav_button_stylesheet(palette, palette['ACCENT_COLOR'], is_today_button=True)
    assert palette['ACCENT_COLOR'] in today
    assert ":pressed" in today  # accent pill lightens/darkens

# --- popup work-area clamping ---------------------------------------------------

@pytest.fixture
def work_area(monkeypatch):
    """Pin every screen lookup to a known 1000x800 work area at the origin, so
    the clamping maths is assertable regardless of the CI desktop's size."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QApplication

    rect = QRect(0, 0, 1000, 800)

    class FakeScreen:
        def availableGeometry(self):
            return rect

    screen = FakeScreen()
    monkeypatch.setattr(QApplication, "screenAt", staticmethod(lambda pos: screen))
    monkeypatch.setattr(QApplication, "primaryScreen", staticmethod(lambda: screen))
    return rect


@pytest.fixture
def menu(qtbot):
    from PyQt6.QtWidgets import QMenu
    popup = QMenu()
    popup.addAction("a")
    return popup


def _hint(menu):
    return menu.sizeHint().width(), menu.sizeHint().height()


def test_clamp_leaves_a_mid_screen_popup_untouched(work_area, menu):
    """The helper must be a no-op in the common case - a menu opened well
    inside the work area keeps the cursor position Qt asked for."""
    width, height = _hint(menu)
    anchor = QPoint(400, 400)
    assert clamp_popup_to_work_area(menu, anchor) == anchor
    assert anchor.x() + width < 1000 and anchor.y() + height < 800


def test_clamp_pulls_back_from_the_right_edge(work_area, menu):
    """A menu anchored so it would hang off the right wall is moved left far
    enough that a margin of breathing room survives - the whole point being
    that a flush-against-the-edge menu reads as clipped even when it is not."""
    width, height = _hint(menu)
    result = clamp_popup_to_work_area(menu, QPoint(work_area.right() - width + 2, 400))
    assert result.x() + width - 1 == work_area.right() - MENU_EDGE_MARGIN


def test_clamp_pulls_back_from_the_bottom_edge(work_area, menu):
    width, height = _hint(menu)
    result = clamp_popup_to_work_area(menu, QPoint(400, work_area.bottom() - height + 2))
    assert result.y() + height - 1 == work_area.bottom() - MENU_EDGE_MARGIN


def test_clamp_keeps_the_top_left_anchor_against_the_edges(work_area, menu):
    """Only the far edges are clamped: a menu at the very top-left of the
    work area must NOT be shoved away from the cursor by the margin floor."""
    result = clamp_popup_to_work_area(menu, QPoint(0, 0))
    assert result == QPoint(MENU_EDGE_MARGIN, MENU_EDGE_MARGIN)


def test_clamp_defers_to_qt_when_the_popup_is_larger_than_the_screen(work_area, qtbot):
    """A popup bigger than the work area cannot be made to fit, so clamping
    would fight Qt's own centring; the anchor is returned unchanged."""
    from PyQt6.QtWidgets import QMenu
    from PyQt6.QtCore import QSize
    big = QMenu()
    big.addAction("x")
    big.setFixedSize(QSize(2000, 1200))
    qtbot.addWidget(big)
    anchor = QPoint(10, 10)
    assert clamp_popup_to_work_area(big, anchor) == anchor


def test_clamp_falls_back_to_the_primary_screen_when_the_cursor_is_off_screen(work_area, menu):
    """After an RDP disconnect there may be no screen under the cursor; the
    helper falls back to the primary screen rather than raising."""
    from PyQt6.QtWidgets import QApplication
    QApplication.screenAt = staticmethod(lambda pos: None)
    assert isinstance(clamp_popup_to_work_area(menu, QPoint(99999, 99999)), QPoint)


def test_nudge_leaves_an_interior_popup_alone(work_area, qtbot):
    """nudge_popup_inside_work_area is the post-show counterpart of the clamp and
    must not move a menu that is already comfortably inside."""
    from PyQt6.QtWidgets import QMenu
    popup = QMenu()
    popup.addAction("a")
    qtbot.addWidget(popup)
    popup.setFixedSize(100, 60)
    popup.show()
    popup.move(300, 300)
    before = popup.pos()
    nudge_popup_inside_work_area(popup)
    assert popup.pos() == before


def test_nudge_pulls_a_flush_popup_off_the_edge(work_area, qtbot):
    """A tray menu shown by Qt lands flush against the work-area edge; the
    nudge must pull it back in by the margin without otherwise relocating it."""
    from PyQt6.QtWidgets import QMenu
    popup = QMenu()
    popup.addAction("a")
    qtbot.addWidget(popup)
    popup.setFixedSize(100, 60)
    popup.show()
    popup.move(work_area.right() - 100 + 1, 300)  # flush right
    nudge_popup_inside_work_area(popup)
    assert popup.x() + 100 - 1 == work_area.right() - MENU_EDGE_MARGIN


def test_nudge_keeps_both_edges_inside_a_snug_work_area(work_area, qtbot):
    """When the work area is barely wider than the popup, a full-width margin on
    both edges makes the left/top rules overwrite the right/bottom ones and push
    the popup back out; each axis's margin must shrink to the free space."""
    from PyQt6.QtWidgets import QMenu
    popup = QMenu()
    popup.addAction("x")
    popup.setFixedSize(work_area.width() - 3, 60)
    qtbot.addWidget(popup)
    popup.show()
    popup.move(work_area.right() - popup.width() + 1, 300)  # flush right
    nudge_popup_inside_work_area(popup)
    assert popup.x() >= work_area.left()
    assert popup.x() + popup.width() - 1 <= work_area.right()


def test_nudge_is_a_no_op_while_hidden(work_area, qtbot):
    """Called from showEvent, so a hidden popup must return immediately rather
    than moving a window the show is about to place itself."""
    from PyQt6.QtWidgets import QMenu
    popup = QMenu()
    popup.addAction("a")
    qtbot.addWidget(popup)
    popup.move(9999, 9999)
    before = popup.pos()
    nudge_popup_inside_work_area(popup)
    assert popup.pos() == before
