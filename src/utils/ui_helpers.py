"""
UI Helper Functions
-------------------

This module contains utility functions related to creating or manipulating
UI elements, such as dynamically drawing pixmaps or building shared stylesheets.
"""
import ctypes
import sys
from typing import Optional

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QScrollArea, QStyle,
                             QStyleOptionComboBox, QStylePainter)

from config import APP_CONFIG
from utils.date_utils import from_persian_digits
from utils.logger import setup_logging

logger = setup_logging(__name__)

# Gap kept between a popup menu and the edge of the work area, in logical
# pixels. Qt already flips or shifts a popup that would not fit, so nothing ever
# clips - this only stops the result from butting flat against the right or
# bottom wall with no breathing room, which reads as "cut off" even when the
# menu is fully visible.
MENU_EDGE_MARGIN = 8


def clamp_popup_to_work_area(popup, global_pos: QPoint, *, margin: int = MENU_EDGE_MARGIN) -> QPoint:
    """Return a position for ``popup`` at ``global_pos`` that keeps a margin.

    Qt keeps a popup on screen by flipping or shifting it, but a menu opened at
    a cursor already near the bottom-right corner ends up flush against the work
    area edge. This nudges the anchor back inside by ``margin`` logical pixels
    instead, which is what the user reads as a deliberate placement.

    The popup's own size is measured from ``sizeHint`` rather than ``width()``:
    a never-shown menu has no geometry yet, but its hint is what Qt will use.
    Falls back to the primary screen when the cursor is on none (RDP
    disconnect), and returns ``global_pos`` untouched if the popup is larger
    than the work area - clamping would then fight Qt's own centring.
    """
    screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
    if screen is None:
        return global_pos
    geo = screen.availableGeometry()

    width = popup.sizeHint().width() or popup.width()
    height = popup.sizeHint().height() or popup.height()
    if width >= geo.width() or height >= geo.height():
        return global_pos

    x = min(global_pos.x(), geo.right() - margin - width + 1)
    y = min(global_pos.y(), geo.bottom() - margin - height + 1)
    # Only the far edges move; a popup near the top-left must not be pushed
    # away from the cursor.
    x = max(x, geo.left() + margin)
    y = max(y, geo.top() + margin)
    return QPoint(int(x), int(y))


