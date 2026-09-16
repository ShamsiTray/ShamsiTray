"""
Themed Update Download Dialog
-----------------------------

`DownloadUpdateDialog` replaces the stock ``QProgressDialog`` that used to
show the installer download. The stock dialog was the last native-styled
surface in the update flow (the popup, the completion ask and every notice
are already themed ``ConfirmDialog``s), and it ignored the app palette
entirely.

Design notes:
- Same frameless rounded card as ``ConfirmDialog``: translucent background,
  painted rounded rect in the palette colors, Vazirmatn everywhere.
- The progress bar switches between determinate (percent, when GitHub sends
  Content-Length) and busy (indeterminate) modes automatically.
- Percent and megabyte counters render with Persian digits; a total of -1 or
  0 (unknown size) keeps the bar busy and shows only received megabytes.
- Cancel emits ``canceled``; the controller wires that to
  ``UpdateChecker.cancel_download`` which aborts the reply (the subsequent
  ``download_failed("canceled")`` is already handled quietly there). Esc and
  the close path go through ``reject`` so they cancel the download too.
- Draggable from blank surfaces, like every other frameless card.
"""
from typing import Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QVBoxLayout)

from config import APP_CONFIG
from utils.date_utils import to_persian_digits
from utils.ui_helpers import (FramelessDragMixin, danger_button_stylesheet,
                              paint_rounded_card)

_MB = 1024.0 * 1024.0


def _mb_str(value: int) -> str:
    """Megabytes with one decimal, Persian digits ('۸.۳')."""
    return to_persian_digits(f"{value / _MB:.1f}")


class DownloadUpdateDialog(FramelessDragMixin, QDialog):
    """Frameless themed progress card for the installer download."""

    canceled = pyqtSignal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # ApplicationModal: the download usually starts with no other window
        # open (tray flow), where WindowModal would guard nothing.
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(340)
        self._drag_position: Optional[QPoint] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(8)

        self.title_label = QLabel("دانلود بروزرسانی")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        self.message_label = QLabel(f"نسخه {version} در حال دریافت است…")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        main_layout.addWidget(self.message_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # busy until the first total arrives
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(14)
        main_layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        main_layout.addSpacing(6)

        button_row = QHBoxLayout()
        self.cancel_button = QPushButton("لغو")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel)
        button_row.addStretch()
        button_row.addWidget(self.cancel_button)
        button_row.addStretch()
        main_layout.addLayout(button_row)

        self.update_styles()

    # --- progress ---------------------------------------------------------------

    def set_progress(self, received: int, total: int):
        """Mirror a download_progress(received, total) signal (-1/0 = unknown)."""
        if total > 0:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
            percent = max(0, min(100, received * 100 // total))
            self.progress.setValue(percent)
            self.status_label.setText(
                f"{to_persian_digits(percent)}٪ — {_mb_str(received)} از {_mb_str(total)} مگابایت")
        else:
            # Size unknown (no Content-Length): back to the busy indicator and
            # show only what has arrived so far.
            if self.progress.maximum() != 0:
                self.progress.setRange(0, 0)
            self.status_label.setText(f"{_mb_str(max(received, 0))} مگابایت دریافت شد")

    def _cancel(self):
        # reject() emits `canceled` before closing, so the button and Esc
        # share one path and the signal is never emitted twice.
        self.reject()

    def reject(self):
        # Esc and any other dismiss path must abort the transfer as well.
        self.canceled.emit()
        super().reject()

    # --- look -------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_rounded_card(painter, self.rect(),
                           APP_CONFIG.current_palette['BACKGROUND_COLOR'],
                           APP_CONFIG.current_palette['MENU_BORDER_COLOR'], 15)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.title_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 16px; font-weight: bold; background: transparent; border: none;")
        self.message_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 13px; background: transparent; border: none;")
        self.progress.setStyleSheet(
            f"QProgressBar {{ background-color: {palette['INPUT_BG_COLOR']};"
            f" border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 7px; }}"
            f"QProgressBar::chunk {{ background-color: {palette['ACCENT_COLOR']}; border-radius: 6px; }}")
        self.status_label.setStyleSheet(
            f"color: {palette['ACCENT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 12px; font-weight: bold; background: transparent; border: none;")
        self.cancel_button.setStyleSheet(danger_button_stylesheet(palette))

    # --- dragging ---------------------------------------------------------------

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
