"""
Shared Confirm Card
-------------------

`ConfirmCard` is the visual half of the app's confirmation surfaces: icon
badge, title, message, optional detail box, and a row of action buttons, all
painted and themed the one way. It is a **plain mixin** - it inherits nothing
but `object` - so the same code can sit on a top-level `QDialog` (a modal ask
over another application) or on a `QWidget` child (an overlay inside the
calendar popup).

Why a mixin and not a shared base widget: a `QWidget`-derived base mixed into
`QDialog` gives the class two QWidget branches, and its `super().__init__()`
would then resolve to a different Qt class depending on the host. That works,
but nothing enforces it. A plain mixin keeps exactly one Qt base per class, which
is the shape this project already uses for `FramelessDragMixin` and
`YearRangeValidationMixin`.

The split that makes this work: the mixin never finishes a dialog itself. It
records the clicked caption and calls `_finish_choice`, which each host
implements - `QDialog` accepts or rejects, the overlay hides. `accept()` and
`reject()` are `QDialog`-only and would raise on a plain widget host.

Design notes carried over from the original `ConfirmDialog`:
- The main message/reason line is plain readable ``TEXT_COLOR`` - it is the one
  sentence that explains what is about to happen and must never read as
  de-emphasised grey; only secondary metadata stays muted.
- The optional ``detail`` text is shown in its own rounded quote box,
  separating "what happens" from "to what".
- The card is draggable on the dialog host only, from its blank surfaces, with
  the same screen clamping the frameless windows use.
- The width argument is a floor, not a law: the card grows wide enough that the
  widest button caption plus its padding always fits.
"""
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout)

from config import APP_CONFIG
from utils.ui_helpers import (accent_button_stylesheet, danger_button_stylesheet,
                              ghost_button_stylesheet, paint_rounded_card)

# Button kinds -> stylesheet builders; ``choose`` labels pick from these.
BUTTON_KINDS = {
    "accent": lambda palette: accent_button_stylesheet(palette),
    "danger": lambda palette: danger_button_stylesheet(palette),
    "ghost": lambda palette: ghost_button_stylesheet(palette),
}


