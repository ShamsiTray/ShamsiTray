"""
Themed Confirmation Dialog
--------------------------

`ConfirmDialog` is a small frameless, palette-aware replacement for the stock
``QMessageBox`` asks (delete / replace confirmations, update offers, notices).
The native message box ignored the app theme entirely - system-styled buttons,
wrong font, square corners - so destructive actions felt bolted-on.

Design notes:
- It is a real ``QDialog`` (``exec()`` works) but painted like every other
  frameless window of the app: rounded card, Vazirmatn, palette colors.
 - Content is centered around an icon badge (trash for destructive asks,
   rotate for replacements/updates) so the dialog reads as a deliberate app
   surface instead of a bland left-aligned system strip.
- The main message/reason line is plain readable ``TEXT_COLOR`` - it is the
  one sentence that explains what is about to happen and must never read as
  de-emphasised grey; only secondary metadata stays muted.
- The optional ``detail`` text (the event preview) is shown in its own rounded
  quote box, separating "what happens" from "to what".
- The confirming button is red only when the action is destructive; neutral
  confirmations (e.g. replace) use the accent color. Cancel is a quiet ghost
  button so the dialog never reads like an alarm.
- Besides the two-button ``ask`` there is ``choose`` (three-way questions like
  the update popup's download/ignore/remind) and ``notify`` (single-button
  notices such as "no updates"), so no native message box remains anywhere in
  the app's interactive flows.
- ``WindowModal`` blocks only the parent window, matching the old ``exec()``
  behaviour on the parent without freezing the whole application.
- The card is draggable from any of its blank surfaces (labels and stretches
  pass mouse events through to the dialog; buttons consume their own), with
  the same screen clamping the frameless windows use - a centered dialog is
  only its *initial* position, not a life sentence.
- The width argument is a floor, not a law: the dialog grows wide enough that
  the widest button caption plus its padding always fits, so three-button
  rows like the update popup («بعداً یادآوری کن") never clip.
"""
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from config import APP_CONFIG
from utils.ui_helpers import (FramelessDragMixin, accent_button_stylesheet,
                              danger_button_stylesheet, ghost_button_stylesheet,
                              paint_rounded_card)

# Button kinds -> stylesheet builders; ``choose`` labels pick from these.
_BUTTON_KINDS = {
    "accent": lambda palette: accent_button_stylesheet(palette),
    "danger": lambda palette: danger_button_stylesheet(palette),
    "ghost": lambda palette: ghost_button_stylesheet(palette),
}


class ConfirmDialog(FramelessDragMixin, QDialog):
    """A themed modal ask: icon badge, title, short message, detail box, buttons."""

    def __init__(self, parent, title: str, message: str, *, detail: str = "",
                 confirm_text: str = "تایید", cancel_text: str = "انصراف",
                 danger: bool = True, width: int = 340,
                 glyph: Optional[str] = None,
                 actions: Optional[List[Tuple[str, str]]] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        # Frameless cards still carry a native title for Alt-Tab / taskbar
        # previews: give every dialog the ACTION's name, not the generic app
        # name, so each surface reads as its own thing.
        self.setWindowTitle(title)
        if APP_CONFIG.ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
        self._danger = danger
        # (text, kind) list driving the button row; defaults to confirm/cancel.
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

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.message_label)

        # Optional preview inside its own rounded box, so the event text never
        # blurs into the question line. Kept verbatim - no decorative quotes.
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
        # caption («بعداً یادآوری کن") used to clip all three buttons.
        self.setFixedWidth(max(width, self._minimum_width_for_buttons()))
        self.choice: Optional[str] = None  # set to the clicked button's text
        # Default two-button flow keeps its named accessors (tests/callers).
        if actions is None:
            self.confirm_button = self.buttons[0]
            self.cancel_button = self.buttons[1]

        self.update_styles()
        self._pin_message_height()

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

    # --- dragging ---------------------------------------------------------------
    # FramelessDragMixin supplies the mouse-event routing: blank-card presses
    # start a drag, buttons consume their own events.

    def _make_choice_handler(self, button: QPushButton, kind: str):
        """Close the dialog, remembering which action was clicked.

        Ghost buttons keep the old reject semantics (Esc, result codes,
        callers that only look at the dialog result); every other kind
        accepts. The kind is bound per button - deriving it from the clicked
        text inside the closure would break duplicate labels and re-lookups.
        """

        def handler():
            self.choice = button.text()
            # Cancel-flavoured buttons keep the old reject semantics (Esc,
            # result codes, callers that only look at the dialog result);
            # leading actions accept.
            if kind == "ghost":
                self.reject()
            else:
                self.accept()
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
            button.setStyleSheet(_BUTTON_KINDS[kind](palette))

    def _center_over_parent(self, parent):
        if parent is not None and parent.isVisible():
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2,
                      center.y() - self.height() // 2)
        else:
            # Tray-only flows (update popup, download results) have no visible
            # parent; centering over the screen beats Qt's default corner-ish
            # placement for a parentless dialog.
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(geo.center().x() - self.width() // 2,
                          geo.center().y() - self.height() // 2)
            return
        # Centering over a parent parked near a screen edge (the 305px calendar
        # sits bottom-right) can push a 340px dialog partly off-screen; the drag
        # clamp only helps while dragging, so clamp the centered position against
        # the parent's screen here.
        screen = parent.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(self.x(), geo.right() - self.width()))
            y = max(geo.top(), min(self.y(), geo.bottom() - self.height()))
            self.move(x, y)

    # --- ready-made flows -------------------------------------------------------

    @staticmethod
    def ask(parent, title: str, message: str, *, detail: str = "",
            confirm_text: str = "تایید", cancel_text: str = "انصراف", danger: bool = True,
            glyph: Optional[str] = None, width: int = 340) -> bool:
        """Build, center over ``parent`` and run the dialog; True on confirm."""
        dialog = ConfirmDialog(parent, title, message, detail=detail,
                               confirm_text=confirm_text, cancel_text=cancel_text,
                               danger=danger, glyph=glyph, width=width)
        dialog.adjustSize()
        dialog._center_over_parent(parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def choose(parent, title: str, message: str, *,
               actions: List[Tuple[str, str]], danger: bool = False,
               detail: str = "", glyph: Optional[str] = None,
               width: int = 340) -> Optional[str]:
        """Run an N-way ask and return the clicked action's text (None = dismissed)."""
        dialog = ConfirmDialog(parent, title, message, danger=danger, detail=detail,
                               glyph=glyph, actions=actions, width=width)
        dialog.adjustSize()
        dialog._center_over_parent(parent)
        dialog.exec()
        return dialog.choice

    @staticmethod
    def notify(parent, title: str, message: str, *, danger: bool = False,
               glyph: Optional[str] = None, button_text: str = "باشه",
               width: int = 340) -> None:
        """Single-button themed notice (replaces the stock informational boxes).

        Failure notices (``danger=True``) style the OK button in the holiday red
        of the destructive actions instead of the accent blue, so an error dialog
        reads as an error at a glance - icon, badge and button all agree.
        """
        ConfirmDialog.choose(parent, title, message,
                             actions=[(button_text, "danger" if danger else "accent")],
                             danger=danger, glyph=glyph, width=width)
