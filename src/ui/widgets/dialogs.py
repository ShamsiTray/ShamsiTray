"""
Custom Dialog Widgets
---------------------

This module contains custom dialog-like widgets used in the application,
such as the 'Go To Date' panel for the calendar.
"""
import jdatetime
from PyQt5.QtCore import QEvent, Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QColor, QIntValidator, QPainter, QPainterPath
from PyQt5.QtWidgets import (QComboBox, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget, QHBoxLayout)

from config import APP_CONFIG
from utils.date_helpers import from_persian_digits, persian_month_name, to_persian_digits

class GoToDateWindow(QWidget):
    """A small, non-movable window to jump to a specific month and year."""
    date_selected = pyqtSignal(int, int)
    MIN_YEAR = 1200
    MAX_YEAR = 1600
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.setWindowTitle("برو به تاریخ")
        self.setFixedSize(200, 230) # Fixed size prevents layout shifts and keeps the dialog compact
        self.setLayoutDirection(Qt.RightToLeft)
        self._setup_ui()
        self.update_styles()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        radius = 15 # Corner radius tuned for small dialog size
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['MENU_BORDER_COLOR']))
        painter.drawPath(path)
        
        painter.setClipPath(path)
        super().paintEvent(event)

    def eventFilter(self, obj, event):
        """Force QComboBox popup on click, even when its line edit is read-only."""
        if event.type() == QEvent.MouseButtonPress and obj is self.month_combo.lineEdit():
            if not self.month_combo.view().isVisible():
                self.month_combo.showPopup()
            return True
        return super().eventFilter(obj, event)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.title_label = QLabel("برو به تاریخ")
        self.title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.title_label)
        
        self.month_combo = QComboBox()
        month_names = [f"{to_persian_digits(str(i).zfill(2))} - {persian_month_name(i)}" for i in range(1, 13)]
        self.month_combo.addItems(month_names)
        self.month_combo.view().setLayoutDirection(Qt.RightToLeft)
        
        line_edit = QLineEdit(self)
        line_edit.setAlignment(Qt.AlignCenter)
        line_edit.setReadOnly(True)
        line_edit.setContextMenuPolicy(Qt.NoContextMenu)
        line_edit.installEventFilter(self)
        self.month_combo.setLineEdit(line_edit)
        main_layout.addWidget(self.month_combo)
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("سال")
        self.year_input.setValidator(QIntValidator(self.MIN_YEAR, self.MAX_YEAR))
        self.year_input.setAlignment(Qt.AlignCenter)
        self.year_input.setContextMenuPolicy(Qt.NoContextMenu)
        main_layout.addWidget(self.year_input)
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
        main_layout.addLayout(button_layout)
        
    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        p = palette
        self.setStyleSheet("GoToDateWindow { background-color: transparent; }")

        self.title_label.setStyleSheet(f"color: {p['TEXT_COLOR']}; "
                                       f"font-family: '{APP_CONFIG.FONT_FAMILY}'; "
                                       "font-size: 18px; font-weight: bold; "
                                       "border: none; background: transparent;")

        scrollbar_style = (f"QAbstractItemView::verticalScrollBar {{ border: none; background-color: {p['SCROLLBAR_GROOVE_COLOR']}; width: 8px; margin: 0px; border-radius: 4px; }}"
                           f"QAbstractItemView::verticalScrollBar::handle {{ background-color: {p['SCROLLBAR_HANDLE_COLOR']}; border-radius: 4px; min-height: 20px; }}")
        
        input_font_size = 14
        
        combo_style = (f"QComboBox {{ background-color: {p['INPUT_BG_COLOR']}; color: {p['TEXT_COLOR']}; border: 1px solid {p['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: {input_font_size}px; }}"
                       f"QComboBox:focus, QComboBox::on {{ border: 1px solid {p['ACCENT_COLOR']}; }}"
                       f"QComboBox::drop-down {{ border: 0px; }}"
                       f"QComboBox QLineEdit {{ background-color: transparent; border: none; }}"
                       f"QComboBox QAbstractItemView {{ background-color: {p['BACKGROUND_COLOR']}; color: {p['TEXT_COLOR']}; border: 1px solid {p['MENU_BORDER_COLOR']}; border-radius: 8px; outline: 0px; }}"
                       f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; }}"
                       f"QComboBox QAbstractItemView::item:hover {{ background-color: {p['HOVER_BG']}; border-radius: 4px; }}"
                       f"QComboBox QAbstractItemView::item:selected {{ background-color: {p['ACCENT_COLOR']}; color: white; border-radius: 4px; }}" + scrollbar_style)

        self.month_combo.setStyleSheet(combo_style)
        self.month_combo.view().setStyleSheet(f"QListView {{ background-color: {p['BACKGROUND_COLOR']}; color: {p['TEXT_COLOR']}; border: 1px solid {p['MENU_BORDER_COLOR']}; selection-background-color: {p['ACCENT_COLOR']}; selection-color: white; }}")
        self.month_combo.lineEdit().setStyleSheet(f"color: {p['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: {input_font_size}px;")

        self.year_input.setStyleSheet(f"QLineEdit {{ background-color: {p['INPUT_BG_COLOR']}; color: {p['TEXT_COLOR']}; border: 1px solid {p['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: {input_font_size}px; }}"
                                      f"QLineEdit::placeholder {{ color: {p['GREY_COLOR']}; }}"
                                      f"QLineEdit:focus {{ border: 1px solid {p['ACCENT_COLOR']}; }}")

        self.confirm_button.setStyleSheet(f"QPushButton {{ background-color: {p['ACCENT_COLOR']}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
                                          f"QPushButton:hover {{ background-color: {QColor(p['ACCENT_COLOR']).lighter(110).name()}; }}"
                                          f"QPushButton:pressed {{ background-color: {QColor(p['ACCENT_COLOR']).darker(120).name()}; }}")
        
        cancel_button_style = (f"QPushButton {{ background-color: transparent; color: {p['TEXT_COLOR']}; border: 1px solid {p['GREY_COLOR']}; "
                               f"border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
                               f"QPushButton:hover {{ background-color: {p['HOVER_BG']}; border-color: {p['TEXT_COLOR']}; }}")
        self.cancel_button.setStyleSheet(cancel_button_style)
        
    def _on_confirm(self):
        year_str = self.year_input.text()
        if not year_str:
            return
        try:
            year = int(from_persian_digits(year_str))
            if not self.MIN_YEAR <= year <= self.MAX_YEAR:
                return
            month = self.month_combo.currentIndex() + 1
            self.date_selected.emit(year, month)
            self.close()
        except (ValueError, TypeError):
            # Invalid input is silently ignored to keep the dialog lightweight
            return