def nudge_popup_inside_work_area(popup, *, margin: int = MENU_EDGE_MARGIN) -> None:
    """Pull an already-positioned popup back from the work-area edges.

    For menus Qt shows itself rather than ones the app calls ``exec()`` on (the
    tray menu, via ``setContextMenu``): there is no anchor to adjust, so the
    only chance is to move the window once it has been placed. Call from
    ``showEvent`` - moving a hidden popup would be undone by the show itself.
    """
    if not popup.isVisible():
        return
    screen = QApplication.screenAt(popup.frameGeometry().center()) or QApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    frame = popup.frameGeometry()

    # A margin wider than the free space on its axis makes the two edge rules
    # fight: the left/top pair would overwrite the right/bottom pair and push
    # the popup back out of the work area. Shrink each margin to what that axis
    # actually has to give, so the rules agree - or the popup simply fills it.
    margin_x = min(margin, max(0, (geo.width() - frame.width()) // 2))
    margin_y = min(margin, max(0, (geo.height() - frame.height()) // 2))

    x, y = frame.x(), frame.y()
    if frame.right() > geo.right() - margin_x:
        x = geo.right() - margin_x - frame.width() + 1
    if frame.bottom() > geo.bottom() - margin_y:
        y = geo.bottom() - margin_y - frame.height() + 1
    if frame.left() < geo.left() + margin_x:
        x = geo.left() + margin_x
    if frame.top() < geo.top() + margin_y:
        y = geo.top() + margin_y

    if (x, y) != (frame.x(), frame.y()):
        popup.move(x, y)

def paint_rounded_card(painter: QPainter, rect, fill_color, border_color, radius: float) -> QPainterPath:
    """Paint the app's rounded-card background (antialiased fill + 1px border).

    Shared by every frameless surface (base window, dialogs, popups) which used
    to carry four near-identical paintEvent bodies. Returns the path so callers
    that clip children to the card (the base window) can reuse it. ``rect`` is
    the widget rect; the card is inset by 1px on each side so the border is not
    clipped at the window edge.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), radius, radius)
    painter.fillPath(path, QColor(fill_color))
    painter.setPen(QColor(border_color))
    painter.drawPath(path)
    return path


class FramelessDragMixin:
    """Shared drag logic and Qt mouse-event routing for frameless surfaces.

    Was duplicated in three places (base window, ConfirmDialog,
    DownloadUpdateDialog) with slightly different clamping; the mixin keeps one
    implementation. It also carries the ``mousePressEvent``/``mouseMoveEvent``/
    ``mouseReleaseEvent`` wrappers those hosts each repeated verbatim, so mixing
    this class in is the whole integration. Configure via the
    ``drag_strip_height`` class attribute: an int restricts dragging to a top
    strip of that many logical pixels (the calendar/tool windows drag by their
    title area only), ``None`` makes the whole blank surface draggable
    (dialogs). ``drag_bottom_keep_visible`` tunes the vertical clamp: ``None``
    keeps the window fully inside the desktop's AVAILABLE area, so a dialog's
    bottom buttons never come to rest behind the taskbar (dialogs), while an int
    N keeps only the top N px of the window reachable above the desktop's bottom
    edge - the tool windows' historical rule, letting most of the window hang
    below it (taskbar strip included) without ever losing it entirely. A card
    can never be lost off-screen.

    Interactive children (buttons, inputs) consume their own mouse events, so a
    press on them never reaches these handlers and never starts a drag.
    """

    drag_strip_height: Optional[int] = None
    drag_bottom_keep_visible: Optional[int] = None
    _drag_position: Optional[QPoint] = None

    def handle_drag_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        strip = self.drag_strip_height
        if strip is not None and event.position().y() >= strip:
            return False
        self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        event.accept()
        return True

    def handle_drag_move(self, event) -> bool:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_position is None:
            return False
        new_pos = event.globalPosition().toPoint() - self._drag_position
        # Clamp against the whole virtual desktop, not the screen under the
        # cursor: that screen flips as the cursor crosses a monitor boundary,
        # and clamping to the new one teleports the window to its left edge
        # while the window itself is still mostly on the old screen.
        primary = QApplication.primaryScreen()
        if primary is not None:
            keep_visible = self.drag_bottom_keep_visible
            if keep_visible is None:
                # A dialog must stay wholly reachable, and the taskbar is not
                # part of the desktop it may use: availableVirtualGeometry is
                # the work area, still the union across monitors so a drag
                # between them keeps spanning the desktop. Fall back when the
                # platform reports nothing usable.
                desktop = primary.availableVirtualGeometry()
                if desktop.isNull():
                    desktop = primary.virtualGeometry()
            else:
                # The tool windows may hang below the edge - only their top N px
                # must stay reachable - so the taskbar strip is theirs to use.
                desktop = primary.virtualGeometry()
            new_pos.setX(max(desktop.left(), min(new_pos.x(), desktop.right() - self.width())))
            y_max = desktop.bottom() - self.height() if keep_visible is None else desktop.bottom() - keep_visible
            new_pos.setY(max(desktop.top(), min(new_pos.y(), y_max)))
            self.move(new_pos)
        event.accept()
        return True

    def handle_drag_release(self, event) -> bool:
        if self._drag_position is None:
            return False
        self._drag_position = None
        event.accept()
        return True

    # --- Qt event routing ---------------------------------------------------------

    def mousePressEvent(self, event):
        if self.handle_drag_press(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.handle_drag_move(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.handle_drag_release(event):
            return
        super().mouseReleaseEvent(event)


# The virtual-key codes of the mouse buttons the hover driver cross-checks
# against Windows (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON). GetAsyncKeyState sets
# the 0x8000 bit of its answer for every key that is physically down.
_MOUSE_BUTTON_VKS = (0x01, 0x02, 0x04)

# A corner of a window where nothing lives (an inert spot on the drag strip):
# the target of the synthetic button releases and of the parked-cursor move.
_INERT_FEED_POS = QPoint(2, 2)


def _win32_capture_hwnd() -> int:
    """(Windows) The window that currently holds the mouse capture, or 0.

    Capture is thread-scoped, so this only answers for the GUI thread."""
    user32 = ctypes.windll.user32
    user32.GetCapture.restype = ctypes.c_void_p
    return user32.GetCapture() or 0


def _win32_release_capture() -> None:
    """(Windows) Release the calling thread's mouse capture."""
    ctypes.windll.user32.ReleaseCapture()


class HoverDriverMixin:
    """Repairs Qt's mouse delivery for frameless surfaces opened by a tray click.

    Such a click's press hides (or opens) the popup and its release never
    reaches Qt, which then keeps believing a button is held; while it does,
    enter/leave and ``:hover`` stop responding to plain mouse moves - tooltips
    arm late and the cursor seems dead until the user clicks once. The mixin
    polls for a bounded stretch after every ``show()``: it cross-checks Qt's
    button state against the OS (Win32 ``GetAsyncKeyState``), gives Qt the
    synthetic releases a real click would have sent, feeds the cursor's real
    position into Qt's mouse pipeline as ordinary moves, and stops as soon as
    the state has healed - ordinary mouse moves carry hover from there.

    Mix it into any Qt window next to ``FramelessDragMixin`` with the mixin
    first in the bases (``class W(HoverDriverMixin, FramelessDragMixin,
    QWidget)``); the cooperative ``__init__``, ``showEvent`` and ``hideEvent``
    chain to whatever follows, and the whole thing parks the repair state per
    open so a host never manages it. Also used by the QDialog hosts
    (``ConfirmDialog``, ``DownloadUpdateDialog``) - the update popup can appear
    from a silent auto-check right after a tray interaction left the state
    stale, and its buttons deserve hover too.
    """
    # Ticks are only spent while the window is visible and the driver has not
    # converged yet - roughly the first third of a second after each open - so
    # a long-lived window pays nothing once it is healed.
    HOVER_TICK_MS = 30
    HOVER_STALE_BUTTON_TICKS = 3   # ~90 ms of Qt-says-down / OS-says-none
    HOVER_STALE_REPAIR_MAX = 3     # repair attempts per open before giving up
    HOVER_CAPTURE_TICKS = 15       # ~450 ms budget for the stray-capture sweep
    HOVER_CONVERGE_TICKS = 5       # clean ticks before the driver stops polling

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-open driver state (see _sync_hover). showEvent resets all of it,
        # so a prewarm show never shares its verdicts with a later real open.
        self._last_fed_cursor = None
        self._was_inside = False
        self._stale_button_ticks = 0
        self._stale_repairs = 0
        self._healthy_ticks = 0
        self._capture_checks = 0
        self._feeding = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(self.HOVER_TICK_MS)
        self._hover_timer.timeout.connect(self._sync_hover)

    def showEvent(self, event):
        super().showEvent(event)
        self._reset_hover_driver()
        self._hover_timer.start()

    def hideEvent(self, event):
        self._hover_timer.stop()
        super().hideEvent(event)

    def _reset_hover_driver(self) -> None:
        """Start a fresh open: clear hover bookkeeping and the per-open budgets.

        The off-screen prewarm show runs through here too, deliberately - the
        prewarm's state must never hand a spent budget to the real open."""
        self._last_fed_cursor = None
        self._was_inside = False
        self._stale_button_ticks = 0
        self._stale_repairs = 0
        self._healthy_ticks = 0
        self._capture_checks = 0

    def _sync_hover(self) -> None:
        """One driver tick: repair Qt's mouse state, then feed the cursor in."""
        if not self.isVisible():
            return
        if self._mouse_button_physically_down():
            return  # mid-click / drag: real events are flowing, leave them alone
        self._release_stray_capture()
        cursor = QCursor.pos()
        under = QApplication.widgetAt(cursor)
        if under is None:
            # The cursor is over a foreign window or no window. Qt ignores
            # moves outside this window, so if it just left, park the pointer
            # on the inert corner to un-hover what it left hovered.
            if self._was_inside:
                self._was_inside = False
                self._last_fed_cursor = None
                self._feed_mouse_move(_INERT_FEED_POS)
        elif under.window() is self:
            # Feed when the cursor moved, or when Qt still has no hover state
            # for the widget under it (e.g. right after a stuck-button reset) -
            # that is what makes hover respond without ever being clicked.
            if cursor != self._last_fed_cursor or not under.underMouse():
                self._last_fed_cursor = cursor
                self._feed_mouse_move(self.mapFromGlobal(cursor))
            self._was_inside = True
        # else: another top-level of this process (menu, tooltip, dialog) is
        # under the cursor; it serves its own hover, so none is fed here.
        if self._healthy_ticks >= self.HOVER_CONVERGE_TICKS:
            self._hover_timer.stop()

    def _mouse_button_physically_down(self) -> bool:
        """Whether a mouse button is REALLY held, as the OS reports it.

        ``QApplication.mouseButtons()`` can be stale after a tray click (see
        the class docstring): Qt keeps claiming a button is held although the
        OS moved on. When the two disagree for ``HOVER_STALE_BUTTON_TICKS`` in
        a row, give Qt the synthetic releases a real click would have sent.
        The OS answer is returned either way - False is what clears this tick
        to feed hover moves.

        Convergence is gauged here: every tick whose states agree (or where a
        physical button truly is down, so real events flow) proves Qt's mouse
        bookkeeping healed or irrelevant; enough of those in a row stop the
        driver in ``_sync_hover``.
        """
        qt_down = QApplication.mouseButtons() != Qt.MouseButton.NoButton
        os_down = self._query_os_buttons()
        if qt_down and not os_down:
            if self._stale_repairs < self.HOVER_STALE_REPAIR_MAX:
                self._stale_button_ticks += 1
                self._healthy_ticks = 0
                if self._stale_button_ticks >= self.HOVER_STALE_BUTTON_TICKS:
                    self._stale_button_ticks = 0
                    self._stale_repairs += 1
                    self._reset_stale_qt_buttons()
            else:
                # The synthetic releases never unstuck it. Re-sending them
                # would only spin; accept the state instead - the tick counts
                # toward convergence, and hover feeding works either way.
                self._healthy_ticks += 1
            return False
        if os_down:
            # A genuine press Qt knows about (or will in a moment): real
            # events are flowing, so hover is not this driver's business.
            self._stale_button_ticks = 0
            self._healthy_ticks = 0
            return True
        self._stale_button_ticks = 0
        self._healthy_ticks += 1
        return False

    def _query_os_buttons(self) -> bool:
        """OS-level truth about pressed mouse buttons.

        Only Windows can answer honestly here - and only Windows suffers the
        tray-click quirk. Elsewhere mirror Qt, which keeps the mismatch (and
        with it the repair) unreachable but every tick healthy."""
        if sys.platform != "win32":
            return QApplication.mouseButtons() != Qt.MouseButton.NoButton
        try:
            get_state = ctypes.windll.user32.GetAsyncKeyState
            return bool(any(get_state(vk) & 0x8000 for vk in _MOUSE_BUTTON_VKS))
        except Exception as e:
            logger.warning(f"Mouse-state probe failed; falling back to Qt's record: {e}")
            return QApplication.mouseButtons() != Qt.MouseButton.NoButton

    def _reset_stale_qt_buttons(self) -> None:
        """Send Qt the releases it missed, at the window's inert corner.

        Nothing lives there that a release could trigger, but Qt's mouse
        bookkeeping gets the complete click it never saw."""
        held = QApplication.mouseButtons()
        self._last_fed_cursor = None  # re-report the cursor once Qt's state is clean
        try:
            from PyQt6.QtTest import QTest
            handle = self.windowHandle()
            if handle is None:
                return
            for button in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton,
                           Qt.MouseButton.MiddleButton):
                if held & button:
                    QTest.mouseRelease(handle, button,
                                       Qt.KeyboardModifier.NoModifier, _INERT_FEED_POS)
        except Exception as e:
            logger.warning(f"Could not reset Qt mouse state: {e}")

    def _feed_mouse_move(self, local: QPoint) -> None:
        """Deliver one synthetic mouse move to this window at ``local``.

        ``QTest.mouseMove`` posts through the window system interface without
        touching the real pointer - the same pipeline real moves travel, which
        is what enter/leave and :hover resolve from."""
        handle = self.windowHandle()
        if handle is None or self._feeding:
            return
        self._feeding = True
        try:
            from PyQt6.QtTest import QTest
            QTest.mouseMove(handle, local)
        except Exception as e:
            logger.warning(f"Could not feed mouse move: {e}")
        finally:
            self._feeding = False

    def _release_stray_capture(self) -> None:
        """Windows: drop the mouse capture THIS window still holds (e.g. from
        the tray menu that just closed). Checked briefly after each open.

        Scoped to the window's own handle: a capture another surface of this
        process holds (an open menu's modal loop) is doing its job and must
        survive this sweep."""
        if sys.platform != "win32" or self._capture_checks >= self.HOVER_CAPTURE_TICKS:
            return
        if not self._shown_on_screen():
            return  # the off-screen prewarm: no capture work, and no budget spent
        self._capture_checks += 1
        try:
            held = _win32_capture_hwnd()
            if held and held == int(self.winId()):
                _win32_release_capture()
        except Exception as e:
            logger.warning(f"Capture check failed: {e}")

    def _shown_on_screen(self) -> bool:
        """Whether some screen's work area actually shows this window."""
        frame = self.frameGeometry()
        return any(frame.intersects(screen.availableGeometry())
                   for screen in QApplication.screens())


class YearRangeValidationMixin:
    """Shared 'red border + hint' validation for a year QLineEdit.

    The host class provides:

    - ``self.year_input``: the QLineEdit to validate
    - ``self._year_bounds() -> (min, max)``: the allowed year range
    - optionally ``self.year_hint_label``: a label shown while errored
    - optionally ``self._year_hint_text()``: builds that label's text from the
      live bounds (the converter's range depends on the calendar mode)
    - optionally ``self._year_style_kwargs(errored) -> dict``: extra kwargs for
      the shared line-edit stylesheet builders
    - optionally ``self._on_year_error_changed(errored)``: called when the state
      flips (the go-to-date window resizes its fixed-size card)

    ``_year_is_submittable`` is the answer for a host that gates a confirm
    button on the year (both the converter and go-to-date do).
    """

    _year_error: bool = False

    def _year_is_out_of_range(self) -> bool:
        """True when the text forms a complete year but outside the bounds."""
        text = self.year_input.text().strip()
        if not text:
            return False
        try:
            year = int(from_persian_digits(text))
        except (ValueError, TypeError):
            return False
        lo, hi = self._year_bounds()
        return not lo <= year <= hi

    def _year_is_submittable(self) -> bool:
        """True when the current input can actually be submitted.

        Distinct from ``_year_is_out_of_range``: an EMPTY (or non-numeric) field
        is not "out of range" - the red-border hint must not claim otherwise -
        but it is definitely not submittable, so a host's confirm button takes
        its enabled state from here. The mixin only owns the red border, which
        is why this is a separate predicate rather than a negation of the other.
        """
        text = self.year_input.text().strip()
        if not text:
            return False
        try:
            year = int(from_persian_digits(text))
        except (ValueError, TypeError):
            return False
        lo, hi = self._year_bounds()
        return lo <= year <= hi

    def _update_year_error_state(self, *_args):
        """Keep the red 'invalid year' border in sync with the typed text."""
        self._set_year_error(self._year_is_out_of_range())

    def _set_year_error(self, errored: bool):
        if getattr(self, "_year_error", False) == errored:
            return
        self._year_error = errored
        self._apply_year_style()
        hint = getattr(self, "year_hint_label", None)
        if hint is not None:
            if errored and hasattr(self, "_year_hint_text"):
                hint.setText(self._year_hint_text())
            hint.setVisible(errored)
        self._on_year_error_changed(errored)

    def _on_year_error_changed(self, errored: bool):
        """Host hook: the error state just flipped. Default no-op."""

    def _apply_year_style(self):
        """Style the year input, switching to the shared error look when flagged."""
        palette = APP_CONFIG.get_current_palette()
        errored = getattr(self, "_year_error", False)
        kwargs = self._year_style_kwargs(errored) if hasattr(self, "_year_style_kwargs") else {}
        builder = error_line_edit_stylesheet if errored else line_edit_stylesheet
        self.year_input.setStyleSheet(builder(palette, **kwargs))


def create_tray_pixmap(day_str: str, color_hex: str) -> QPixmap:
    """
    Creates a square QPixmap with the given day number drawn in the center.

    This function handles DPI scaling to ensure the icon looks crisp on
    high-resolution displays.
    """
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96

    icon_size, font_size = (36, 20) if dpi >= 110 else (38, 26)

    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    if not painter.isActive():
        return pixmap
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color_hex))
    painter.setFont(QFont(APP_CONFIG.FONT_FAMILY, font_size, QFont.Weight.Bold))

    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, day_str)
    painter.end()

    return pixmap

