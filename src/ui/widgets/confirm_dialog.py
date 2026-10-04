"""
Themed Confirmation Dialog
--------------------------

`ConfirmDialog` is a small frameless, palette-aware replacement for the stock
``QMessageBox`` asks (delete / replace confirmations, update offers, notices).
The native message box ignored the app theme entirely - system-styled buttons,
wrong font, square corners - so destructive actions felt bolted-on.

The card itself (badge, title, message, detail box, buttons, painting) lives in
`confirm_card.ConfirmCard`; this class is only what makes it a *window*: modal
top-level flags, `exec()`, accept/reject, centering with screen clamping, and
whole-surface dragging. An in-calendar overlay needs the same card without any
of that, so the two share the mixin rather than a QWidget base - see
`confirm_overlay.ConfirmOverlay`.

Design notes:
- It is a real ``QDialog`` (``exec()`` works) but painted like every other
  frameless window of the app: rounded card, Vazirmatn, palette colors.
- ``WindowModal`` blocks only the parent window, matching the old ``exec()``
  behaviour on the parent without freezing the whole application.
- The card is draggable from any of its blank surfaces (labels and stretches
  pass mouse events through to the dialog; buttons consume their own), with
  the same screen clamping the frameless windows use - a centered dialog is
  only its *initial* position, not a life sentence.
- Besides the two-button ``ask`` there is ``choose`` (three-way questions like
  the update popup's download/ignore/remind) and ``notify`` (single-button
  notices such as "no updates"), so no native message box remains anywhere in
  the app's interactive flows.
"""
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog

from config import APP_CONFIG
from ui.widgets.confirm_card import ConfirmCard
from utils.ui_helpers import FramelessDragMixin


class ConfirmDialog(FramelessDragMixin, ConfirmCard, QDialog):
    """A themed modal ask: icon badge, title, short message, detail box, buttons."""

    def __init__(self, parent, title: str, message: str, *, detail: str = "",
                 confirm_text: str = "تایید", cancel_text: str = "انصراف",
                 danger: bool = True, width: int = 340,
                 glyph: Optional[str] = None,
                 actions: Optional[List[Tuple[str, str]]] = None):
        # The mixin's cooperative __init__ builds the card and its fixed width;
        # the window flags below are what make it a dialog, and re-asserting
        # them after is harmless because Qt only evaluates native flags on show.
        super().__init__(parent, title, message, detail=detail,
                         confirm_text=confirm_text, cancel_text=cancel_text,
                         danger=danger, glyph=glyph, width=width, actions=actions)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        # Frameless cards still carry a native title for Alt-Tab / taskbar
        # previews: give every dialog the ACTION's name, not the generic app
        # name, so each surface reads as its own thing.
        self.setWindowTitle(title)
        if APP_CONFIG.ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))

    def _finish_choice(self, kind: str) -> None:
        """Close the dialog, remembering which action was clicked.

        Ghost buttons keep reject semantics (Esc, result codes, callers that
        only look at the dialog result); every other kind accepts.
        """
        if kind == "ghost":
            self.reject()
        else:
            self.accept()

    # --- dragging ---------------------------------------------------------------
    # FramelessDragMixin supplies the mouse-event routing: blank-card presses
    # start a drag, buttons consume their own events.

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
    def notify(parent, title: str, message: str, *, detail: str = "",
               danger: bool = False,
               glyph: Optional[str] = None, button_text: str = "باشه",
               width: int = 340) -> None:
        """Single-button themed notice (replaces the stock informational boxes).

        Takes the same ``detail`` line as ``ask``/``choose`` so a notice can show
        a breakdown under its headline.

        Failure notices (``danger=True``) style the OK button in the holiday red
        of the destructive actions instead of the accent blue, so an error dialog
        reads as an error at a glance - icon, badge and button all agree.
        """
        ConfirmDialog.choose(parent, title, message,
                             actions=[(button_text, "danger" if danger else "accent")],
                             danger=danger, detail=detail, glyph=glyph, width=width)
