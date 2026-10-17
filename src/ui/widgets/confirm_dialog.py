"""
Themed Confirmation Dialog
--------------------------

`ConfirmDialog` is a small frameless, palette-aware replacement for the stock
``QMessageBox`` asks (delete / replace confirmations, update offers, notices).
A native message box ignores the app theme entirely - system-styled buttons,
wrong font, square corners - so destructive actions read as bolted-on.

The card itself (badge, title, message, detail box, buttons, painting) lives in
`confirm_card.ConfirmCard`; this class is only what makes it a *window*: modal
top-level flags, `exec()`, accept/reject, centering with screen clamping, and
whole-surface dragging. An in-calendar overlay needs the same card without any
of that, so the two share the mixin rather than a QWidget base - see
`confirm_overlay.ConfirmOverlay`.

Design notes:
- It is a real ``QDialog`` (``exec()`` works) but painted like every other
  frameless window of the app: rounded card, Vazirmatn, palette colors.
- ``WindowModal`` blocks only the parent window, so a prompt cannot freeze the
  whole application.
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

    # The open notice opened under a replacement key, and that key. A newer
    # result of the SAME key re-words this dialog instead of stacking a second
    # window; ordinary (unkeyed) notices are never tracked.
    _active_notice: Optional["ConfirmDialog"] = None
    _active_notice_key: Optional[str] = None

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

    def center_over_parent(self, parent):
        """Center over ``parent`` (or the screen when there is no visible one),
        clamped to the screen so a dialog near an edge stays fully on it."""
        if parent is not None and parent.isVisible():
            # mapToGlobal, not geometry(): geometry() is parent-relative for a
            # child widget, so a dialog centered over one would land at that
            # relative offset on the screen instead.
            center = parent.mapToGlobal(parent.rect().center())
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

    def exec_centered(self, parent=None):
        """The shared tail of every dialog flow: size, center, run modally.

        Callers that must keep a reference to the dialog itself (the update
        popup raises it when a manual check lands while it is up) build it by
        hand and end with this method instead of duplicating the tail; the
        ready-made flows below go through it too, so a change to how dialogs
        are presented cannot diverge between them. Returns the QDialog exec()
        result code.
        """
        self._refit()
        self.center_over_parent(parent)
        return self.exec()

    @staticmethod
    def ask(parent, title: str, message: str, *, detail: str = "",
            confirm_text: str = "تایید", cancel_text: str = "انصراف", danger: bool = True,
            glyph: Optional[str] = None, width: int = 340) -> bool:
        """Build, center over ``parent`` and run the dialog; True on confirm."""
        dialog = ConfirmDialog(parent, title, message, detail=detail,
                               confirm_text=confirm_text, cancel_text=cancel_text,
                               danger=danger, glyph=glyph, width=width)
        return dialog.exec_centered(parent) == QDialog.DialogCode.Accepted

    @staticmethod
    def choose(parent, title: str, message: str, *,
               actions: List[Tuple[str, str]], danger: bool = False,
               detail: str = "", glyph: Optional[str] = None,
               width: int = 340) -> Optional[str]:
        """Run an N-way ask and return the clicked action's text (None = dismissed)."""
        dialog = ConfirmDialog(parent, title, message, danger=danger, detail=detail,
                               glyph=glyph, actions=actions, width=width)
        dialog.exec_centered(parent)
        return dialog.choice

    @staticmethod
    def notify(parent, title: str, message: str, *, detail: str = "",
               danger: bool = False,
               glyph: Optional[str] = None, button_text: str = "باشه",
               width: int = 340, key: Optional[str] = None) -> None:
        """Single-button themed notice (replaces the stock informational boxes).

        Takes the same ``detail`` line as ``ask``/``choose`` so a notice can show
        a breakdown under its headline.

        Failure notices (``danger=True``) style the OK button in the holiday red
        of the destructive actions instead of the accent blue, so an error dialog
        reads as an error at a glance - icon, badge and button all agree.

        ``key`` opts a notice into single-instance replacement: while a notice
        opened under the same key is up, a new call re-words it in place and
        raises it rather than opening a second window. Unkeyed notices (every
        other caller) keep the ordinary, untracked modal behavior.
        """
        if key is None:
            ConfirmDialog.choose(parent, title, message,
                                 actions=[(button_text, "danger" if danger else "accent")],
                                 danger=danger, detail=detail, glyph=glyph, width=width)
            return
        existing = ConfirmDialog._active_notice
        if existing is not None and ConfirmDialog._active_notice_key == key:
            existing.apply_notice(title, message, detail=detail, danger=danger,
                                  glyph=glyph, button_text=button_text)
            existing.setWindowTitle(title)
            existing.raise_()
            existing.activateWindow()
            return
        dialog = ConfirmDialog(parent, title, message, detail=detail, danger=danger,
                               glyph=glyph, width=width,
                               actions=[(button_text, "danger" if danger else "accent")])
        ConfirmDialog._active_notice = dialog
        ConfirmDialog._active_notice_key = key
        try:
            dialog.exec_centered(parent)
        finally:
            ConfirmDialog._clear_active_notice(dialog)

    @staticmethod
    def _clear_active_notice(dialog) -> None:
        """Drop the tracked notice only if it is still ``dialog``.

        The identity guard is what stops an older, dismissed dialog's cleanup
        from clearing a newer instance that already took the slot.
        """
        if ConfirmDialog._active_notice is dialog:
            ConfirmDialog._active_notice = None
            ConfirmDialog._active_notice_key = None

    @staticmethod
    def dismiss_active_notice(key: str) -> bool:
        """Reject the open notice opened under ``key``; True if one was dismissed.

        The tracked references are cleared BEFORE rejecting: the dialog's own
        ``finally`` then sees a non-matching identity and cannot double-clear (or
        clear a newer instance). A second call finds the reference clear and is a
        no-op, so it is safe to call again.
        """
        dialog = ConfirmDialog._active_notice
        if dialog is None or ConfirmDialog._active_notice_key != key:
            return False
        ConfirmDialog._active_notice = None
        ConfirmDialog._active_notice_key = None
        dialog.reject()
        return True