def center_combo_items(combo: QComboBox) -> None:
    """Center every item text of a combo box, both in the dropdown and closed.

    The dropdown rows honor the per-item TextAlignmentRole; the closed combo
    draws its current text centered through ``combo_stylesheet(center_text=
    True)``, so pair this helper with that flag for a fully centered control.
    Call it again whenever the items are repopulated (clear() drops the roles).

    The role MUST combine the horizontal and vertical flags: a horizontal-only
    alignment leaves the popup painting an empty band under the last option
    (the dead-space bug). ``AlignCenter`` is the same as the two OR'd together.
    """
    for i in range(combo.count()):
        combo.setItemData(i, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, Qt.ItemDataRole.TextAlignmentRole)


class DigitsFirstCombo(QComboBox):
    """Combo whose mixed «digits - month» labels always render digits-first.

    Items like «۰۶ - شهریور» are bidi-ambiguous: their visual order depends on
    the base direction of whatever paints them, and the style used for the
    closed field differs per platform/style from the popup's - which is how
    «شهریور - ۰۶» (closed) ever disagreed with «۰۶ - شهریور» (dropdown rows).
    Painting the closed label here with an explicit RTL base pins the
    digits-first order on every platform (an RTL base lays the number at the
    left), and centers it like the dropdown rows. The popup view is pinned to
    the same base in ``showPopup`` so rows can never flip either.
    """

    def paintEvent(self, event):
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        painter = QStylePainter(self)
        # Frame, background and arrow; the label is drawn manually below.
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        palette = APP_CONFIG.get_current_palette()
        enabled = bool(opt.state & QStyle.StateFlag.State_Enabled)
        painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # digits-first bidi base
        painter.setPen(QColor(palette['GREY_COLOR'] if not enabled else palette['TEXT_COLOR']))
        painter.setFont(self.font())
        painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         opt.currentText)

    def showPopup(self):
        # Top-level popup windows do not reliably inherit the widget direction
        # on every platform; pin it so the rows render digits-first as well.
        self.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        super().showPopup()

