"""
Date Converter Window
---------------------

This module provides the `DateConverterWindow`, a tool for converting dates
between Jalali (Shamsi) and Gregorian calendars. It features input validation,
dynamic day/month population, and calculates elapsed time from the present.
"""
import sys
import datetime

import jdatetime
from PyQt6.QtCore import Qt, QTimer, QRegularExpression
from PyQt6.QtGui import (QColor, QFont, QIcon, QPalette, QRegularExpressionValidator, QCursor)
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout, QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QGraphicsOpacityEffect)

from config import APP_CONFIG
from utils.date_helpers import (from_persian_digits, to_persian_digits, is_gregorian_leap_year, is_jalali_leap_year, persian_month_name, gregorian_month_name, persian_weekday_name)
from utils.logging_setup import setup_logging
from .base_window import BaseFramelessWindow
from utils.ui_helpers import apply_combo_style
from ui.widgets.custom_tooltip import CustomTooltip

logger = setup_logging(__name__)

try:
    from dateutil.relativedelta import relativedelta
    RELATIVEDELTA_AVAILABLE = True
except ImportError:
    logger.warning("dateutil.relativedelta not available. Elapsed time calculation will be less precise.")
    RELATIVEDELTA_AVAILABLE = False

try:
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    logger.warning("win32api not available. Window style modifications will be skipped.")
    WIN32_AVAILABLE = False