class ConfirmCard:
    """Mixin building the themed card: badge, title, message, detail, buttons.

    Hosts supply the Qt base and implement `_finish_choice(kind)`.
    """

    def __init__(self, parent, title: str, message: str, *, detail: str = "",
                 confirm_text: str = "تایید", cancel_text: str = "انصراف",
                 danger: bool = True, width: int = 340,
                 glyph: Optional[str] = None,
                 actions: Optional[List[Tuple[str, str]]] = None):
        super().__init__(parent)
        # Shared by both hosts: without it the rounded card paints square
        # corners, which is invisible on a dialog's own surface but shows
        # against the calendar's translucent popup.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._danger = danger
        self._actions = actions if actions else [
            (confirm_text, "danger" if danger else "accent"),
            (cancel_text, "ghost"),
        ]
        self.buttons: List[QPushButton] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(8)

        # Icon badge: a colored circle with a white glyph, centered like the
        # rest of the content. Trash marks destructive asks; the rotate glyph
        # marks replacements/updates - both at a glance, before any text.
        badge_row = QHBoxLayout()
        default_glyph = APP_CONFIG.FAS.FA_TRASH if danger else APP_CONFIG.FAS.FA_ARROWS_ROTATE
        self.icon_badge = QLabel(glyph if glyph else default_glyph)
        self.icon_badge.setFixedSize(48, 48)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addStretch()
        badge_row.addWidget(self.icon_badge)
        badge_row.addStretch()
        main_layout.addLayout(badge_row)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        # A surface that carries everything in ``detail`` (the calendar's
        # distance notice) leaves no headline, so the label is hidden rather
        # than reserving its font height as dead air above the box.
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setVisible(bool(message))
        main_layout.addWidget(self.message_label)

        # Optional preview in its own rounded box, so the event text never blurs
        # into the question line.
        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setVisible(bool(detail))
        main_layout.addWidget(self.detail_label)

        main_layout.addSpacing(6)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        for text, kind in self._actions:
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self._make_choice_handler(button, kind))
            # Equal-width buttons; RTL puts the first add on the right, keeping
            # the leading action on the leading side as before.
            button_row.addWidget(button, 1)
            self.buttons.append(button)
        main_layout.addLayout(button_row)
        # Width floor from the caller, raised to whatever the button row needs:
        # equal stretch shrinks every button to the same width, so one long
        # caption («بعداً یادآوری کن") would clip all three buttons.
        self.setFixedWidth(max(width, self._minimum_width_for_buttons()))
        self.choice: Optional[str] = None  # set to the clicked button's text
        # Default two-button flow keeps its named accessors (tests/callers).
        if actions is None:
            self.confirm_button = self.buttons[0]
            self.cancel_button = self.buttons[1]

        self.update_styles()
        self._pin_message_height()

    def _finish_choice(self, kind: str) -> None:
        """End the card once an action was chosen. Host-supplied.

        ``kind`` is the button's style kind, so a host can tell a ghost
        (cancel-flavoured) click from a leading one without re-reading the
        caption.
        """
        raise NotImplementedError

    def _pin_message_height(self):
        """Fit the message label exactly around its wrapped text.

        A word-wrapped QLabel's sizeHint badly over-estimates (Qt's wrapped-text
        hint heuristic prefers a roughly square block). The card's height was
        fixed from those inflated hints and then re-flowed at the real width, and
        the surplus was smeared across the title and message rows - a visible band
        of dead air between the header and the reason text (worst on short
        one-line messages, whose inflated hint claimed twice the real need).
        Pinning the label to ``heightForWidth`` at the card's real inner width
        gives the layout its true need. Long, wrapping messages already matched
        their hint and are unaffected.
        """
        if not self.message_label.text():
            return
        self.message_label.ensurePolished()
        margins = self.layout().contentsMargins()
        inner_width = self.width() - margins.left() - margins.right()
        height = self.message_label.heightForWidth(inner_width)
        if height > 0:
            self.message_label.setFixedHeight(height)

    def _minimum_width_for_buttons(self) -> int:
        """Dialog width at which no button caption ever clips.

        Qt measures sizeHint before the QSS font lands, and the shared button
        styles hard-code 18px side padding, so the requirement is measured
        here with the same family/weight the stylesheets ask for: caption
        advance + 2x18px padding + 2px border per button, plus the row's
        margins and spacing, times a small raster-safety factor.
        """
        font = QFont(APP_CONFIG.FONT_FAMILY, 10)
        font.setBold(True)
        metrics = QFontMetrics(font)
        margins = self.layout().contentsMargins()
        total = margins.left() + margins.right()
        for i, (text, _kind) in enumerate(self._actions):
            total += metrics.horizontalAdvance(text) + 38  # 2x18 padding + 2 border
            if i:
                total += 10  # button_row spacing
        return int(total * 1.1)

    def _make_choice_handler(self, button: QPushButton, kind: str):
        """Record the click, then let the host finish.

        The kind is bound per button - deriving it from the clicked text inside
        the closure would break duplicate labels and re-lookups.
        """

        def handler():
            self.choice = button.text()
            self._finish_choice(kind)
        return handler

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_rounded_card(painter, self.rect(),
                           APP_CONFIG.current_palette['BACKGROUND_COLOR'],
                           APP_CONFIG.current_palette['MENU_BORDER_COLOR'], 15)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        badge_color = palette['HOLIDAY_COLOR'] if self._danger else palette['ACCENT_COLOR']
        self.icon_badge.setStyleSheet(
            f"background-color: {badge_color}; color: white; border-radius: 24px;"
            f"font-family: '{APP_CONFIG.FONT_AWESOME_FAMILY}'; font-size: 20px;")
        self.title_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 16px; font-weight: bold; background: transparent; border: none;")
        self.message_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 13px; background: transparent; border: none;")
        self.detail_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 13px; font-weight: bold; background-color: {palette['INPUT_BG_COLOR']}; "
            f"border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 10px; padding: 10px 12px;")
        for button, (_text, kind) in zip(self.buttons, self._actions):
            button.setStyleSheet(BUTTON_KINDS[kind](palette))