def fit_combo_width(combo: QComboBox, *, font_size: int = 14, bold: bool = False,
                    extra: int = 46, safety: float = 1.12) -> None:
    """Grow a styled combo box so its longest item is never elided.

    Stylesheet fonts are applied after Qt measures ``sizeHint``, so a combo
    with ``AdjustToContents`` plus a QSS ``font-size`` under-measures its own
    text and the closed combo shows ellipses ("بدو...رار"). We measure the
    widest item with the same pixel size the QSS uses and enforce it as a
    minimum width. ``extra`` covers the worst side of the chrome: the closed
    combo's padding + border, or the popup's item padding + vertical scrollbar
    + frame, whichever is larger. A small ``safety`` factor absorbs the
    per-platform font raster differences (a couple of pixels per glyph on
    some Windows DPI settings) that would elide «همه ماه‌ها» to "همه...ه ها"
    and «۱۴۰۸» to "۱..۸". The popup view inherits the same
    minimum so list rows never clip either. Call this after the items are
    filled and the stylesheet is applied, and again whenever the items are
    repopulated.
    """
    font = QFont(APP_CONFIG.FONT_FAMILY)
    font.setPixelSize(font_size)
    font.setBold(bold)
    metrics = QFontMetrics(font)
    widest = max((metrics.horizontalAdvance(combo.itemText(i))
                  for i in range(combo.count())), default=0)
    if widest > 0:
        min_width = int(widest * safety) + extra
        combo.setMinimumWidth(min_width)
        # The dropdown is as wide as the combo by default; keep it wide enough
        # for item padding plus the scrollbar so no row is ever elided.
        combo.view().setMinimumWidth(min_width)


