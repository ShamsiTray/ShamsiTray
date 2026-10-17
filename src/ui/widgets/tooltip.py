"""
Custom Tooltip Widget
--------------------

This module provides `CustomTooltip`, a custom-rendered tooltip that bypasses
Qt6's native tooltip rendering. This fixes the issue where native tooltips on
Windows ignore border-radius styling and appear as rectangles with sharp corners.

`HoverTooltipMixin` is the widget half: a widget that mixes it in gets the
themed tooltip on hover instead of Qt's own.
"""
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget, QVBoxLayout, QApplication

from config import APP_CONFIG

# The one hover delay every custom tooltip waits - the day cell reads it too, so
# the grid and the event manager cannot drift apart. It sits near Qt's own native
# tooltip delay (~700ms) rather than below it: at 500ms a tooltip fired while the
# hand was still travelling towards the target, which reads as a flicker.
TOOLTIP_DELAY_MS = 700

# A tone says what a tooltip is telling the user; the palette decides the colour,
# so both themes stay legible. An absent tone means "neutral" - content tooltips
# (a holiday's reason, an event's text) colour their own lines already. "danger"
# is for the one action that destroys data, and resolves to the palette's warning
# colour for the border and the text.
TOOLTIP_TONES = {"danger": "HOLIDAY_COLOR"}


class CustomTooltip(QWidget):
    """A custom tooltip widget that bypasses Qt6's native tooltip rendering."""

    _instance = None

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._label)

        # One reusable auto-hide timer for the copy confirmations. Restarting a
        # single shot gives every copy its own full window; separate
        # QTimer.singleShot calls cannot be cancelled, so an earlier one could
        # cut a later copy short or hide an unrelated tooltip (a holiday, say)
        # mid-display.
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        # Which widget asked for the text currently on screen. There is one
        # shared tooltip window, so a widget that is leaving (or being hidden)
        # must not dismiss a tooltip another widget owns - a «کپی شد» flash, say.
        self._owner = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = CustomTooltip()
        return cls._instance

    def flash_tooltip(self, text: str, global_pos: QPoint, duration_ms: int = 600):
        """Show a transient confirmation (e.g. «کپی شد») that hides itself.

        Restarting the single shot on every call is the point: two copies in a
        row never shorten each other's feedback window.
        """
        self.show_tooltip(text, global_pos)
        self._auto_hide_timer.start(duration_ms)

    def show_tooltip(self, text: str, global_pos: QPoint, owner=None, tone: str = "neutral"):
        # An explicit show must never be auto-hidden by a flash still counting
        # down - a holiday or event tooltip arriving right after a copy would
        # vanish mid-read.
        self._auto_hide_timer.stop()
        if not text:
            self.hide()
            self._owner = None
            return
        self._owner = owner

        palette = APP_CONFIG.get_current_palette()
        # An unknown tone falls back to neutral instead of raising: a typo must
        # never leave a tooltip unstyled.
        accent = palette.get(TOOLTIP_TONES.get(tone, ""))
        self._label.setStyleSheet(
            "QLabel {"
            f"background-color: {palette['BACKGROUND_COLOR']}; "
            f"color: {accent or palette['TEXT_COLOR']}; "
            f"border: 1px solid {accent or palette['CALENDAR_BORDER_COLOR']}; "
            "border-radius: 8px; padding: 5px 9px; "
            f"font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 12px; font-weight: bold;"
            "}")

        self._label.setText(text)
        self.adjustSize()

        screen = QApplication.screenAt(global_pos)
        if screen:
            screen_geo = screen.availableGeometry()
            x = global_pos.x() + 4
            y = global_pos.y() + 12

            if x + self.width() > screen_geo.right():
                x = global_pos.x() - self.width() - 8
            if y + self.height() > screen_geo.bottom():
                y = global_pos.y() - self.height() - 8

            self.move(x, y)
        else:
            self.move(global_pos + QPoint(16, 16))

        self.show()
        self.raise_()

    def hide_if_owned_by(self, owner) -> bool:
        """Dismiss the tooltip, but only if ``owner`` asked for the text on screen.

        A flash (and the tray-wide messages) belongs to nobody, so a widget
        going away can never cut another widget's tooltip short by hiding the
        one window they all share.
        """
        if self._owner is None or self._owner is not owner:
            return False
        self._owner = None
        self.hide()
        return True


class HoverTooltipMixin:
    """Routes ``setToolTip`` through ``CustomTooltip`` after a hover delay.

    Native ``setToolTip`` would show Qt's own tooltip (a black box with square
    corners in Windows dark mode), so the text is stored instead and shown by
    the shared custom tooltip - the pattern ``CalendarDayCell`` already uses for
    its own tooltips, which stay separate because they answer to a context menu.
    """

    # Mirrors the module default so a widget (or a test) can override just its
    # own delay; the day cell, which keeps its own tooltip lifecycle, reads the
    # module constant directly.
    TOOLTIP_DELAY_MS = TOOLTIP_DELAY_MS
    # What the tooltip means, not how it looks: a widget explaining a destructive
    # action sets "danger" and the palette colours it.
    TOOLTIP_TONE = "neutral"

    def _init_hover_tooltip(self):
        self._tooltip_text = ""
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_custom_tooltip)

    def setToolTip(self, text: str):
        """Store the tip instead of handing it to Qt (see the class docstring).

        The text also becomes the accessible description: assistive tech still
        reads what a native tooltip would have described the widget with, which
        matters most for a widget whose own text says nothing (an icon glyph).
        """
        self._tooltip_text = text
        self.setAccessibleDescription(text)

    def cancel_pending_tooltip(self):
        """Stop a pending tooltip and dismiss the one this widget owns.

        Hosts call this when a hover is broken without an enter/leave pair - a
        wheel scroll slides the widget out from under a stationary cursor.
        """
        self._tooltip_timer.stop()
        CustomTooltip.instance().hide_if_owned_by(self)

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._tooltip_text:
            self._tooltip_timer.start(self.TOOLTIP_DELAY_MS)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.cancel_pending_tooltip()

    def mousePressEvent(self, event):
        # Clicking acts on the widget (edit/delete); a tooltip must not linger
        # over the editor or the row that is about to be rebuilt.
        self.cancel_pending_tooltip()
        super().mousePressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.cancel_pending_tooltip()

    def _cursor_inside(self) -> bool:
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _show_custom_tooltip(self):
        # The cursor check is what keeps a stale timer (a scroll, a popup menu
        # or an overlay breaks the enter/leave chain) from popping a tooltip
        # over a widget the cursor has left; the visibility check stops a timer
        # that outlived its whole window from floating the tooltip over
        # unrelated applications.
        if self.isVisible() and self._tooltip_text and self._cursor_inside():
            CustomTooltip.instance().show_tooltip(self._tooltip_text, QCursor.pos(),
                                                  owner=self, tone=self.TOOLTIP_TONE)


class TooltipButton(HoverTooltipMixin, QPushButton):
    """QPushButton whose tooltip uses the app's themed CustomTooltip."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._init_hover_tooltip()


class TooltipLabel(HoverTooltipMixin, QLabel):
    """QLabel whose tooltip uses the app's themed CustomTooltip."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._init_hover_tooltip()

