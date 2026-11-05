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
from utils.ui_helpers import copied_pill_ground, legible_on

# The one hover delay every custom tooltip waits - the day cell reads it too, so
# the grid and the event manager cannot drift apart. It sits near Qt's own native
# tooltip delay (~700ms) rather than below it: at 500ms a tooltip fired while the
# hand was still travelling towards the target, which reads as a flicker.
TOOLTIP_DELAY_MS = 700

# A tone says what a tooltip is telling the user; the palette decides the colour,
# so both themes stay legible. An absent tone means "neutral" - content tooltips
# (a holiday's reason, an event's text) colour their own lines already. "danger"
# is for the one action that destroys data, and resolves to the palette's warning
# colour for the border and the text. "success" is the accent colour, for a
# confirmation that something worked (a copy).
TOOLTIP_TONES = {"danger": "HOLIDAY_COLOR", "success": "ACCENT_COLOR"}

# The contrast floor a tone's colour has to clear on the tooltip's own ground.
# The copy confirmation is 12px bold - normal text, not the large text WCAG's
# 3:1 bar covers - so the success tone takes the body floor; the dark accent
# lands at 3.01:1 raw, which is why it is nudged rather than used as-is.
TONE_MIN_CONTRAST = {"success": 4.5}

# The one copy confirmation. The calendar's «کپی تاریخ» row morphs into this
# text and the converter / distance windows flash it as a tooltip, so a copy
# reads the same wherever it happened.
COPIED_TEXT = "✓ کپی شد"


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

    def flash_tooltip(self, text: str, global_pos: QPoint, duration_ms: int = 600,
                      tone: str = "neutral", pill: bool = False):
        """Show a transient confirmation (e.g. «کپی شد») that hides itself.

        Restarting the single shot on every call is the point: two copies in a
        row never shorten each other's feedback window. ``pill`` opts into the
        copy pill: the calendar copy menu's wash ground instead of the
        reference-info box.
        """
        self.show_tooltip(text, global_pos, tone=tone, pill=pill)
        self._auto_hide_timer.start(duration_ms)

    def flash_copied(self, global_pos: QPoint):
        """The app-wide «✓ کپی شد» confirmation: the success tone on the copy
        pill, one look with the calendar's morphed copy row. The text travels
        plain - the label half (show_tooltip's pill branch) carries the checkmark's
        LRM pin, so no caller of flash_tooltip ever sees markup or marks."""
        self.flash_tooltip(COPIED_TEXT, global_pos, tone="success", pill=True)

    def show_tooltip(self, text: str, global_pos: QPoint, owner=None,
                     tone: str = "neutral", pill: bool = False):
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
        # never leave a tooltip unstyled. A tone that declares a floor is nudged
        # to it, so the palette stays the hue owner; a tone without one keeps
        # its palette colour verbatim.
        accent = palette.get(TOOLTIP_TONES.get(tone, ""))
        floor = TONE_MIN_CONTRAST.get(tone)
        if pill:
            # The copy pill borrows the calendar copy menu's wash ground.
            ground = copied_pill_ground(palette)
        else:
            ground = palette["BACKGROUND_COLOR"]
        if accent and floor:
            # Floored against the actual surface - the pill's accent-tinted
            # wash, not the flat background.
            accent = legible_on(accent, ground, floor)
        # The menu SURFACE owns the pill's chrome (the frame, hairlines and
        # rows around it define the shape), so wash alone reads there. A
        # floating flash has no such frame - it frames ITSELF, in the
        # caption's floored accent: the reference box's border over the
        # pill's wash.
        border = f"1px solid {accent or palette['CALENDAR_BORDER_COLOR']}"
        self._label.setStyleSheet(
            "QLabel {"
            f"background-color: {ground}; "
            f"color: {accent or palette['TEXT_COLOR']}; "
            f"border: {border}; "
            "border-radius: 8px; padding: 5px 9px; "
            f"font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 12px; font-weight: bold;"
            "}")

        if pill:
            # The copy confirmation leads with LRM (U+200E, a strong
            # Left-to-Right bidi character): the paragraph's first-strong
            # auto-detection would otherwise follow «ک» and push a leading
            # neutral ✓ to the far right - on every locale, app direction
            # aside. Measured under forced app-RTL and app-LTR renders: an
            # inline <span dir="ltr"> is a no-op in Qt rich text and a
            # widget-level pin cannot reach the label's paragraph base; the
            # menu's copied row answers the same pull with its own painter
            # pin. The mark rides the label, not flash_tooltip's arguments,
            # so the text contract stays plain.
            text = f"\u200e{text}"
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

    def current_owner(self):
        """The widget whose tooltip is on screen right now, or None.

        A flash (and any broadcast notice) is owned by nobody, so a host can
        check and drop only widgets it recognises - the same boundary
        hide_if_owned_by keeps, readable instead of blind.
        """
        return self._owner


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