def accent_button_stylesheet(palette: dict, *, padding: str = "8px 18px", font_size: Optional[int] = None) -> str:
    """Shared primary (accent) button style: lightens on hover, darkens on press,
    dimmed when disabled."""
    base = QColor(palette['ACCENT_COLOR'])
    font_rule = f" font-size: {font_size}px;" if font_size else ""
    return (
        f"QPushButton {{ background-color: {base.name()}; color: white; border: none; border-radius: 8px; padding: {padding};{font_rule} font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {base.lighter(110).name()}; }}"
        f"QPushButton:pressed {{ background-color: {base.darker(120).name()}; }}"
        f"QPushButton:disabled {{ background-color: {base.darker(150).name()}; color: rgba(255, 255, 255, 110); }}")


def ghost_button_stylesheet(palette: dict, *, padding: str = "8px 18px") -> str:
    """Shared neutral outline button (accent on hover) for secondary actions.

    Destructive actions keep ``danger_button_stylesheet``; import/export and
    similar low-emphasis buttons use this so red never implies "click me".
    """
    return (
        f"QPushButton {{ background-color: transparent; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ border-color: {palette['ACCENT_COLOR']}; color: {palette['ACCENT_COLOR']}; }}"
        f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}")


def danger_button_stylesheet(palette: dict) -> str:
    """Shared destructive (holiday-red) button style for cancel/delete actions."""
    base = QColor(palette['HOLIDAY_COLOR'])
    return (
        f"QPushButton {{ background-color: {base.darker(120).name()}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {base.darker(110).name()}; }}"
        f"QPushButton:pressed {{ background-color: {base.darker(140).name()}; }}")


