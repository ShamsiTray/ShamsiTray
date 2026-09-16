"""
Go To Date Widget
---------------------

This module contains custom dialog-like widgets used in the application,
such as the 'Go To Date' panel for the calendar.
"""
import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QRegularExpression
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRegularExpressionValidator, QPen
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QHBoxLayout

from config import APP_CONFIG
from utils.date_utils import from_persian_digits, persian_month_name, to_persian_digits
from utils.ui_helpers import (DigitsFirstCombo, accent_button_stylesheet,
                              combo_stylesheet, danger_button_stylesheet,
                              error_line_edit_stylesheet, line_edit_stylesheet)

# The «NN - month» items mix digits with Persian text, which is bidi-ambiguous:
# their visual order depends on the base direction of whatever paints them.
# DigitsFirstCombo pins closed label and popup rows to the digits-first order
# («۰۶ - شهریور") on every platform.

class GoToDateWindow(QWidget):
    """A small, non-movable window to jump to a specific month and year."""
    date_selected = pyqtSignal(int, int)
    MIN_YEAR = 1200
    MAX_YEAR = 1600

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("برو به تاریخ")
        self._initial_height = 200
        self.setFixedSize(200, self._initial_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._year_error = False
        self._setup_ui()
        self.update_styles()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 15
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        pen = QPen(QColor(APP_CONFIG.current_palette['MENU_BORDER_COLOR']))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.title_label = QLabel("برو به تاریخ")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        self.month_combo = DigitsFirstCombo()
        self.month_combo.setMaxVisibleItems(5)
        month_names = [f"{to_persian_digits(str(i).zfill(2))} - {persian_month_name(i)}" for i in range(1, 13)]
        for name in month_names:
            self.month_combo.addItem(name)
            last_index = self.month_combo.count() - 1
            self.month_combo.setItemData(last_index, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)
        main_layout.addWidget(self.month_combo)

        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("سال (از ۱۲۰۰ تا ۱۶۰۰)")
        regex = QRegularExpression("^[0-9۰-۹]{0,4}$")
        validator = QRegularExpressionValidator(regex)
        self.year_input.setValidator(validator)
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.year_input)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        main_layout.addWidget(self.error_label)

        today = jdatetime.date.today()
        self.month_combo.setCurrentIndex(today.month - 1)
        self.year_input.setText(to_persian_digits(today.year))

        main_layout.addStretch(1)

        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("تایید")
        self.cancel_button = QPushButton("لغو")
        button_layout.addWidget(self.confirm_button)
        button_layout.addWidget(self.cancel_button)

        self.confirm_button.clicked.connect(self._on_confirm)
        self.cancel_button.clicked.connect(self.close)
        self.year_input.returnPressed.connect(self._on_confirm)
        self.year_input.textChanged.connect(self._clear_error)
        self.year_input.textChanged.connect(self._update_year_error_state)

        main_layout.addLayout(button_layout)

    def _year_is_out_of_range(self) -> bool:
        text = self.year_input.text().strip()
        if not text:
            return False
        try:
            year = int(from_persian_digits(text))
        except ValueError:
            return False
        return not self.MIN_YEAR <= year <= self.MAX_YEAR

    def _update_year_error_state(self, *_args):
        errored = self._year_is_out_of_range()
        if self._year_error == errored:
            return
        self._year_error = errored
        self._apply_year_style()

    def _apply_year_style(self):
        palette = APP_CONFIG.get_current_palette()
        style = (error_line_edit_stylesheet(palette, padding="5px", center_text=True)
                 if self._year_error
                 else line_edit_stylesheet(palette, padding="5px", center_text=True,
                                           placeholder_color=palette['GREY_COLOR']))
        self.year_input.setStyleSheet(style)

    def _clear_error(self):
        """Clear error and reset window size when user types."""
        if self.error_label.isVisible():
            self.error_label.hide()
            self.setFixedSize(200, self._initial_height)

    def _show_error(self, message: str):
        """Show error and resize window to fit error message."""
        self.error_label.setText(message)
        self.error_label.show()

        error_height = 230
        self.setFixedSize(200, error_height)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet("GoToDateWindow { background-color: transparent; }")

        self.title_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 18px; font-weight: bold; border: none; background: transparent;")

        self.error_label.setStyleSheet(f"color: red; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; border: none; background: transparent;")

        self.month_combo.setStyleSheet(combo_stylesheet(
            palette,
            padding="5px",
            center_text=True,
            dropdown_bg=palette['BACKGROUND_COLOR'],
            dropdown_border_key='MENU_BORDER_COLOR',
            scrollbar_width=8,
            zero_drop_down=False))
        self.month_combo.view().setStyleSheet(f"QListView {{ background-color: {palette['BACKGROUND_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}")

        self._apply_year_style()

        self.confirm_button.setStyleSheet(accent_button_stylesheet(palette))
        self.cancel_button.setStyleSheet(danger_button_stylesheet(palette))

    def _on_confirm(self):
        year_str = self.year_input.text()
        if not year_str:
            self._show_error("لطفاً سال را وارد کنید")
            return

        try:
            year = int(from_persian_digits(year_str))
            if not self.MIN_YEAR <= year <= self.MAX_YEAR:
                min_y = to_persian_digits(str(self.MIN_YEAR))
                max_y = to_persian_digits(str(self.MAX_YEAR))
                self._show_error(f"سال باید بین {min_y} تا {max_y} باشد")
                return

            month = self.month_combo.currentIndex() + 1
            self.date_selected.emit(year, month)
            self.close()
        except (ValueError, TypeError):
            self._show_error("ورودی نامعتبر است")
