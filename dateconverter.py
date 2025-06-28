import sys
import jdatetime
import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QSpacerItem, QSizePolicy, QFrame,
    QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QEvent, QRect, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPainterPath, QPalette, QIntValidator, QIcon

from config import (
    APP_CONFIG, to_persian_digits, from_persian_digits,
    persian_weekday_name, is_gregorian_leap_year, is_jalali_leap_year,
    gregorian_month_name, setup_logging
)

# Setup logging for this module
logger = setup_logging(__name__)

try:
    from dateutil.relativedelta import relativedelta
    RELATIVEDELTA_AVAILABLE = True
except ImportError:
    logger.warning("dateutil.relativedelta not available. Elapsed time calculation will be less precise.")
    RELATIVEDELTA_AVAILABLE = False

try:
    import win32api
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    logger.warning("win32api not available. Window style modifications for minimize/system menu will be skipped.")
    WIN32_AVAILABLE = False

MIN_JALALI_YEAR = 1
MAX_JALALI_YEAR = 1600
MIN_GREGORIAN_YEAR = 622
MAX_GREGORIAN_YEAR = 2500

class DateConverterWindow(QWidget):
    """
    Window for converting dates between Jalali (Persian) and Gregorian calendars.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("تبدیل تاریخ")
        self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
        self._initial_height = 260
        self._divider_height = 2
        self._divider_spacing = 10
        self.setFixedSize(650, self._initial_height)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setFocusPolicy(Qt.StrongFocus)
        self._drag_position: Optional[QRect] = None

        self._setup_ui()
        self._set_theme_colors()

        self._initialize_date_inputs()

        if sys.platform == "win32" and WIN32_AVAILABLE:
            try:
                hwnd = self.winId().__int__()
                current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                new_style = current_style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
                win32gui.SetWindowPos(
                    hwnd, None, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
                )
            except Exception as e:
                logger.error(f"Failed to apply Windows window styles: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, lambda: self.year_input.setFocus())

    def _set_theme_colors(self):
        """Applies colors based on the current theme."""
        palette = self.palette()
        palette.setColor(QPalette.WindowText, QColor(APP_CONFIG.current_palette['TEXT_COLOR']))
        palette.setColor(QPalette.Text, QColor(APP_CONFIG.current_palette['TEXT_COLOR']))
        self.setPalette(palette)
        self._apply_styles()
        self.repaint()

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
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect = self.rect()
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
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
        self.exit_button.clicked.connect(self.close) # Changed to self.close()
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
        self.conversion_type_combo.currentIndexChanged.connect(self._on_conversion_type_changed)
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
        self.middle_divider.setStyleSheet(f"color: {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; border-width: 0.5px;")
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
        base_font = QFont(APP_CONFIG.FONT_FAMILY, 14)
        bold_font = QFont(APP_CONFIG.FONT_FAMILY, 14, QFont.Bold)
        input_field_height = 40

        self.minimize_button.setStyleSheet(
            f"QPushButton {{ background-color: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: 1px solid {APP_CONFIG.current_palette['MENU_BORDER_COLOR']}; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG']}; }}"
            f"QPushButton:pressed {{ background-color: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.05').replace('0.05', '0.03')}; }}"
        )
        self.exit_button.setStyleSheet(
            f"QPushButton {{ background-color: #FF4C4C; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: 1px solid {APP_CONFIG.current_palette['MENU_BORDER_COLOR']}; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #FF6666; }}"
            f"QPushButton:pressed {{ background-color: #CC3D3D; }}"
        )

        for label in [self.conversion_type_label, self.year_label, self.month_label, self.day_label]:
            label.setFont(base_font)
            label.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 8px 5px;")
            label.setFixedHeight(input_field_height)

        for label in [self.jalali_date_label_1, self.gregorian_date_label_1]:
            label.setFont(bold_font)
            label.setStyleSheet(f"color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; font-size: 16px; padding: 5px;")
            label.setMinimumHeight(30)

        self.jalali_date_value_1.setFont(QFont(APP_CONFIG.FONT_FAMILY, 15, QFont.Bold))
        self.jalali_date_value_1.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.jalali_date_value_1.setMinimumHeight(30)
        self.jalali_date_value_2.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
        self.jalali_date_value_2.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.jalali_date_value_2.setMinimumHeight(30)

        self.gregorian_date_value_1.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 15, QFont.Bold))
        self.gregorian_date_value_1.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.gregorian_date_value_1.setMinimumHeight(30)
        self.gregorian_date_value_2.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 14))
        self.gregorian_date_value_2.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;")
        self.gregorian_date_value_2.setMinimumHeight(30)

        self.elapsed_text.setFont(base_font)
        self.elapsed_text.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px; border-radius: 5px;")
        self.leap_year_status.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.leap_year_status.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; padding: 2px; border-radius: 5px;")

        # This snippet applies to QAbstractItemView scrollbars (e.g., in QComboBox dropdowns)
        scrollbar_style_snippet = (
            f"QAbstractItemView::verticalScrollBar {{"
            f"    border: none;"
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_GROOVE_COLOR']};"
            f"    width: 10px;"
            f"    margin: 0px;"
            f"    border-radius: 5px;"
            f"}}"
            f"QAbstractItemView::verticalScrollBar::handle {{"
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_HANDLE_COLOR']};"
            f"    border-radius: 5px;"
            f"    min-height: 20px;"
            f"}}"
            f"QAbstractItemView::add-line:vertical,"
            f"QAbstractItemView::sub-line:vertical {{"
            f"    height: 0px;"
            f"}}"
            f"QAbstractItemView::add-page:vertical,"
            f"QAbstractItemView::sub-page:vertical {{"
            f"    background: none;"
            f"}}"
        )
        combo_base_style = (
            f"QComboBox {{ "
            f"    background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; "
            f"    color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"    border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"    border-radius: 8px; "
            f"    padding: 8px 5px; "
            f"    font-size: 14px; "
            f"    font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"    text-align: center; "
            f"}}"
            f"QComboBox:focus {{ border: 1px solid {APP_CONFIG.current_palette['ACCENT_COLOR']}; }}"
            f"QComboBox::on {{ border: 1px solid {APP_CONFIG.current_palette['ACCENT_COLOR']}; }}"
            f"QComboBox::drop-down {{ border: 0px; width: 0px; height: 0px; }}"
        )
        combo_view_style = (
            f"QComboBox QAbstractItemView {{ "
            f"    background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; "
            f"    color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"    selection-background-color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; "
            f"    border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
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
            f"QLineEdit {{ background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 8px; font-size: 14px; "
            f"font-family: '{APP_CONFIG.FONT_FAMILY}'; text-align: center; }}"
            f"QLineEdit:focus {{ border: 1px solid {APP_CONFIG.current_palette['ACCENT_COLOR']}; }}"
        )
        self.convert_button.setStyleSheet(
            f"QPushButton {{ background-color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: none; border-radius: 8px; padding: 8px 15px; font-size: 16px; "
            f"font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(120).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(150).name()}; }}"
        )

    # --- UI Logic Helpers ---

    def _initialize_date_inputs(self):
        """Sets the initial date values based on the current conversion type."""
        self._on_conversion_type_changed(self.conversion_type_combo.currentIndex())

    def _on_conversion_type_changed(self, index: int):
        """
        Handles changes in the conversion type dropdown.
        Updates month/day dropdowns and year input based on the selected type.
        """
        self._clear_results()
        conversion_type_text = self.conversion_type_combo.itemText(index)
        
        if conversion_type_text == "شمسی به میلادی":
            today = jdatetime.date.today()
            self.year_input.setText(to_persian_digits(str(today.year)))
            self.year_validator.setRange(MIN_JALALI_YEAR, MAX_JALALI_YEAR)
            self.month_combo.view().setLayoutDirection(Qt.RightToLeft)
            self.day_combo.view().setLayoutDirection(Qt.RightToLeft)
            
            self.month_combo.clear()
            self.month_combo.addItems([
                f"{to_persian_digits(str(i+1))} - {name}" for i, name in enumerate(APP_CONFIG.PERSIAN_MONTHS)
            ])
            self.month_combo.setCurrentIndex(today.month - 1)
            self._update_day_dropdown(to_persian_digits(str(today.day)))

        else: # میلادی به شمسی
            today = datetime.date.today()
            self.year_input.setText(str(today.year))
            self.year_validator.setRange(MIN_GREGORIAN_YEAR, MAX_GREGORIAN_YEAR)
            self.month_combo.view().setLayoutDirection(Qt.LeftToRight)
            self.day_combo.view().setLayoutDirection(Qt.LeftToRight)

            self.month_combo.clear()
            self.month_combo.addItems([
                f"{i+1:02d} - {name}" for i, name in enumerate(APP_CONFIG.GREGORIAN_MONTHS)
            ])
            self.month_combo.setCurrentIndex(today.month - 1)
            self._update_day_dropdown(str(today.day))

        self.year_input.setValidator(self.year_validator)
        self.month_combo.update()
        self.day_combo.update()
        self.year_input.update()
        self.repaint()

    def _clear_results(self):
        """Clears all output fields and resets window size."""
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

    def _get_days_in_month(self, conversion_type: str, year: int, month: int) -> int:
        """Helper to get the number of days in a given month for either calendar type."""
        if conversion_type == "شمسی به میلادی":
            if month == 12:
                return 30 if is_jalali_leap_year(year) else 29
            elif month <= 6:
                return 31
            else:
                return 30
        else: # Gregorian
            if month in [1, 3, 5, 7, 8, 10, 12]:
                return 31
            elif month in [4, 6, 9, 11]:
                return 30
            elif month == 2:
                return 29 if is_gregorian_leap_year(year) else 28
        return 31

    def _update_day_dropdown(self, prev_day_text: str = ""):
        """
        Updates the day dropdown based on the selected month and year.
        Tries to preserve the previously selected day.
        """
        self.day_combo.clear()
        self.status_message.setText("")

        conversion_type_text = self.conversion_type_combo.currentText()
        year_text = self.year_input.text().strip()
        year_val_english = from_persian_digits(year_text)

        current_year = None
        if year_val_english.isdigit():
            current_year = int(year_val_english)
        else:
            if conversion_type_text == "شمسی به میلادی":
                current_year = jdatetime.date.today().year
            else:
                current_year = datetime.date.today().year
            self.year_input.setText(to_persian_digits(str(current_year)) if conversion_type_text == "شمسی به میلادی" else str(current_year))

        month_index = self.month_combo.currentIndex()
        current_month = month_index + 1 if month_index != -1 else 1

        days_in_current_month = self._get_days_in_month(conversion_type_text, current_year, current_month)
        
        for day_num in range(1, days_in_current_month + 1):
            display_day = to_persian_digits(str(day_num)) if conversion_type_text == "شمسی به میلادی" else str(day_num)
            self.day_combo.addItem(display_day)
        
        day_to_select = None
        if prev_day_text:
            try:
                prev_day_int = int(from_persian_digits(prev_day_text))
                if 1 <= prev_day_int <= days_in_current_month:
                    day_to_select = prev_day_int
            except ValueError:
                pass
        
        if day_to_select is None:
            if conversion_type_text == "شمسی به میلادی":
                today_day = jdatetime.date.today().day
            else:
                today_day = datetime.date.today().day
            
            if 1 <= today_day <= days_in_current_month:
                day_to_select = today_day
            else:
                day_to_select = 1

        if day_to_select is not None:
            display_selected_day = to_persian_digits(str(day_to_select)) if conversion_type_text == "شمسی به میلادی" else str(day_to_select)
            index = self.day_combo.findText(display_selected_day)
            if index != -1:
                self.day_combo.setCurrentIndex(index)
                self.day_combo.lineEdit().setText(self.day_combo.currentText())
                self.day_combo.lineEdit().home(False)

        self.day_combo.update()
        self.year_input.update()
        self.repaint()

    def _convert_date(self):
        self._clear_results()
        self.middle_divider.setVisible(True)

        conversion_type_text = self.conversion_type_combo.currentText()
        year_text = self.year_input.text().strip()
        year_val_english = from_persian_digits(year_text)

        if not year_val_english.isdigit() or not (1 <= len(year_val_english) <= 4):
            self._show_error("خطا: سال باید یک عدد 1 تا 4 رقمی باشد.")
            return

        year = int(year_val_english)

        if conversion_type_text == "شمسی به میلادی":
            if not (MIN_JALALI_YEAR <= year <= MAX_JALALI_YEAR):
                self._show_error(f"سال باید بین {to_persian_digits(str(MIN_JALALI_YEAR))} تا {to_persian_digits(str(MAX_JALALI_YEAR))} باشد.")
                return
        else:
            if not (MIN_GREGORIAN_YEAR <= year <= MAX_GREGORIAN_YEAR):
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
        day = int(from_persian_digits(day_text_on_display))

        target_jalali_date = None
        target_gregorian_date = None
        is_input_year_leap = False

        try:
            if conversion_type_text == "شمسی به میلادی":
                target_jalali_date = jdatetime.date(year, month, day)
                target_gregorian_date = target_jalali_date.togregorian()
                is_input_year_leap = is_jalali_leap_year(year)
            else:
                target_gregorian_date = datetime.date(year, month, day)
                target_jalali_date = jdatetime.date.fromgregorian(
                    year=target_gregorian_date.year,
                    month=target_gregorian_date.month,
                    day=target_gregorian_date.day
                )
                is_input_year_leap = is_gregorian_leap_year(year)
        except ValueError as e:
            self._show_error(f"خطا: تاریخ وارد شده معتبر نیست. ({e})")
            return
        except Exception as e:
            logger.exception("Unexpected error during date conversion.")
            self._show_error(f"خطا در تبدیل تاریخ: {e}. لطفاً ورودی را بررسی کنید.")
            return

        self.status_message.setVisible(False)
        self.dynamic_content_widget.setVisible(True)
        self.setFixedSize(650, 550)

        if target_jalali_date:
            jalali_year_pd = to_persian_digits(str(target_jalali_date.year))
            jalali_month_pd = to_persian_digits(f"{target_jalali_date.month:02d}")
            jalali_day_pd = to_persian_digits(f"{target_jalali_date.day:02d}")
            jalali_weekday_name_str = persian_weekday_name(target_jalali_date.weekday())
            jalali_month_name_str = APP_CONFIG.PERSIAN_MONTHS[target_jalali_date.month - 1]
            self.jalali_date_value_1.setText(f"{jalali_year_pd}/{jalali_month_pd}/{jalali_day_pd}")
            self.jalali_date_value_2.setText(f"{jalali_weekday_name_str} - {jalali_day_pd} {jalali_month_name_str} {jalali_year_pd}")
        else:
            self.jalali_date_value_1.setText("N/A")
            self.jalali_date_value_2.setText("N/A")

        if target_gregorian_date:
            gregorian_year_en = str(target_gregorian_date.year)
            gregorian_month_en = f"{target_gregorian_date.month:02d}"
            gregorian_day_en = f"{target_gregorian_date.day:02d}"
            gregorian_weekday_name_str = target_gregorian_date.strftime("%A")
            gregorian_month_name_str = target_gregorian_date.strftime("%B")
            self.gregorian_date_value_1.setText(f"{gregorian_year_en}-{gregorian_month_en}-{gregorian_day_en}")
            self.gregorian_date_value_2.setText(f"{gregorian_weekday_name_str} - {gregorian_month_name_str} {gregorian_day_en}, {gregorian_year_en}")
        else:
            self.gregorian_date_value_1.setText("N/A")
            self.gregorian_date_value_2.setText("N/A")

        self._update_elapsed_time_and_leap_year(target_gregorian_date, conversion_type_text, year, is_input_year_leap)
        self.repaint()

    def _update_elapsed_time_and_leap_year(self, target_gregorian_date: Optional[datetime.date], conversion_type: str, year: int, is_input_year_leap: bool):
        """Calculates and displays elapsed time and leap year status."""
        elapsed_text_full = "..."
        leap_year_status_full = "..."

        if target_gregorian_date:
            today_gregorian = datetime.date.today()
            delta = today_gregorian - target_gregorian_date
            total_days = abs(delta.days)

            years, months, days = 0, 0, 0
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
            
            if delta.days > 0:
                elapsed_text_full = f"{elapsed_text_prefix} {elapsed_time_str} گذشته"
            elif delta.days < 0:
                elapsed_text_full = f"{elapsed_text_prefix} {elapsed_time_str} مانده"
            else:
                elapsed_text_full = "تاریخ امروز است."

            calendar_type_str = "شمسی" if conversion_type == "شمسی به میلadi" else "میلادی"
            leap_year_status_full = f"سال {calendar_type_str} {to_persian_digits(str(year))} یک سال {'کبیسه است' if is_input_year_leap else 'کبیسه نیست'}"
        
        self.elapsed_text.setText(elapsed_text_full)
        self.leap_year_status.setText(leap_year_status_full)
        self.leap_year_status_opacity_effect.setOpacity(1.0 if is_input_year_leap else 0.5)


    def _show_error(self, msg: str):
        """Displays an error message and adjusts window size."""
        self.status_message.setText(msg)
        self.status_message.setVisible(True)
        new_height = self._initial_height + self._divider_height + self._divider_spacing + self.status_message.sizeHint().height() + 20
        self.setFixedSize(650, new_height)
        self.status_message.repaint()

    def _build_stylesheet(self):
        # This method is here only for historical context from the original code.
        # The QToolTip and QScrollBar styles for the main app are now managed globally in main.py.
        # This function is no longer called within the DateConverterWindow class itself.
        return (
            f"QToolTip {{ background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}\n"
            f"QScrollBar:vertical {{ background-color: {APP_CONFIG.current_palette['SCROLLBAR_GROOVE_COLOR']}; width: 10px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical {{ background-color: {APP_CONFIG.current_palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: 5px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )

def main():
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        from config import load_fonts, verify_assets
        if not verify_assets():
            print("برخی از فایل‌های موردنیاز برنامه وجود ندارند. لطفاً نصب را بررسی کنید.")
            sys.exit(1)
        load_fonts()
    except Exception as e:
        logger.critical(f"Asset verification or font loading failed: {e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    
    # Default to Dark theme for standalone testing, as system theme is removed.
    APP_CONFIG.set_theme(APP_CONFIG.Theme.DARK)

    # The global stylesheet for QToolTip and QScrollBar is now set in main.py.
    # This block is for standalone testing of DateConverterWindow and should be consistent.
    app.setStyleSheet(
        f"QToolTip {{ background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
        f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
        f"QScrollBar:vertical {{"
        f"    border: none;"
        f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_GROOVE_COLOR']};"
        f"    width: 10px;"
        f"    margin: 0px;"
        f"    border-radius: 5px;"
        f"}}"
        f"QScrollBar::handle:vertical {{"
        f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_HANDLE_COLOR']};"
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