# One value owns both bottom insets of a scrolled tool-window list: the
# content column's bottom pad and the scrollbar track's bottom margin. They
# must move together - the pad keeps the last card above the container's
# bottom edge, and a track that still spans the full viewport would let the
# thumb's edge sail past that same card at max scroll.
SCROLL_BOTTOM_PAD_PX = 10


def _scrollbar_rules(palette: dict, *, width: int, selector: str, min_handle: int,
                     bottom_margin: int = 0) -> str:
    """Core rounded-scrollbar rules shared by every scrollbar in the app.

    ``selector`` is ``QScrollBar`` for plain scroll areas and
    ``QAbstractItemView::verticalScrollBar`` for combo-box popups. The groove
    is painted with ``SCROLLBAR_GROOVE_COLOR`` so the track reads as one round
    pill, the handle is a rounded bar that lights up in the accent color on
    hover and press, and the corner arrow buttons are removed entirely.
    ``bottom_margin`` insets the track's bottom edge so the thumb stops where
    the content pad ends; the top stays untouched, so at scroll-top the thumb
    still opens aligned with the first card. Scrolled lists pass their pad
    (``SCROLL_BOTTOM_PAD_PX``) so the two insets cannot drift apart.
    """
    radius = width // 2
    return (
        f"{selector}:vertical {{ border: none; background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; width: {width}px; margin: 0px 0px {bottom_margin}px 0px; border-radius: {radius}px; }}"
        f"{selector}::handle:vertical {{ background-color: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: {radius}px; min-height: {min_handle}px; }}"
        f"{selector}::handle:vertical:hover {{ background-color: {palette['ACCENT_COLOR']}; }}"
        f"{selector}::handle:vertical:pressed {{ background-color: {palette['ACCENT_COLOR']}; }}"
        f"{selector}::add-line:vertical, {selector}::sub-line:vertical {{ height: 0px; }}"
        f"{selector}::add-page:vertical, {selector}::sub-page:vertical {{ background: none; }}")


def scrollbar_stylesheet(palette: dict, *, width: int = 10,
                         bottom_margin: int = 0) -> str:
    """Shared vertical QScrollBar style for the scroll areas of the tool windows.

    Same round pill look the combo-box popups already used (grooved round
    track, rounded handle) plus the accent-color hover reaction that every
    scrollbar in the app now shares. ``bottom_margin`` stops the thumb at the
    caller's content bottom pad instead of letting it run to the track's end.
    """
    return _scrollbar_rules(palette, width=width, selector="QScrollBar",
                            min_handle=24, bottom_margin=bottom_margin)