class DateConverterWindow(BaseFramelessWindow):
    """A window for converting dates between Jalali and Gregorian calendars."""
    MIN_JALALI_YEAR, MAX_JALALI_YEAR = 1, 1600
    MIN_GREGORIAN_YEAR, MAX_GREGORIAN_YEAR = 622, 2200

    def __init__(self):
        super().__init__()
        self._initial_height = 260
        self.setWindowTitle("تبدیل تاریخ")
        self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(650, self._initial_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self._setup_ui()
        self.update_styles()
        self._connect_signals()
        
        self._initialize_date_inputs()
        self._apply_windows_styles()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.year_input.setFocus)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        main_layout.addLayout(self._create_title_bar())
        main_layout.addSpacing(10)
        main_layout.addLayout(self._create_input_section())
        main_layout.addSpacing(10)
        
        self.convert_button = QPushButton("تبدیل")
        main_layout.addWidget(self.convert_button)
        main_layout.addSpacing(10)

        self.middle_divider = self._create_divider()
        main_layout.addWidget(self.middle_divider)
        main_layout.addSpacing(10)

        self.output_widget = self._create_output_section()
        main_layout.addWidget(self.output_widget)
        
        self.status_message = QLabel("")
        self.status_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_message)
        main_layout.addStretch(1)

        self.middle_divider.hide()
        self.output_widget.hide()
        self.status_message.hide()

    def _set_combo_items(self, combo: QComboBox, items: list):
        combo.clear()
        for text in items:
            combo.addItem(text)
            combo.setItemData(combo.count() - 1, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)

    def _create_title_bar(self) -> QHBoxLayout:
        self.exit_button = QPushButton("✕")
        self.minimize_button = QPushButton("—")
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.exit_button, alignment=Qt.AlignmentFlag.AlignTop)
        button_layout.addWidget(self.minimize_button, alignment=Qt.AlignmentFlag.AlignTop)
        button_layout.addStretch(1)
        return button_layout

    def _create_input_section(self) -> QHBoxLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(5)
        labels = {"نوع تبدیل": (0, 0), "روز": (0, 1), "ماه": (0, 2), "سال": (0, 3)}
        self.input_labels = []
        for text, pos in labels.items():
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, pos[0], pos[1])
            self.input_labels.append(label)

        self.conversion_type_combo = QComboBox()
        self.day_combo = QComboBox()
        self.month_combo = QComboBox()
        
        apply_combo_style(self.conversion_type_combo)
        apply_combo_style(self.day_combo)
        apply_combo_style(self.month_combo)

        self._set_combo_items(self.conversion_type_combo, ["شمسی به میلادی", "میلادی به شمسی"])
        self.year_input = QLineEdit()
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        regex = QRegularExpression("^[0-9۰-۹]{0,4}$")
        validator = QRegularExpressionValidator(regex)
        self.year_input.setValidator(validator)

        grid.addWidget(self.conversion_type_combo, 1, 0)
        grid.addWidget(self.day_combo, 1, 1)
        grid.addWidget(self.month_combo, 1, 2)
        grid.addWidget(self.year_input, 1, 3)
        wrapper_layout = QHBoxLayout()
        wrapper_layout.addStretch(1)
        wrapper_layout.addLayout(grid)
        wrapper_layout.addStretch(1)
        return wrapper_layout

    def _create_output_section(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)

            self.output_grid = QGridLayout()
            self.output_grid.setContentsMargins(20, 0, 20, 0)
            self.output_grid.setVerticalSpacing(0) 
            self.output_grid.setHorizontalSpacing(20)

            greg_title = QLabel("تاریخ میلادی")
            greg_title.setObjectName("OutputTitleLabel")
            greg_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            jalali_title = QLabel("تاریخ شمسی")
            jalali_title.setObjectName("OutputTitleLabel")
            jalali_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self.gregorian_date_value_1 = QLabel("...")
            self.gregorian_date_value_2 = QLabel("...")
            self.jalali_date_value_1 = QLabel("...")
            self.jalali_date_value_2 = QLabel("...")

            for lbl in [self.gregorian_date_value_1, self.gregorian_date_value_2, 
                    self.jalali_date_value_1, self.jalali_date_value_2]:
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setWordWrap(False)
                lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                lbl.mousePressEvent = (lambda event, label=lbl: self._copy_to_clipboard(label) if event.button() == Qt.MouseButton.LeftButton else None)

            self.output_grid.addWidget(greg_title, 0, 0)
            self.output_grid.addWidget(jalali_title, 0, 2)

            self.output_grid.addWidget(self.gregorian_date_value_1, 1, 0)
            self.output_grid.addWidget(self.jalali_date_value_1, 1, 2)

            self.output_grid.addWidget(self.gregorian_date_value_2, 2, 0)
            self.output_grid.addWidget(self.jalali_date_value_2, 2, 2)

            self.output_grid.setColumnStretch(1, 1)

            layout.addLayout(self.output_grid)
            layout.addSpacing(10)

            self.elapsed_text = QLabel("...")
            self.elapsed_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.leap_year_status = QLabel("...")
            self.leap_year_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.leap_year_status_opacity_effect = QGraphicsOpacityEffect(self)
            self.leap_year_status.setGraphicsEffect(self.leap_year_status_opacity_effect)
            
            layout.addWidget(self.elapsed_text)
            layout.addWidget(self.leap_year_status)
            
            return widget

    def _create_divider(self) -> QFrame:
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        return divider

    def update_styles(self):
        palette = self.palette()
        p = APP_CONFIG.get_current_palette()
        text_color = p['TEXT_COLOR']
        palette.setColor(QPalette.ColorRole.WindowText, QColor(text_color))
        palette.setColor(QPalette.ColorRole.Text, QColor(text_color))
        self.setPalette(palette)
        for label in self.findChildren(QLabel):
            if not label.objectName():
                label.setStyleSheet(f"color: {text_color};")
        
        input_field_height = 40
        input_bg = p['INPUT_BG_COLOR']
        border_color = p['CALENDAR_BORDER_COLOR']
        accent_color = p['ACCENT_COLOR']
        scrollbar_style = (f"QAbstractItemView::verticalScrollBar {{ border: none; background-color: {p['SCROLLBAR_GROOVE_COLOR']}; width: 10px; margin: 0px; border-radius: 5px; }}"
                           f"QAbstractItemView::verticalScrollBar::handle {{ background-color: {p['SCROLLBAR_HANDLE_COLOR']}; border-radius: 5px; min-height: 20px; }}"
                           f"QAbstractItemView::add-line:vertical, QAbstractItemView::sub-line:vertical {{ height: 0px; }} QAbstractItemView::add-page:vertical, QAbstractItemView::sub-page:vertical {{ background: none; }}")
        combo_style = (f"QComboBox {{ background-color: {input_bg}; color: {text_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 8px 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; text-align: center; selection-background-color: {p['ACCENT_COLOR']}; selection-color: white;}}"
                       f"QComboBox:hover {{ border: 1px solid {accent_color}; }}"
                       f"QComboBox:focus, QComboBox::on {{ border: 1px solid {accent_color}; }}"
                       f"QComboBox::drop-down {{ border: 0px; width: 0px; height: 0px; }}"
                       f"QComboBox QAbstractItemView {{ background-color: {input_bg}; color: {text_color}; selection-background-color: {accent_color}; border: 1px solid {border_color}; border-radius: 8px; outline: none;}}"
                       f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; min-height: 25px; border: none; }}"
                       f"QComboBox QAbstractItemView::item:hover {{ background-color: {p['HOVER_BG']}; border-radius: 4px; }}"
                       f"QComboBox QAbstractItemView::item:selected {{ background-color: {p['ACCENT_COLOR']}; color: white; border-radius: 4px; }}"
                       f"QComboBox QAbstractItemView::item:selected:hover {{background-color: {p['ACCENT_COLOR']}; color: white; }}" + scrollbar_style)
        
        base_button_style = f"border: 1px solid {border_color}; border-radius: 8px; font-size: 18px; font-weight: bold; color: {text_color};"
        self.exit_button.setFixedSize(30, 30)
        self.exit_button.setStyleSheet(f"QPushButton {{ background-color: #FF4C4C; {base_button_style} }} QPushButton:hover {{ background-color: #FF6666; }}")
        self.minimize_button.setFixedSize(30, 30)
        self.minimize_button.setStyleSheet(f"QPushButton {{ background-color: {p['BACKGROUND_COLOR']}; {base_button_style} }} QPushButton:hover {{ background-color: {p['HOVER_BG']}; }}")
        for label in self.input_labels:
             label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
             label.setFixedHeight(input_field_height)
        self.conversion_type_combo.setFixedSize(220, input_field_height)
        self.day_combo.setFixedSize(80, input_field_height)
        self.month_combo.setFixedSize(140, input_field_height)
        for combo in [self.conversion_type_combo, self.day_combo, self.month_combo]:
            combo.setStyleSheet(combo_style)
        self.year_input.setFixedSize(100, input_field_height)
        self.year_input.setStyleSheet(f"QLineEdit {{ background-color: {input_bg}; color: {text_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 8px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; text-align: center; selection-background-color: {p['ACCENT_COLOR']}; selection-color: white;}} QLineEdit:focus {{ border: 1px solid {accent_color}; selection-background-color: {p['ACCENT_COLOR']}; selection-color: white; }} QLineEdit:hover {{ border: 1px solid {accent_color}; }}")
        self.convert_button.setFixedHeight(50)
        self.convert_button.setStyleSheet(f"QPushButton {{ background-color: {accent_color}; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }} QPushButton:hover {{ background-color: {QColor(accent_color).lighter(110).name()}; }} QPushButton:pressed {{ background-color: {QColor(accent_color).darker(120).name()}; }}")
        self.middle_divider.setStyleSheet(f"color: {border_color};")
        for label in self.output_widget.findChildren(QLabel):
            if label.objectName() == "OutputTitleLabel":
                 label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 16, QFont.Weight.Bold))
                 label.setStyleSheet(f"color: {accent_color}; padding: 5px;")
        self.jalali_date_value_1.setFont(QFont(APP_CONFIG.FONT_FAMILY, 15, QFont.Weight.Bold))
        self.jalali_date_value_2.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
        self.gregorian_date_value_1.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 15, QFont.Weight.Bold))
        self.gregorian_date_value_2.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 14))
        self.elapsed_text.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
        self.leap_year_status.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.status_message.setStyleSheet("color: red; font-weight: bold; font-size: 18px;")

    def _connect_signals(self):
        self.exit_button.clicked.connect(self.close)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.conversion_type_combo.currentIndexChanged.connect(self._on_conversion_type_changed)
        self.month_combo.currentIndexChanged.connect(self._update_day_dropdown)
        self.year_input.textChanged.connect(self._update_day_dropdown)
        self.day_combo.currentIndexChanged.connect(self._clear_results)
        self.month_combo.currentIndexChanged.connect(self._clear_results)
        self.year_input.textChanged.connect(self._clear_results)
        self.convert_button.clicked.connect(self._convert_date)
        self.year_input.returnPressed.connect(self._convert_date)
        self.conversion_type_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.day_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.month_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.year_input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _copy_to_clipboard(self, label: QLabel):
        """Copy the label's text to clipboard and show a brief confirmation."""
        text = label.text()
        if text and text != "...":
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            palette = APP_CONFIG.get_current_palette()
            global_pos = QCursor.pos()
            CustomTooltip.instance().show_tooltip("کپی شد", global_pos, palette)
            QTimer.singleShot(600, CustomTooltip.instance().hide)

    def _apply_windows_styles(self):
        if sys.platform == "win32" and WIN32_AVAILABLE:
            try:
                hwnd = self.winId().__int__()
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style |= win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0, win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)
            except Exception as e:
                logger.error(f"Failed to apply Windows window styles: {e}")

    def _initialize_date_inputs(self): self._on_conversion_type_changed()
    def _on_conversion_type_changed(self):
        self._clear_results()
        is_jalali_to_greg = self.conversion_type_combo.currentText() == "شمسی به میلادی"
        today = jdatetime.date.today() if is_jalali_to_greg else datetime.date.today()
        if is_jalali_to_greg:
            self.year_input.setText(to_persian_digits(str(today.year)))
            months = [f"{to_persian_digits(str(i+1).zfill(2))} - {name}" for i, name in enumerate(APP_CONFIG.PERSIAN_MONTHS)]
            self.month_combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.day_combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.year_input.setText(str(today.year))
            months = [f"{i+1:02d} - {name}" for i, name in enumerate(APP_CONFIG.GREGORIAN_MONTHS)]
            self.month_combo.view().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.day_combo.view().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        
        self._set_combo_items(self.month_combo, months)
        self.month_combo.setCurrentIndex(today.month - 1)
        self._update_day_dropdown()
        day_str_to_set = to_persian_digits(today.day) if is_jalali_to_greg else str(today.day)
        if self.day_combo.findText(day_str_to_set) != -1:
            self.day_combo.setCurrentText(day_str_to_set)

    def _update_day_dropdown(self, *args):
        """
        Rebuilds the day dropdown based on selected year, month, and calendar type.
        Preserves the currently selected day when possible.
        """
        current_day_text = self.day_combo.currentText()
        is_jalali_input = self.conversion_type_combo.currentText() == "شمسی به میلادی"
        try:
            year_str = self.year_input.text()
            year = int(from_persian_digits(year_str)) if year_str else 1
            month_index = self.month_combo.currentIndex()
            if month_index < 0:
                days_in_month = 31
            else:
                month = self.month_combo.currentIndex() + 1
                days_in_month = self._get_days_in_month(is_jalali_input, year, month)
        except (ValueError, IndexError):
            days_in_month = 31 
        
        self.day_combo.blockSignals(True)
        days = [to_persian_digits(d) if is_jalali_input else str(d) for d in range(1, days_in_month + 1)]
        self._set_combo_items(self.day_combo, days)
        if self.day_combo.findText(current_day_text) != -1:
            self.day_combo.setCurrentText(current_day_text)
        elif self.day_combo.count() > 0:
            self.day_combo.setCurrentIndex(self.day_combo.count() - 1)
        self.day_combo.blockSignals(False)

    def _get_days_in_month(self, is_jalali: bool, year: int, month: int) -> int:
        if is_jalali:
            if 1 <= month <= 6:
                return 31
            if 7 <= month <= 11:
                return 30
            if month == 12:
                return 30 if is_jalali_leap_year(year) else 29
        else:
            return (datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)).day if month < 12 else 31
        return 0

    def _clear_results(self, *args):
        if self.status_message.isVisible():
            self.status_message.clear()
            self.status_message.hide()

        if self.output_widget.isVisible():
            self.output_widget.hide()
            self.middle_divider.hide()

        if self.height() != self._initial_height:
            self.setFixedSize(650, self._initial_height)

    def _show_error(self, message: str):
        self._clear_results()
        self.status_message.setText(message)
        self.status_message.show()
        new_height = self._initial_height + self.status_message.sizeHint().height() + 20
        self.setFixedSize(650, new_height)
            

    def _convert_date(self):
        """
        Validates input, performs calendar conversion, and updates the UI.
        All validation is done BEFORE creating date objects to prevent invalid states.
        """
        self._clear_results()
        is_jalali_input = self.conversion_type_combo.currentText() == "شمسی به میلادی"

        try:
            year_text = self.year_input.text().strip()
            if not year_text:
                self._show_error("لطفاً سال را وارد کنید.")
                return
            
            day_text = self.day_combo.currentText().strip()
            year = int(from_persian_digits(year_text))
            month = self.month_combo.currentIndex() + 1
            day = int(from_persian_digits(day_text))

            if is_jalali_input:
                if not (self.MIN_JALALI_YEAR <= year <= self.MAX_JALALI_YEAR):
                    min_y = to_persian_digits(str(self.MIN_JALALI_YEAR))
                    max_y = to_persian_digits(str(self.MAX_JALALI_YEAR))
                    self._show_error(f"سال شمسی باید بین {min_y} و {max_y} باشد.")
                    return
                j_date = jdatetime.date(year, month, day)
                g_date = j_date.togregorian()
            else:
                if not (self.MIN_GREGORIAN_YEAR <= year <= self.MAX_GREGORIAN_YEAR):
                    self._show_error(f"سال میلادی باید بین {self.MIN_GREGORIAN_YEAR} و {self.MAX_GREGORIAN_YEAR} باشد.")
                    return
                g_date = datetime.date(year, month, day)
                j_date = jdatetime.date.fromgregorian(date=g_date)

            self._display_results(j_date, g_date, is_jalali_input)

        except (ValueError, TypeError) as e:
            self._show_error("تاریخ ورودی نامعتبر است.")
            logger.warning(f"Date conversion failed: {e}")


        if is_jalali_input:
            if not (self.MIN_JALALI_YEAR <= year <= self.MAX_JALALI_YEAR):
                min_y = to_persian_digits(str(self.MIN_JALALI_YEAR))
                max_y = to_persian_digits(str(self.MAX_JALALI_YEAR))
                self._show_error(f"سال شمسی باید بین {min_y} و {max_y} باشد.")
                return
        else:
            if not (self.MIN_GREGORIAN_YEAR <= year <= self.MAX_GREGORIAN_YEAR):
                self._show_error(f"سال میلادی باید بین {self.MIN_GREGORIAN_YEAR} و {self.MAX_GREGORIAN_YEAR} باشد.")
                return

    def _display_results(self, j_date: jdatetime.date, g_date: datetime.date, is_jalali_input: bool):
        self.jalali_date_value_1.setText(to_persian_digits(j_date.strftime("%Y/%m/%d")))
        self.jalali_date_value_2.setText(f"{persian_weekday_name(j_date.weekday())} - {to_persian_digits(j_date.day)} {persian_month_name(j_date.month)} {to_persian_digits(j_date.year)}")
        self.gregorian_date_value_1.setText(g_date.strftime("%Y-%m-%d"))
        self.gregorian_date_value_2.setText(f"{g_date.strftime('%A')} - {gregorian_month_name(g_date.month)} {g_date.day}, {g_date.year}")

        self._update_elapsed_time(g_date)
        input_year = j_date.year if is_jalali_input else g_date.year
        is_leap = is_jalali_leap_year(input_year) if is_jalali_input else is_gregorian_leap_year(input_year)
        calendar_name = "شمسی" if is_jalali_input else "میلادی"
        self.leap_year_status.setText(f"سال {calendar_name} {to_persian_digits(input_year)} یک سال {'کبیسه است' if is_leap else 'کبیسه نیست'}")
        self.leap_year_status_opacity_effect.setOpacity(1.0 if is_leap else 0.5)
        self.middle_divider.show()
        self.output_widget.show()
        self.setFixedSize(650, 470)

    def _update_elapsed_time(self, target_date: datetime.date):
        """
        Calculates human-readable elapsed time between today and the target date.
        Uses dateutil.relativedelta when available, otherwise falls back to approximation.
        """
        today = datetime.date.today()
        if target_date == today:
             self.elapsed_text.setText("تاریخ امروز است.")
             return

        future = target_date > today
        if RELATIVEDELTA_AVAILABLE:
            delta = relativedelta(today, target_date)
            parts = [f"{to_persian_digits(abs(d))} {n}" for d, n in [(delta.years, "سال"), (delta.months, "ماه"), (delta.days, "روز")] if d]
        else:
            total_days = abs((today - target_date).days)
            years, rem = divmod(total_days, 365)
            months, days = divmod(rem, 30)
            parts = [f"{to_persian_digits(d)} {n}" for d, n in [(years, "سال"), (months, "ماه"), (days, "روز")] if d]
        
        status = "مانده" if future else "گذشته"
        self.elapsed_text.setText(f"فاصله زمانی: {' '.join(parts)} {status}")