"""
Custom Dialog Widgets
---------------------

This module contains custom dialog-like widgets used in the application,
such as the 'Go To Date' panel for the calendar.
"""
import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QRegularExpression
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRegularExpressionValidator, QPen
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QHBoxLayout

from config import APP_CONFIG
from utils.date_utils import from_persian_digits, persian_month_name, to_persian_digits
from utils.ui_utils import apply_combo_style

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
        
        self.month_combo = QComboBox()
        apply_combo_style(self.month_combo)
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
        
        main_layout.addLayout(button_layout)
    
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

        scrollbar_style = (
            f"QAbstractItemView::verticalScrollBar {{ border: none; background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; width: 8px; margin: 0px; border-radius: 4px; }}"
            f"QAbstractItemView::verticalScrollBar::handle {{ background-color: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: 4px; min-height: 20px; }}")
        
        combo_style = (
            f"QComboBox {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; }}"
            f"QComboBox:focus, QComboBox::on, QComboBox:hover {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
            f"QComboBox::drop-down {{ border: 0px; }}"
            f"QComboBox QAbstractItemView {{ background-color: {palette['BACKGROUND_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; outline: 0px; }}"
            f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; min-height: 25px; border: none }}"
            f"QComboBox QAbstractItemView::item:hover {{ background-color: {palette['HOVER_BG']}; border-radius: 4px; }}"
            f"QComboBox QAbstractItemView::item:selected {{ background-color: {palette['ACCENT_COLOR']}; color: white; border-radius: 4px; }}"
            f"QComboBox QAbstractItemView::item:selected:hover {{background-color: {palette['ACCENT_COLOR']}; color: white; }}" + scrollbar_style)

        self.month_combo.setStyleSheet(combo_style)
        self.month_combo.view().setStyleSheet(f"QListView {{ background-color: {palette['BACKGROUND_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}")
        
        self.year_input.setStyleSheet(
            f"QLineEdit {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}"
            f"QLineEdit:hover {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
            f"QLineEdit::placeholder {{ color: {palette['GREY_COLOR']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {palette['ACCENT_COLOR']}; }}")

        self.confirm_button.setStyleSheet(
            f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).lighter(110).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}")
        
        cancel_button_style = (
            f"QPushButton {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(120).name()}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(110).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(140).name()}; }}")
        self.cancel_button.setStyleSheet(cancel_button_style)
        
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