def global_scrollbar_stylesheet(palette: dict) -> str:
    """App-wide scrollbar style applied at the QApplication level.

    Building the rounded rules here keeps every scrollbar rule in one place so a
    theme tweak cannot drift between the app-wide and per-widget styles.
    """
    return _scrollbar_rules(palette, width=10, selector="QScrollBar", min_handle=20)


class ReservedRailScrollArea(QScrollArea):
    """A scroll area whose vertical rail is always reserved but only painted
    when the content can actually scroll.

    ``ScrollBarAlwaysOn`` reserves the rail column permanently, which is what
    keeps the viewport width stable while rows are inserted during a rebuild —
    the AsNeeded policy reflows the viewport by the rail's width every time the
    content crosses the scrollability threshold, and that reflow is the twitch
    seen when a tool window opens. But a rail that is always *painted* reads as
    an empty groove on short lists. This class splits the two: the policy stays
    ``AlwaysOn`` (stable geometry), while the rail's paint falls back to
    transparent whenever the scrollbar's range is empty — groove fill *and*
    handle, because an empty range draws the handle across the whole track and
    a groove-only override still leaves a full-length pill. A per-widget sheet
    on the scrollbar itself outranks the theme's rules from the scroll area,
    and the handle's hover rules stay cascading through untouched for real
    content.
    """

    # The sheet handed to the scrollbar while its range is empty: the groove
    # fill and the handle both go transparent (hover and press too, so a dead
    # rail cannot light in the accent color under the cursor).
    _RAIL_HIDDEN_SHEET = ("QScrollBar:vertical { background-color: transparent; }"
                          "QScrollBar::handle:vertical { background-color: transparent; }"
                          "QScrollBar::handle:vertical:hover { background-color: transparent; }"
                          "QScrollBar::handle:vertical:pressed { background-color: transparent; }")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Empty until proven otherwise: a fresh area has a zero range, and
        # rangeChanged only fires on actual changes, so the never-scrollable
        # case would otherwise keep the theme's groove color.
        self.verticalScrollBar().setStyleSheet(self._RAIL_HIDDEN_SHEET)
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

    def _on_range_changed(self, _minimum: int, maximum: int):
        sheet = "" if maximum > 0 else self._RAIL_HIDDEN_SHEET
        if self.verticalScrollBar().styleSheet() != sheet:
            # Skip the no-op set: re-polishing an unchanged sheet churns the
            # scrollbar's layout for nothing.
            self.verticalScrollBar().setStyleSheet(sheet)


def nav_button_stylesheet(palette: dict, bg_color: str, *, is_today_button: bool = False) -> str:
    """Calendar header buttons (month arrows, «امروز») shared style.

    Arrow buttons sit on the transparent header (hover = the palette's hover
    fill); the today button is a solid accent pill that lightens on hover and
    darkens on press. Was a private method on the calendar window, moved here so
    theme-driven button styles stay centralized.
    """
    text_color = palette['TEXT_COLOR']
    if is_today_button:
        base_color = QColor(bg_color)
        hover_color = base_color.lighter(120).name()
        pressed_color = base_color.darker(120).name()
        return (f"QPushButton {{ background-color: {base_color.name()}; color: white; border: none; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: {hover_color}; }}"
                f"QPushButton:pressed {{ background-color: {pressed_color}; }}")
    hover_color = QColor(bg_color).darker(120).name() if bg_color != "transparent" else palette['HOVER_BG']
    return (f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border: none; border-radius: 8px; }}"
            f"QPushButton:hover {{ background-color: {hover_color}; }}")


def line_edit_stylesheet(palette: dict, *, padding: str = "8px", center_text: bool = False,
                         placeholder_color: Optional[str] = None) -> str:
    """Shared single-line input style: accent border on hover/focus, greyed
    out while disabled (e.g. the event date-picker's year field for recurring
    events, which need no year). The disabled state dims the text, the border
    and the fill so the field clearly reads as "not editable". Pass
    ``placeholder_color`` to pin the placeholder text's color (QSS placeholders
    otherwise fall back to a platform-chosen grey)."""
    align_rule = " text-align: center;" if center_text else ""
    # A `QLineEdit::placeholder { color: ... }` block never matches in a Qt
    # style sheet - the glyphs keep the platform's grey - so the placeholder
    # color has to ride on the QLineEdit rule itself as `placeholder-text-color`.
    placeholder_rule = f" QLineEdit {{ placeholder-text-color: {placeholder_color}; }}" if placeholder_color else ""
    return (
        f"QLineEdit {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding};{align_rule} font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}"
        f"QLineEdit:hover {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QLineEdit:focus {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QLineEdit:disabled {{ background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; color: {palette['GREY_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; }}"
        + placeholder_rule)


