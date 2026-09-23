"""Tests for utils.ui_helpers: rounded-card painting, the frameless drag
mixin (shared by every frameless surface), tray pixmaps, combo fitting and
the shared stylesheet builders."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import QComboBox, QWidget

from config import APP_CONFIG
from tests.qt_mousing import press, release
from utils.ui_helpers import (DigitsFirstCombo, FramelessDragMixin,
                              accent_button_stylesheet, center_combo_items,
                              combo_stylesheet, create_tray_pixmap,
                              danger_button_stylesheet, error_line_edit_stylesheet,
                              fit_combo_width, ghost_button_stylesheet,
                              line_edit_stylesheet, paint_rounded_card,
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
    """The cursor point must stay ON screen during the move (screenAt is the
    clamp anchor), while the dragged window is pushed past the edge."""
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


def test_line_edit_stylesheet_variants(palette):
    plain = line_edit_stylesheet(palette)
    assert "QLineEdit:hover" in plain
    assert "QLineEdit:disabled" in plain
    assert "text-align: center" not in plain
    centered = line_edit_stylesheet(palette, center_text=True, placeholder_color="#808080")
    assert "text-align: center" in centered
    assert "QLineEdit::placeholder { color: #808080; }" in centered


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
