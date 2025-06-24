import sys
import jdatetime
import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QSpacerItem, QSizePolicy, QFrame,
    QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QEvent, QRect
from PyQt5.QtGui import QFont, QColor, QPainter, QPainterPath, QPalette, QIntValidator, QIcon

from config import (
    Config, to_persian_digits, from_persian_digits,
    persian_weekday_name, is_gregorian_leap_year, is_jalali_leap_year, load_fonts, verify_assets
)

try:
    from dateutil.relativedelta import relativedelta
    RELATIVEDELTA_AVAILABLE = True
except ImportError:
    RELATIVEDELTA_AVAILABLE = False

try:
    import win32api
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# Define safe year ranges for UI input
MIN_JALALI_YEAR = 1
MAX_JALALI_YEAR = 1600
MIN_GREGORIAN_YEAR = 1
MAX_GREGORIAN_YEAR = 2500

class DateConverterWindow(QWidget):
    """
    Window for converting dates between Jalali (Persian) and Gregorian calendars.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("تبدیل تاریخ")
        self.setWindowIcon(QIcon(Config.ICON_PATH))
        self._initial_height = 260
        self._divider_height = 2
        self._divider_spacing = 10
        self.setFixedSize(650, self._initial_height)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setFocusPolicy(Qt.StrongFocus)
        self._drag_position: Optional[QRect] = None
        self._focus_timer = None

        self._setup_ui()
        self._apply_styles()
        self._update_month_dropdown()
        self.setStyleSheet(self._build_stylesheet())

        if sys.platform == "win32" and WIN32_AVAILABLE:
            hwnd = self.winId().__int__()
            current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            new_style = current_style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
            win32gui.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )

    def showEvent(self, event):
        super().showEvent(event)
        if self._focus_timer is None:
            self._focus_timer = self.startTimer(100)

    def timerEvent(self, event):
        if self._focus_timer is not None and self.year_input.isVisible() and self.year_input.isEnabled():
            self.year_input.setFocus()
            self.killTimer(self._focus_timer)
            self._focus_timer = None
            event.accept()
        super().timerEvent(event)

    # --- Window Drag and Paint Events ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if pos.y() < 40 and not self.minimize_button.geometry().contains(pos) \
               and not self.exit_button.geometry().contains(pos):
                self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.desktop().availableGeometry(self)
            min_x = screen_geometry.left()
            max_x = screen_geometry.right() - self.width()
            min_y = screen_geometry.top()
            max_y = screen_geometry.bottom() - 50
            clamped_x = max(min_x, min(new_pos.x(), max_x))
            clamped_y = max(min_y, min(new_pos.y(), max_y))
            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        QApplication.processEvents()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect = self.rect()
        path = QPainterPath()
        radius = 15
        path.addRoundedRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2, radius, radius)
        painter.fillPath(path, QColor(Config.BACKGROUND_COLOR))
        painter.setPen(QColor("#606060"))
        painter.drawPath(path)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease and (
            obj == self.conversion_type_combo.lineEdit() or
            obj == self.day_combo.lineEdit() or
            obj == self.month_combo.lineEdit()
        ):
            parent_combo = None
            if obj == self.conversion_type_combo.lineEdit():
                parent_combo = self.conversion_type_combo
            elif obj == self.day_combo.lineEdit():
                parent_combo = self.day_combo
            elif obj == self.month_combo.lineEdit():
                parent_combo = self.month_combo

            if parent_combo and not parent_combo.view().isVisible():
                parent_combo.showPopup()
            return True
        return super().eventFilter(obj, event)

    # --- UI Setup ---

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Minimize & Exit Buttons
        button_layout = QHBoxLayout()
        self.exit_button = QPushButton("✕")
        self.exit_button.setFixedSize(30, 30)
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)

        self.minimize_button = QPushButton("—")
        self.minimize_button.setFixedSize(30, 30)
        self.minimize_button.clicked.connect(self.showMinimized)
        button_layout.addWidget(self.minimize_button)
        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        main_layout.addSpacing(10)

        # Input Section
        input_grid = QGridLayout()
        input_grid.setContentsMargins(0, 0, 0, 0)
        input_grid.setHorizontalSpacing(15)
        input_grid.setVerticalSpacing(5)

        self.conversion_type_label = QLabel("نوع تبدیل")
        self.conversion_type_label.setAlignment(Qt.AlignCenter)
        input_grid.addWidget(self.conversion_type_label, 0, 0)
        self.day_label = QLabel("روز")
        self.day_label.setAlignment(Qt.AlignCenter)
        input_grid.addWidget(self.day_label, 0, 1)
        self.month_label = QLabel("ماه")
        self.month_label.setAlignment(Qt.AlignCenter)
        input_grid.addWidget(self.month_label, 0, 2)
        self.year_label = QLabel("سال")
        self.year_label.setAlignment(Qt.AlignCenter)
        input_grid.addWidget(self.year_label, 0, 3)

        self.conversion_type_combo = QComboBox()
        self.conversion_type_combo.addItems(["شمسی به میلادی", "میلادی به شمسی"])
        self.conversion_type_combo.currentIndexChanged.connect(self._update_month_dropdown)
        self.conversion_type_combo.currentIndexChanged.connect(self._clear_results)
        self.conversion_type_combo.setEditable(True)
        self.conversion_type_combo.lineEdit().setReadOnly(True)
        self.conversion_type_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.conversion_type_combo.lineEdit().installEventFilter(self)
        input_grid.addWidget(self.conversion_type_combo, 1, 0)

        self.day_combo = QComboBox()
        self.day_combo.currentIndexChanged.connect(self._clear_results)
        self.day_combo.setEditable(True)
        self.day_combo.lineEdit().setReadOnly(True)
        self.day_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.day_combo.lineEdit().installEventFilter(self)
        input_grid.addWidget(self.day_combo, 1, 1)

        self.month_combo = QComboBox()
        self.month_combo.currentIndexChanged.connect(self._update_day_dropdown)
        self.month_combo.currentIndexChanged.connect(self._clear_results)
        self.month_combo.setEditable(True)
        self.month_combo.lineEdit().setReadOnly(True)
        self.month_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.month_combo.lineEdit().installEventFilter(self)
        input_grid.addWidget(self.month_combo, 1, 2)

        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("1404 / 2025")
        self.year_input.returnPressed.connect(self._convert_date)
        self.year_input.textChanged.connect(self._clear_results)
        self.year_input.setAlignment(Qt.AlignCenter)
        self.year_input.setFocusPolicy(Qt.StrongFocus)
        # Validator range will be set dynamically in _set_initial_year_and_dropdown_direction
        self.year_validator = QIntValidator(1, 9999, self)
        self.year_input.setValidator(self.year_validator)
        input_grid.addWidget(self.year_input, 1, 3)

        input_h_wrapper_layout = QHBoxLayout()
        input_h_wrapper_layout.addStretch(1)
        input_h_wrapper_layout.addLayout(input_grid)
        input_h_wrapper_layout.addStretch(1)
        main_layout.addLayout(input_h_wrapper_layout)
        main_layout.addSpacing(10)

        # Convert Button
        self.convert_button = QPushButton("تبدیل")
        self.convert_button.clicked.connect(self._convert_date)
        self.convert_button.setFixedHeight(50)
        self.convert_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_layout.addWidget(self.convert_button)
        main_layout.addSpacing(10)

        # Middle separator line
        self.middle_divider = QFrame()
        self.middle_divider.setFrameShape(QFrame.HLine)
        self.middle_divider.setFrameShadow(QFrame.Sunken)
        self.middle_divider.setStyleSheet("color: #606060; border-width: 0.5px;")
        main_layout.addWidget(self.middle_divider)
        self.middle_divider.setVisible(False)
        main_layout.addSpacing(10)

        # Output Section
        self.dynamic_content_widget = QWidget()
        self.dynamic_content_layout = QVBoxLayout(self.dynamic_content_widget)
        self.dynamic_content_layout.setContentsMargins(0, 0, 0, 0)
        self.dynamic_content_layout.setSpacing(10)

        self.output_h_layout = QHBoxLayout()
        self.output_h_layout.setSpacing(10)
        self.output_h_layout.setAlignment(Qt.AlignCenter)

        # Gregorian Output
        gregorian_output_v_layout = QVBoxLayout()
        gregorian_output_v_layout.setAlignment(Qt.AlignCenter)
        gregorian_output_v_layout.setSpacing(0)
        self.gregorian_date_label_1 = QLabel("تاریخ میلادی")
        self.gregorian_date_label_1.setAlignment(Qt.AlignCenter)
        self.gregorian_date_value_1 = QLabel("...")
        self.gregorian_date_value_1.setAlignment(Qt.AlignCenter)
        self.gregorian_date_value_1.setWordWrap(True)
        self.gregorian_date_value_2 = QLabel("...")
        self.gregorian_date_value_2.setAlignment(Qt.AlignCenter)
        self.gregorian_date_value_2.setWordWrap(True)
        gregorian_output_v_layout.addWidget(self.gregorian_date_label_1)
        gregorian_output_v_layout.addWidget(self.gregorian_date_value_1)
        gregorian_output_v_layout.addWidget(self.gregorian_date_value_2)
        self.output_h_layout.addLayout(gregorian_output_v_layout)
        self.output_h_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Jalali Output
        jalali_output_v_layout = QVBoxLayout()
        jalali_output_v_layout.setAlignment(Qt.AlignCenter)
        jalali_output_v_layout.setSpacing(0)
        self.jalali_date_label_1 = QLabel("تاریخ شمسی")
        self.jalali_date_label_1.setAlignment(Qt.AlignCenter)
        self.jalali_date_value_1 = QLabel("...")
        self.jalali_date_value_1.setAlignment(Qt.AlignCenter)
        self.jalali_date_value_1.setWordWrap(True)
        self.jalali_date_value_2 = QLabel("...")
        self.jalali_date_value_2.setAlignment(Qt.AlignCenter)
        self.jalali_date_value_2.setWordWrap(True)
        jalali_output_v_layout.addWidget(self.jalali_date_label_1)
        jalali_output_v_layout.addWidget(self.jalali_date_value_1)
        jalali_output_v_layout.addWidget(self.jalali_date_value_2)
        self.output_h_layout.addLayout(jalali_output_v_layout)

        self.dynamic_content_layout.addLayout(self.output_h_layout)
        self.dynamic_content_layout.addSpacing(10)

        # Elapsed Time and Leap Year
        self.elapsed_text = QLabel("...")
        self.elapsed_text.setAlignment(Qt.AlignCenter)
        self.elapsed_text.setWordWrap(True)
        self.dynamic_content_layout.addWidget(self.elapsed_text)
        self.leap_year_status = QLabel("...")
        self.leap_year_status.setAlignment(Qt.AlignCenter)
        self.leap_year_status.setWordWrap(True)
        self.leap_year_status_opacity_effect = QGraphicsOpacityEffect(self)
        self.leap_year_status.setGraphicsEffect(self.leap_year_status_opacity_effect)
        self.dynamic_content_layout.addWidget(self.leap_year_status)

        # Error message label
        self.status_message = QLabel("")
        self.status_message.setAlignment(Qt.AlignCenter)
        self.status_message.setStyleSheet("color: red; font-weight: bold; font-size: 18px;")

        main_layout.addWidget(self.dynamic_content_widget)
        main_layout.addWidget(self.status_message)
        self.dynamic_content_widget.setVisible(False)
        self.status_message.setVisible(False)
        main_layout.addStretch(1)

    def _apply_styles(self):
        base_font = QFont(Config.FONT_FAMILY, 14)
        bold_font = QFont(Config.FONT_FAMILY, 14, QFont.Bold)
        palette = self.palette()
        palette.setColor(QPalette.WindowText, QColor(Config.TEXT_COLOR))
        palette.setColor(QPalette.Text, QColor(Config.TEXT_COLOR))
        self.setPalette(palette)

        # Centralize style snippets
        button_style_basic = (
            f"QPushButton {{ background-color: {Config.BACKGROUND_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Config.HOVER_BG}; }}"
            f"QPushButton:pressed {{ background-color: rgba(255, 255, 255, 0.05); }}"
        )
        self.minimize_button.setStyleSheet(button_style_basic)
        self.exit_button.setStyleSheet(
            f"QPushButton {{ background-color: #FF4C4C; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #FF6666; }}"
            f"QPushButton:pressed {{ background-color: #CC3D3D; }}"
        )

        input_field_height = 40

        for label in [self.conversion_type_label, self.year_label, self.month_label, self.day_label]:
            label.setFont(base_font)
            label.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 8px 5px;")
            label.setFixedHeight(input_field_height)

        for label in [self.jalali_date_label_1, self.gregorian_date_label_1]:
            label.setFont(bold_font)
            label.setStyleSheet(f"color: {Config.ACCENT_COLOR}; font-size: 16px; padding: 5px;")
            label.setMinimumHeight(30)

        self.jalali_date_value_1.setFont(QFont(Config.FONT_FAMILY, 15, QFont.Bold))
        self.jalali_date_value_1.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.jalali_date_value_1.setMinimumHeight(30)
        self.jalali_date_value_2.setFont(QFont(Config.FONT_FAMILY, 14))
        self.jalali_date_value_2.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.jalali_date_value_2.setMinimumHeight(30)

        self.gregorian_date_value_1.setFont(QFont(Config.GREGORIAN_FONT_FAMILY, 15, QFont.Bold))
        self.gregorian_date_value_1.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.gregorian_date_value_1.setMinimumHeight(30)
        self.gregorian_date_value_2.setFont(QFont(Config.GREGORIAN_FONT_FAMILY, 14))
        self.gregorian_date_value_2.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.gregorian_date_value_2.setMinimumHeight(30)

        self.elapsed_text.setFont(base_font)
        self.elapsed_text.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px; border-radius: 5px;")
        self.leap_year_status.setFont(QFont(Config.FONT_FAMILY, 12))
        self.leap_year_status.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px; border-radius: 5px;")

        scrollbar_style_snippet = (
            f"QAbstractItemView::verticalScrollBar {{"
            f"    border: none;"
            f"    background-color: {Config.SCROLLBAR_GROOVE_COLOR};"
            f"    width: 10px;"
            f"    margin: 0px;"
            f"    border-radius: 5px;"
            f"}}"
            f"QAbstractItemView::verticalScrollBar::handle {{"
            f"    background-color: {Config.SCROLLBAR_HANDLE_COLOR};"
            f"    border-radius: 5px;"
            f"    min-height: 20px;"
            f"}}"
            f"QAbstractItemView::add-line,"
            f"QAbstractItemView::sub-line {{"
            f"    height: 0px;"
            f"}}"
            f"QAbstractItemView::add-page,"
            f"QAbstractItemView::sub-page {{"
            f"    background: none;"
            f"}}"
        )
        combo_base_style = (
            f"QComboBox {{ "
            f"    background-color: {Config.INPUT_BG_COLOR}; "
            f"    color: {Config.TEXT_COLOR}; "
            f"    border: 1px solid #606060; "
            f"    border-radius: 8px; "
            f"    padding: 8px 5px; "
            f"    font-size: 14px; "
            f"    font-family: '{Config.FONT_FAMILY}'; "
            f"    text-align: center; "
            f"}}"
            f"QComboBox:focus {{ border: 1px solid {Config.ACCENT_COLOR}; }}"
            f"QComboBox::on {{ border: 1px solid {Config.ACCENT_COLOR}; }}"
            f"QComboBox::drop-down {{ border: 0px; width: 0px; height: 0px; }}"
        )
        combo_view_style = (
            f"QComboBox QAbstractItemView {{ "
            f"    background-color: {Config.INPUT_BG_COLOR}; "
            f"    color: {Config.TEXT_COLOR}; "
            f"    selection-background-color: {Config.ACCENT_COLOR}; "
            f"    border: 1px solid #606060; "
            f"    border-radius: 8px; "
            f"}}"
            + scrollbar_style_snippet
        )
        self.conversion_type_combo.setFixedSize(220, input_field_height)
        self.conversion_type_combo.setStyleSheet(combo_base_style + combo_view_style)
        self.day_combo.setFixedSize(80, input_field_height)
        self.day_combo.setStyleSheet(combo_base_style + combo_view_style)
        self.month_combo.setFixedSize(140, input_field_height)
        self.month_combo.setStyleSheet(combo_base_style + combo_view_style)

        self.year_input.setFixedSize(100, input_field_height)
        self.year_input.setStyleSheet(
            f"QLineEdit {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; padding: 8px; font-size: 14px; "
            f"font-family: '{Config.FONT_FAMILY}'; text-align: center; }}"
            f"QLineEdit:focus {{ border: 1px solid {Config.ACCENT_COLOR}; }}"
        )
        button_style = (
            f"QPushButton {{ background-color: {Config.ACCENT_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: none; border-radius: 8px; padding: 8px 15px; font-size: 16px; "
            f"font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: rgba(92, 184, 92, 0.8); }}"
            f"QPushButton:pressed {{ background-color: rgba(92, 184, 92, 0.6); }}"
        )
        self.convert_button.setStyleSheet(button_style)

    # --- UI Logic Helpers ---

    def _clear_results(self):
        self.jalali_date_value_1.setText("...")
        self.jalali_date_value_2.setText("...")
        self.gregorian_date_value_1.setText("...")
        self.gregorian_date_value_2.setText("...")
        self.elapsed_text.setText("...")
        self.leap_year_status.setText("...")
        self.status_message.setText("")
        self.dynamic_content_widget.setVisible(False)
        self.status_message.setVisible(False)
        self.middle_divider.setVisible(False)
        self.setFixedSize(650, self._initial_height)
        self.repaint()

    def _set_initial_year_and_dropdown_direction(self):
        conversion_type_text = self.conversion_type_combo.currentText()
        if conversion_type_text == "شمسی به میلادی":
            self.year_input.setText(str(jdatetime.date.today().year))
            self.year_validator.setRange(MIN_JALALI_YEAR, MAX_JALALI_YEAR)
            self.month_combo.view().setLayoutDirection(Qt.RightToLeft)
            self.day_combo.view().setLayoutDirection(Qt.RightToLeft)
        else:
            self.year_input.setText(str(datetime.date.today().year))
            self.year_validator.setRange(MIN_GREGORIAN_YEAR, MAX_GREGORIAN_YEAR)
            self.month_combo.view().setLayoutDirection(Qt.LeftToRight)
            self.day_combo.view().setLayoutDirection(Qt.LeftToRight)
        self.year_input.setValidator(self.year_validator)
        self.month_combo.update()
        self.day_combo.update()
        self.year_input.update()
        self.repaint()

    def _update_month_dropdown(self):
        self.month_combo.clear()
        conversion_type_text = self.conversion_type_combo.currentText()
        if conversion_type_text == "شمسی به میلادی":
            self.month_combo.addItems([
                f"{to_persian_digits(str(i+1))} - {name}" for i, name in enumerate(Config.PERSIAN_MONTHS)
            ])
        else:
            self.month_combo.addItems([
                f"{i+1:02d} - {name}" for i, name in enumerate(Config.GREGORIAN_MONTHS)
            ])
        if self.month_combo.count() > 0:
            self.month_combo.setCurrentIndex(0)
        self._set_initial_year_and_dropdown_direction()
        self._update_day_dropdown()
        self.month_combo.update()
        self.repaint()
        QApplication.processEvents()

    def _update_day_dropdown(self):
        current_day_text = self.day_combo.currentText()
        current_day_int = -1
        if current_day_text and current_day_text != '...':
            english_str = from_persian_digits(current_day_text)
            if english_str.isdigit():
                current_day_int = int(english_str)
        self.day_combo.clear()
        self.status_message.setText("")
        year_text = self.year_input.text().strip()
        year_text_english = from_persian_digits(year_text)
        year = int(year_text_english) if year_text_english.isdigit() else (
            jdatetime.date.today().year if self.conversion_type_combo.currentText() == "شمسی به میلادی"
            else datetime.date.today().year
        )
        month_index = self.month_combo.currentIndex()
        month = month_index + 1 if month_index != -1 else 1
        conversion_type_text = self.conversion_type_combo.currentText()
        days_in_month = 31
        try:
            if conversion_type_text == "شمسی به میلادی":
                if month == 12:
                    days_in_month = 30 if is_jalali_leap_year(year) else 29
                elif month <= 6:
                    days_in_month = 31
                else:
                    days_in_month = 30
            else:
                if month in [1, 3, 5, 7, 8, 10, 12]:
                    days_in_month = 31
                elif month in [4, 6, 9, 11]:
                    days_in_month = 30
                else:
                    days_in_month = 29 if not is_gregorian_leap_year(year) else 28
        except Exception:
            days_in_month = 31
        for day_num in range(1, days_in_month + 1):
            display = to_persian_digits(str(day_num)) if conversion_type_text == "شمسی به میلادی" else str(day_num)
            self.day_combo.addItem(display)
        if current_day_int != -1 and 1 <= current_day_int <= days_in_month:
            day_to_find = to_persian_digits(str(current_day_int)) if conversion_type_text == "شمسی به میلادی" else str(current_day_int)
            index = self.day_combo.findText(day_to_find)
            if index != -1:
                self.day_combo.setCurrentIndex(index)
            elif self.day_combo.count() > 0:
                self.day_combo.setCurrentIndex(0)
        elif self.day_combo.count() > 0:
            self.day_combo.setCurrentIndex(0)
        self.day_combo.update()
        self.year_input.update()
        self.repaint()
        QApplication.processEvents()

    def _convert_date(self):
        self._clear_results()
        self.middle_divider.setVisible(True)
        conversion_type_text = self.conversion_type_combo.currentText()
        year_text = self.year_input.text().strip()
        year_text_english = from_persian_digits(year_text)
        # --- Improved validation for year range ---
        if not year_text_english.isdigit() or len(year_text_english) not in [1, 2, 3, 4]:
            self._show_error("خطا: سال باید یک عدد 1 تا 4 رقمی باشد.")
            return
        year = int(year_text_english)
        if conversion_type_text == "شمسی به میلادی":
            if year < MIN_JALALI_YEAR or year > MAX_JALALI_YEAR:
                self._show_error(f"سال باید بین {to_persian_digits(str(MIN_JALALI_YEAR))} تا {to_persian_digits(str(MAX_JALALI_YEAR))} باشد.")
                return
        else:
            if year < MIN_GREGORIAN_YEAR or year > MAX_GREGORIAN_YEAR:
                self._show_error(f"سال باید بین {MIN_GREGORIAN_YEAR} تا {MAX_GREGORIAN_YEAR} باشد.")
                return
        month_index = self.month_combo.currentIndex()
        if month_index == -1:
            self._show_error("خطا: ماه را انتخاب کنید.")
            return
        month = month_index + 1
        day_index = self.day_combo.currentIndex()
        if day_index == -1:
            self._show_error("خطا: روز را انتخاب کنید.")
            return
        day_text_on_display = self.day_combo.currentText()
        day_text_english = from_persian_digits(day_text_on_display)
        day = int(day_text_english)
        target_jalali_date = None
        target_gregorian_date = None
        is_input_year_leap = False
        try:
            if conversion_type_text == "شمسی به میلادی":
                try:
                    target_jalali_date = jdatetime.date(year, month, day)
                except ValueError:
                    self._show_error("خطا: تاریخ شمسی وارد شده معتبر نیست.")
                    return
                target_gregorian_date = target_jalali_date.togregorian()
                is_input_year_leap = is_jalali_leap_year(year)
            else:
                try:
                    target_gregorian_date = datetime.date(year, month, day)
                except ValueError:
                    self._show_error("خطا: تاریخ میلادی وارد شده معتبر نیست.")
                    return
                target_jalali_date = jdatetime.date.fromgregorian(
                    year=target_gregorian_date.year,
                    month=target_gregorian_date.month,
                    day=target_gregorian_date.day
                )
                is_input_year_leap = is_gregorian_leap_year(year)
        except Exception:
            self._show_error("خطا در تبدیل تاریخ. لطفاً ورودی را بررسی کنید.")
            return
        self.status_message.setVisible(False)
        self.dynamic_content_widget.setVisible(True)
        self.setFixedSize(650, 550)

        # Display Jalali result
        if target_jalali_date:
            jalali_year_pd = to_persian_digits(str(target_jalali_date.year))
            jalali_month_pd = to_persian_digits(f"{target_jalali_date.month:02d}")
            jalali_day_pd = to_persian_digits(f"{target_jalali_date.day:02d}")
            jalali_weekday_name = persian_weekday_name(target_jalali_date.weekday())
            jalali_month_name = Config.PERSIAN_MONTHS[target_jalali_date.month - 1]
            self.jalali_date_value_1.setText(f"{jalali_year_pd}/{jalali_month_pd}/{jalali_day_pd}")
            self.jalali_date_value_2.setText(f"{jalali_weekday_name} - {jalali_day_pd} {jalali_month_name} {jalali_year_pd}")
        else:
            self.jalali_date_value_1.setText("N/A")
            self.jalali_date_value_2.setText("N/A")

        # Display Gregorian result
        if target_gregorian_date:
            gregorian_year_en = str(target_gregorian_date.year)
            gregorian_month_en = f"{target_gregorian_date.month:02d}"
            gregorian_day_en = f"{target_gregorian_date.day:02d}"
            gregorian_weekday_name = target_gregorian_date.strftime("%A")
            gregorian_month_name = target_gregorian_date.strftime("%B")
            self.gregorian_date_value_1.setText(f"{gregorian_year_en}-{gregorian_month_en}-{gregorian_day_en}")
            self.gregorian_date_value_2.setText(f"{gregorian_weekday_name} - {gregorian_month_name} {gregorian_day_en}, {gregorian_year_en}")
        else:
            self.gregorian_date_value_1.setText("N/A")
            self.gregorian_date_value_2.setText("N/A")

        # Elapsed Time and Leap Year
        elapsed_text_full = ""
        leap_year_status_full = ""
        if target_gregorian_date:
            today_gregorian = datetime.date.today()
            delta = today_gregorian - target_gregorian_date
            total_days = abs(delta.days)
            # Improved: use relativedelta if available
            if RELATIVEDELTA_AVAILABLE:
                rel = relativedelta(today_gregorian, target_gregorian_date)
                years = abs(rel.years)
                months = abs(rel.months)
                days = abs(rel.days)
            else:
                years = total_days // 365
                remaining_days_after_years = total_days % 365
                months = remaining_days_after_years // 30
                days = remaining_days_after_years % 30
            elapsed_text_prefix = "فاصله زمانی:"
            elapsed_time_str = f"{to_persian_digits(str(years))} سال {to_persian_digits(str(months))} ماه {to_persian_digits(str(days))} روز"
            elapsed_text_full = f"{elapsed_text_prefix} {elapsed_time_str} {'گذشته' if delta.days >= 0 else 'مانده'}"
            input_year_val = int(from_persian_digits(self.year_input.text()))
            calendar_type_str = "شمسی" if conversion_type_text == "شمسی به میلادی" else "میلادی"
            if conversion_type_text == "شمسی به میلادی":
                is_input_year_leap = is_jalali_leap_year(input_year_val)
            else:
                is_input_year_leap = is_gregorian_leap_year(input_year_val)
            leap_year_status_full = f"سال {calendar_type_str} {to_persian_digits(str(input_year_val))} یک سال {'کبیسه است' if is_input_year_leap else 'کبیسه نیست'}"
            if delta.days == 0:
                elapsed_text_full = "تاریخ انتخاب شده، امروز است."
                leap_year_status_full = ""
        self.elapsed_text.setText(elapsed_text_full)
        self.leap_year_status.setText(leap_year_status_full)
        self.leap_year_status_opacity_effect.setOpacity(1.0 if is_input_year_leap else 0.5)
        self.repaint()

    def _show_error(self, msg: str):
        self.status_message.setText(msg)
        self.status_message.setVisible(True)
        self.setFixedSize(650, self._initial_height + self._divider_height + self._divider_spacing + self.status_message.sizeHint().height() + 20)
        self.status_message.repaint()

    def _build_stylesheet(self):
        return (
            f"QToolTip {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.ACCENT_COLOR}; border: 1px solid #606060; "
            f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}\n"
            f"QScrollBar:vertical {{ background-color: {Config.SCROLLBAR_GROOVE_COLOR}; width: 10px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical {{ background-color: {Config.SCROLLBAR_HANDLE_COLOR}; border-radius: 5px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )

def main():
    import logging
    logging.basicConfig(level=logging.INFO)
    if not verify_assets():
        print("برخی از فایل‌های موردنیاز برنامه وجود ندارند. لطفاً نصب را بررسی کنید.")
        sys.exit(1)
    app = QApplication(sys.argv)
    load_fonts()
    app.setStyleSheet(
        f"QToolTip {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.ACCENT_COLOR}; border: 1px solid #606060; "
        f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}"
        f"QScrollBar:vertical {{"
        f"    border: none;"
        f"    background-color: {Config.SCROLLBAR_GROOVE_COLOR};"
        f"    width: 10px;"
        f"    margin: 0px;"
        f"    border-radius: 5px;"
        f"}}"
        f"QScrollBar::handle:vertical {{"
        f"    background-color: {Config.SCROLLBAR_HANDLE_COLOR};"
        f"    border-radius: 5px;"
        f"    min-height: 20px;"
        f"}}"
        f"QScrollBar::add-line:vertical,"
        f"QScrollBar::sub-line:vertical {{"
        f"    height: 0px;"
        f"}}"
        f"QScrollBar::add-page:vertical,"
        f"QScrollBar::sub-page:vertical {{"
        f"    background: none;"
        f"}}"
    )
    converter_window = DateConverterWindow()
    converter_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()