def error_line_edit_stylesheet(palette: dict, *, padding: str = "8px", center_text: bool = False) -> str:
    """The shared line-edit style with the invalid-input (holiday-red) look.

    Appended over ``line_edit_stylesheet`` so the border and text turn holiday
    red - and stay red on hover/focus. Revert to a normal year input by
    applying the plain ``line_edit_stylesheet`` again.
    """
    red = palette['HOLIDAY_COLOR']
    return (line_edit_stylesheet(palette, padding=padding, center_text=center_text)
            + f"QLineEdit {{ border: 1px solid {red}; color: {red}; }}"
              f"QLineEdit:hover, QLineEdit:focus {{ border: 1px solid {red}; }}")


def window_title_button_stylesheets(palette: dict) -> tuple[str, str]:
    """Shared (close, minimize) caption-button styles used by the frameless windows."""
    close_style = (
        f"QPushButton {{ background-color: transparent; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; color: {palette['TEXT_COLOR']}; font-size: 13px; }}"
        f"QPushButton:hover {{ background-color: #E81123; border-color: #E81123; color: white; }}"
        f"QPushButton:pressed {{ background-color: #C50F1F; border-color: #C50F1F; color: white; }}")
    minimize_style = (
        f"QPushButton {{ background-color: transparent; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; color: {palette['TEXT_COLOR']}; font-size: 13px; }}"
        f"QPushButton:hover {{ background-color: {palette['HOVER_BG']}; }}"
        f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}")
    return close_style, minimize_style


def rgba_string(color_hex: str, alpha: float, *, channel_max: int = 255) -> str:
    """The one ``rgba()`` builder for stylesheet text. ``channel_max`` names
    the alpha channel's notation: Qt's QSS keeps the classic integer form in
    the calendar's day styles (tuned over 0-255), while the holiday viewer's
    rows use the CSS 0-1 float form - each stylesheet keeps the notation it
    was tuned with, one builder stops the forms from drifting."""
    color = QColor(color_hex)
    alpha_value = int(alpha * channel_max) if channel_max != 1 else alpha
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_value})"


def plain_menu_stylesheet(palette: dict, *, dividers: bool = False) -> str:
    """The stock-QMenu popup look shared by the tray menu and the calendar's
    go-to-date popup: one rounded frame clause, optionally followed by the
    11px no-paint separator clause the spacing rows need (the tray menu's
    separator rows provide spacing only - TrayMenu paints the actual divider
    lines, so the clause must not draw anything itself)."""
    sheet = (f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; "
             f"border: 1px solid {palette['MENU_BORDER_COLOR']}; "
             f"border-radius: 8px; padding: 5px; }}")
    if dividers:
        sheet += "QMenu::separator { height: 11px; background-color: transparent; }"
    return sheet


def combo_stylesheet(
    palette: dict,
    *,
    padding: str = "8px 5px",
    center_text: bool = False,
    dropdown_bg: Optional[str] = None,
    dropdown_border_key: str = 'CALENDAR_BORDER_COLOR',
    scrollbar_width: int = 10,
    zero_drop_down: bool = True,
) -> str:
    """
    Builds the shared QComboBox stylesheet used by the converter and the
    go-to-date popup. Parameters cover the small per-window visual differences.
    """
    dropdown_color = dropdown_bg if dropdown_bg is not None else palette['INPUT_BG_COLOR']
    dropdown_border_rule = "border: 0px; width: 0px; height: 0px;" if zero_drop_down else "border: 0px;"
    # Same round scrollbar as the scroll areas (shared rules), including the
    # accent-color hover so every scrollbar in the app reacts identically.
    scrollbar_style = _scrollbar_rules(
        palette, width=scrollbar_width,
        selector="QAbstractItemView::verticalScrollBar", min_handle=20)
    text_align_rule = " text-align: center;" if center_text else ""
    return (
        f"QComboBox {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px;{text_align_rule} selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white;}}"
        f"QComboBox:hover, QComboBox:focus, QComboBox::on {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QComboBox:disabled {{ background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; color: {palette['GREY_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; }}"
        f"QComboBox::drop-down {{ {dropdown_border_rule} }}"
        f"QComboBox QAbstractItemView {{ background-color: {dropdown_color}; color: {palette['TEXT_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; border: 1px solid {palette[dropdown_border_key]}; border-radius: 8px; outline: none;}}"
        f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; min-height: 25px; border: none; }}"
        f"QComboBox QAbstractItemView::item:hover {{ background-color: {palette['HOVER_BG']}; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected {{ background-color: {palette['ACCENT_COLOR']}; color: white; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected:hover {{background-color: {palette['ACCENT_COLOR']}; color: white; }}" + scrollbar_style)
