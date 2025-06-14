import sys
import jdatetime
import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QSpacerItem, QSizePolicy, QFrame,
    QGraphicsOpacityEffect # Import QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPainterPath, QPalette, QIntValidator

# ================== CONFIGURATION ==================

class Config:
    """Application-wide configuration and constants for the Date Converter."""
    FONT_FAMILY = "Vazirmatn" # Font for Persian/Jalali text
    GREGORIAN_FONT_FAMILY = "Inter" # New: Font for Gregorian text (changed from Roboto)
    TEXT_COLOR = "#e0e0e0" # Light grey for general text
    BACKGROUND_COLOR = "#2c2c2c" # Dark grey for window background
    INPUT_BG_COLOR = "#3a3a3a" # Slightly lighter dark grey for input fields
    ACCENT_COLOR = "#5cb85c" # Green for accent (button, primary results)
    HOVER_BG = "rgba(255, 255, 255, 0.08)" # Light hover effect
    SCROLLBAR_HANDLE_COLOR = "#505050" # Darker grey for scrollbar handle
    SCROLLBAR_GROOVE_COLOR = "#303030" # Even darker grey for scrollbar background

    PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
    PERSIAN_MONTH_NAMES = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    GREGORIAN_MONTH_NAMES = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    PERSIAN_WEEKDAY_NAMES = [
        "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"
    ]

# ================== UTILITY FUNCTIONS ==================

def to_persian_digits(s: str) -> str:
    """Convert English digits in a string to Persian digits."""
    return ''.join(Config.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert Persian digits in a string to English digits."""
    english_digits_map = {v: k for k, v in enumerate(Config.PERSIAN_DIGITS)}
    return ''.join(str(english_digits_map.get(ch, ch)) for ch in s)

def get_persian_weekday_name(weekday: int) -> str:
    """Return the Persian name for a given weekday index (0=Saturday, 6=Friday)."""
    return Config.PERSIAN_WEEKDAY_NAMES[weekday]

def is_gregorian_leap_year(year: int) -> bool:
    """Check if a Gregorian year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    """Check if a Jalali year is a leap year."""
    try:
        # If Esfand 30 exists, it's a leap year
        jdatetime.date(year, 12, 30)
        return True
    except ValueError:
        return False

# ================== DATE CONVERTER WINDOW ==================

class DateConverterWindow(QWidget):
    """A separate window for converting dates between Jalali and Gregorian calendars."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Date Converter - تبدیل تاریخ")
        
        # Initial fixed size for the window (input area + buttons + separator)
        self.initial_window_height = 260 # Base height for input section
        # Calculate approximate height of the divider line and its spacing (20px from layout)
        self.divider_height = 2 # Approximate height of the line itself
        self.divider_spacing_after = 10 # Corresponds to main_layout.addSpacing(10)
        
        self.setFixedSize(650, self.initial_window_height) 

        # Set window flags and background for a custom look
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Set the layout direction for the whole window
        self.setLayoutDirection(Qt.RightToLeft) 
        self.setFocusPolicy(Qt.StrongFocus)

        # Variables for dragging the window
        self._drag_position = None
        self.timer = None

        self._init_ui()
        self._apply_styles()
        self._update_month_dropdown() # This will now also set initial year and direction

    def showEvent(self, event):
        """Event handler for when the widget is shown."""
        super().showEvent(event)
        # Ensure year input gets focus when the window is shown
        if self.timer is None:
            self.timer = self.startTimer(100) # Give window time to draw before setting focus
            
    def timerEvent(self, event):
        """Event handler for QTimer."""
        if self.timer is not None and self.year_input.isVisible() and self.year_input.isEnabled():
            self.year_input.setFocus()
            self.killTimer(self.timer)
            self.timer = None
            event.accept()
        super().timerEvent(event)

    def mousePressEvent(self, event):
        """Allow dragging the window."""
        # Only allow dragging if not clicking on the minimize/exit buttons
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            # Check if clicked on the top bar region (e.g., top 40px)
            if pos.y() < 40: # Adjust this height if needed for your title bar area
                # Note: geometry() returns coordinates relative to the parent widget (self)
                if not self.minimize_button.geometry().contains(pos) and \
                   not self.exit_button.geometry().contains(pos):
                    self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                    event.accept()
                else:
                    event.ignore() # Ignore click if it's on a button
            else:
                event.ignore() # Ignore if not in draggable top region


    def mouseMoveEvent(self, event):
        """Update window position during drag."""
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            self.move(event.globalPos() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Reset drag position."""
        self._drag_position = None
        QApplication.processEvents() # Force event processing to ensure UI responsiveness
        event.accept()

    def paintEvent(self, event):
        """Custom paint event for rounded corners and background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        rect = self.rect()
        path = QPainterPath()
        radius = 15
        path.addRoundedRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2, radius, radius)

        # Fill background
        painter.fillPath(path, QColor(Config.BACKGROUND_COLOR))

        # Draw a subtle border
        painter.setPen(QColor("#606060"))
        painter.drawPath(path)

    def _init_ui(self):
        """Initializes the UI elements and layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10) # Reduced main layout spacing

        # --- Minimize and Exit Buttons ---
        button_layout = QHBoxLayout()


        # In RTL, adding widgets pushes them from right to left.
        # To get Exit on the far right and Minimize to its left, add Exit first, then Minimize.
        self.exit_button = QPushButton("✕") # Unicode multiplication sign for exit
        self.exit_button.setFixedSize(30, 30)
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)

        self.minimize_button = QPushButton("—") # Unicode minus sign for minimize
        self.minimize_button.setFixedSize(30, 30)
        self.minimize_button.clicked.connect(self.showMinimized) # Keep it simple for button
        button_layout.addWidget(self.minimize_button)
        button_layout.addStretch(1) 
        
        main_layout.addLayout(button_layout) # Add button layout to main layout
        main_layout.addSpacing(10) # Space below buttons

        # --- Input Section (using QGridLayout for precise control) ---
        input_grid = QGridLayout()
        input_grid.setContentsMargins(0, 0, 0, 0)
        input_grid.setHorizontalSpacing(15) # Adjusted horizontal spacing for compactness
        input_grid.setVerticalSpacing(5) # Reduced vertical spacing

        # Row 0: Labels for input fields (Right to Left: Conversion Type, Day, Month, Year)
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
        
        # Row 1: Input fields themselves
        self.conversion_type_combo = QComboBox()
        # Updated text for the first item: removed "و قمری"
        self.conversion_type_combo.addItems(["شمسی به میلادی", "میلادی به شمسی"])
        self.conversion_type_combo.currentIndexChanged.connect(self._update_month_dropdown)
        self.conversion_type_combo.currentIndexChanged.connect(self._clear_results)
        input_grid.addWidget(self.conversion_type_combo, 1, 0)

        self.day_combo = QComboBox()
        self.day_combo.currentIndexChanged.connect(self._clear_results)
        input_grid.addWidget(self.day_combo, 1, 1)

        self.month_combo = QComboBox()
        self.month_combo.currentIndexChanged.connect(self._update_day_dropdown)
        self.month_combo.currentIndexChanged.connect(self._clear_results)
        input_grid.addWidget(self.month_combo, 1, 2)

        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("مثال: 1402 / 2023")
        self.year_input.returnPressed.connect(self._convert_date)
        self.year_input.textChanged.connect(self._clear_results)
        self.year_input.setAlignment(Qt.AlignCenter) # Center text in QLineEdit
        self.year_input.setFocusPolicy(Qt.StrongFocus)
        
        # Update QIntValidator to allow 1 to 4 digit numbers (1 to 9999)
        self.year_validator = QIntValidator(1, 9999, self) 
        self.year_input.setValidator(self.year_validator)

        input_grid.addWidget(self.year_input, 1, 3)

        # Add a horizontal spacer to push the grid to the center, along with the button
        input_h_wrapper_layout = QHBoxLayout()
        input_h_wrapper_layout.addStretch(1) # Left stretch
        input_h_wrapper_layout.addLayout(input_grid)
        input_h_wrapper_layout.addStretch(1) # Right stretch
        
        main_layout.addLayout(input_h_wrapper_layout)
        main_layout.addSpacing(10) # Reduced spacer before convert button

        # Convert Button (Spans the width)
        self.convert_button = QPushButton("تبدیل")
        self.convert_button.clicked.connect(self._convert_date)
        self.convert_button.setFixedHeight(50) # Set fixed height
        self.convert_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) # Make it expand horizontally
        main_layout.addWidget(self.convert_button)
        
        main_layout.addSpacing(10)

        # --- Middle separator line (Visibility controlled) ---
        self.middle_divider = QFrame()
        self.middle_divider.setFrameShape(QFrame.HLine)
        self.middle_divider.setFrameShadow(QFrame.Sunken)
        self.middle_divider.setStyleSheet("color: #606060; border-width: 0.5px;")
        main_layout.addWidget(self.middle_divider)
        self.middle_divider.setVisible(False) # Initially hidden
        main_layout.addSpacing(10) # Reduced spacing after divider

        # --- Widget to hold the dynamic content (results or error) ---
        self.dynamic_content_widget = QWidget() # Use a QWidget to control visibility of its children
        self.dynamic_content_layout = QVBoxLayout(self.dynamic_content_widget)
        self.dynamic_content_layout.setContentsMargins(0, 0, 0, 0)
        self.dynamic_content_layout.setSpacing(10)


        # --- Output Section (These widgets will be added to dynamic_content_layout) ---
        self.output_h_layout = QHBoxLayout()
        self.output_h_layout.setSpacing(10) # Reduced horizontal spacing between output date columns
        self.output_h_layout.setAlignment(Qt.AlignCenter)

        # Gregorian Date Output (Left side in image, so added second in RTL layout)
        gregorian_output_v_layout = QVBoxLayout()
        gregorian_output_v_layout.setAlignment(Qt.AlignCenter)
        gregorian_output_v_layout.setSpacing(0) # Changed to 0 to align more tightly
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

        # شمسی Date Output (Right side in image, so added first in RTL layout)
        jalali_output_v_layout = QVBoxLayout()
        jalali_output_v_layout.setAlignment(Qt.AlignCenter)
        jalali_output_v_layout.setSpacing(0) # Changed to 0 to align more tightly
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
        self.dynamic_content_layout.addSpacing(10) # Reduced spacing after output section

        # --- Elapsed Time and Leap Year ---
        # Changed this to 'elapsed_text' and 'leap_year_status' labels for separate styling
        self.elapsed_text = QLabel("...")
        self.elapsed_text.setAlignment(Qt.AlignCenter)
        self.elapsed_text.setWordWrap(True)
        self.dynamic_content_layout.addWidget(self.elapsed_text)

        self.leap_year_status = QLabel("...")
        self.leap_year_status.setAlignment(Qt.AlignCenter)
        self.leap_year_status.setWordWrap(True)
        self.dynamic_content_layout.addWidget(self.leap_year_status)

        # Opacity effect for leap_year_status
        self.leap_year_status_opacity_effect = QGraphicsOpacityEffect(self)
        self.leap_year_status.setGraphicsEffect(self.leap_year_status_opacity_effect)


        # Status Message (Error message) - This will be placed in its own layout
        self.status_message = QLabel("")
        self.status_message.setAlignment(Qt.AlignCenter)
        self.status_message.setStyleSheet("color: red; font-weight: bold; font-size: 18px;") 

        # Add dynamic content widget and status message to main layout
        main_layout.addWidget(self.dynamic_content_widget) # This holds all results
        main_layout.addWidget(self.status_message) # This is just for errors

        # Initial states
        self.dynamic_content_widget.setVisible(False)
        self.status_message.setVisible(False)

        main_layout.addStretch(1) # Final stretch pushes everything up in the main layout

    def _apply_styles(self):
        """Applies consistent styling to all widgets."""
        base_font = QFont(Config.FONT_FAMILY, 14)
        bold_font = QFont(Config.FONT_FAMILY, 14, QFont.Bold)

        palette = self.palette()
        palette.setColor(QPalette.WindowText, QColor(Config.TEXT_COLOR))
        palette.setColor(QPalette.Text, QColor(Config.TEXT_COLOR))
        self.setPalette(palette)

        # Style for minimize and exit buttons
        button_style_basic = (
            f"QPushButton {{ background-color: {Config.BACKGROUND_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Config.HOVER_BG}; }}"
            f"QPushButton:pressed {{ background-color: rgba(255, 255, 255, 0.05); }}"
        )
        self.minimize_button.setStyleSheet(button_style_basic)
        
        # Red for exit button, with a similar hover effect
        self.exit_button.setStyleSheet(
            f"QPushButton {{ background-color: #FF4C4C; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #FF6666; }}" # Slightly lighter red on hover
            f"QPushButton:pressed {{ background-color: #CC3D3D; }}" # Darker red on press
        )


        # Fixed width and height for input QComboBoxes and QLineEdit
        input_field_height = 40 # Consistent height for combo boxes and line edit

        # Labels for inputs (Type, Day, Month, Year) - Adjusted height and padding for alignment
        for label in [self.conversion_type_label, self.year_label, self.month_label,
                       self.day_label]:
            label.setFont(base_font)
            # Match padding and height of input fields for better alignment
            label.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 8px 5px;") 
            label.setFixedHeight(input_field_height) 

        # Output section labels - "تاریخ میلادی" and "تاریخ شمسی"
        for label in [self.jalali_date_label_1, self.gregorian_date_label_1]:
            label.setFont(bold_font)
            label.setStyleSheet(f"color: {Config.ACCENT_COLOR}; font-size: 16px; padding: 5px;")
            label.setMinimumHeight(30) # Ensure enough height for the label text itself

        # For Jalali date values (Vazirmatn) - Adjusted top and bottom padding
        self.jalali_date_value_1.setFont(QFont(Config.FONT_FAMILY, 15, QFont.Bold))
        self.jalali_date_value_1.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;") # Adjusted padding-top/bottom to 2px
        self.jalali_date_value_1.setMinimumHeight(30) # Further reduced minimum height

        self.jalali_date_value_2.setFont(QFont(Config.FONT_FAMILY, 14))
        self.jalali_date_value_2.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;") # Adjusted padding-top/bottom to 2px
        self.jalali_date_value_2.setMinimumHeight(30) # Further reduced minimum height

        # For Gregorian date values (Inter) - Adjusted top and bottom padding
        self.gregorian_date_value_1.setFont(QFont(Config.GREGORIAN_FONT_FAMILY, 15, QFont.Bold))
        self.gregorian_date_value_1.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;") # Adjusted padding-top/bottom to 2px
        self.gregorian_date_value_1.setMinimumHeight(30) # Further reduced minimum height

        self.gregorian_date_value_2.setFont(QFont(Config.GREGORIAN_FONT_FAMILY, 14))
        self.gregorian_date_value_2.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px 5px; border-radius: 5px; vertical-align: middle;") # Adjusted padding-top/bottom to 2px
        self.gregorian_date_value_2.setMinimumHeight(30) # Further reduced minimum height


        self.elapsed_text.setFont(base_font)
        self.elapsed_text.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px; border-radius: 5px;") # Reduced padding
        
        # Initial style for leap_year_status with 16px font size
        self.leap_year_status.setFont(QFont(Config.FONT_FAMILY, 12)) # Changed font size to 16px
        self.leap_year_status.setStyleSheet(f"color: {Config.TEXT_COLOR}; padding: 2px; border-radius: 5px;")


        # Common scrollbar styling to be reused
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
            f"QAbstractItemView::verticalScrollBar::add-line,"
            f"QAbstractItemView::verticalScrollBar::sub-line {{"
            f"    height: 0px;" # Hide the arrows
            f"}}"
            f"QAbstractItemView::add-page,"
            f"QAbstractItemView::sub-page {{"
            f"    background: none;" # Hide the page buttons
            f"}}"
        )
        
        # Conversion Type ComboBox
        self.conversion_type_combo.setFixedSize(220, input_field_height) # Adjusted width for "شمسی به میلادی  "
        self.conversion_type_combo.setStyleSheet(
            f"QComboBox {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; padding: 8px 5px; font-size: 14px; "
            f"font-family: '{Config.FONT_FAMILY}'; text-align: center; }}"
            f"QComboBox::drop-down {{ border: 0px; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"selection-background-color: {Config.ACCENT_COLOR}; border: 1px solid #606060; border-radius: 8px; }}"
            + scrollbar_style_snippet # Append scrollbar style
        )
        
        # Day ComboBox
        self.day_combo.setFixedSize(80, input_field_height)
        self.day_combo.setStyleSheet(
            f"QComboBox {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; padding: 8px 5px; font-size: 14px; "
            f"font-family: '{Config.FONT_FAMILY}'; text-align: center; }}"
            f"QComboBox::drop-down {{ border: 0px; }}"
            f"QComboBox::down-arrow {{ image: url(no_arrow.png); }}"
            f"QComboBox QAbstractItemView {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"selection-background-color: {Config.ACCENT_COLOR}; border: 1px solid #606060; border-radius: 8px; }}"
            + scrollbar_style_snippet # Append scrollbar style
        )

        # Month ComboBox
        self.month_combo.setFixedSize(140, input_field_height) # Adjusted width for "اردیبهشت"
        self.month_combo.setStyleSheet(
            f"QComboBox {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; padding: 8px 5px; font-size: 14px; "
            f"font-family: '{Config.FONT_FAMILY}'; text-align: center; }}"
            f"QComboBox::drop-down {{ border: 0px; }}"
            f"QComboBox::down-arrow {{ image: url(no_arrow.png); }}"
            f"QComboBox QAbstractItemView {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"selection-background-color: {Config.ACCENT_COLOR}; border: 1px solid #606060; border-radius: 8px; }}"
            + scrollbar_style_snippet # Append scrollbar style
        )

        # Year LineEdit
        self.year_input.setFixedSize(100, input_field_height)
        self.year_input.setStyleSheet(
            f"QLineEdit {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: 1px solid #606060; border-radius: 8px; padding: 8px; font-size: 14px; "
            f"font-family: '{Config.FONT_FAMILY}'; text-align: center; }}"
            f"QLineEdit:focus {{ border: 1px solid {Config.ACCENT_COLOR}; }}"
        )

        # Button styling (already has fixed size set via setFixedSize in _init_ui)
        button_style = (
            f"QPushButton {{ background-color: {Config.ACCENT_COLOR}; color: {Config.TEXT_COLOR}; "
            f"border: none; border-radius: 8px; padding: 8px 15px; font-size: 16px; "
            f"font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: rgba(92, 184, 92, 0.8); }}"
            f"QPushButton:pressed {{ background-color: rgba(92, 184, 92, 0.6); }}"
        )
        self.convert_button.setStyleSheet(button_style)

    def _clear_results(self):
        """Clears all output labels and hides the results container."""
        # Clear output labels
        self.jalali_date_value_1.setText("...")
        self.jalali_date_value_2.setText("...")
        self.gregorian_date_value_1.setText("...")
        self.gregorian_date_value_2.setText("...")
        self.elapsed_text.setText("...") # Clear elapsed text
        self.leap_year_status.setText("...") # Clear leap year status
        self.status_message.setText("") # Clear status message
        
        # Hide the dynamic content widget (which contains all results)
        self.dynamic_content_widget.setVisible(False)
        
        # Hide the status message explicitly when clearing for valid input
        self.status_message.setVisible(False)

        # Hide the separator line
        self.middle_divider.setVisible(False)

        # Shrink window back to initial state (only input + button)
        self.setFixedSize(650, self.initial_window_height) 

        # Force updates for clear results to be visible immediately
        self.jalali_date_value_1.update()
        self.jalali_date_value_2.update()
        self.gregorian_date_value_1.update()
        self.gregorian_date_value_2.update()
        self.elapsed_text.update()
        self.leap_year_status.update()
        self.status_message.update()
        self.repaint()


    def _set_initial_year_and_dropdown_direction(self):
        """
        Sets the initial year in the year input box based on the conversion type
        and adjusts the layout direction of the month/day dropdowns.
        """
        conversion_type_text = self.conversion_type_combo.currentText()
        current_year_to_set = ""
        
        # Get the item views for month and day comboboxes
        month_view = self.month_combo.view()
        day_view = self.day_combo.view()

        # Determine the current year based on conversion type
        if conversion_type_text == "شمسی به میلادی": 
            # Set Jalali year in normal (English) digits as preview
            current_year_to_set = str(jdatetime.date.today().year)
            
            # Set dropdowns to RTL for Persian text
            month_view.setLayoutDirection(Qt.RightToLeft)
            day_view.setLayoutDirection(Qt.RightToLeft)
            
            # Update stylesheet for alignment in the combo box itself
            current_style = self.month_combo.styleSheet()
            new_style = current_style.replace("text-align: left;", "text-align: right;").replace("text-align: center;", "text-align: right;")
            self.month_combo.setStyleSheet(new_style)

            current_style = self.day_combo.styleSheet()
            new_style = current_style.replace("text-align: left;", "text-align: right;").replace("text-align: center;", "text-align: right;")
            self.day_combo.setStyleSheet(new_style)
            
        else: # "میلادی به شمسی"
            # Set Gregorian year in normal English digits as preview
            current_year_to_set = str(datetime.date.today().year)

            # Set dropdowns to LTR for Gregorian text
            month_view.setLayoutDirection(Qt.LeftToRight)
            day_view.setLayoutDirection(Qt.LeftToRight)
            
            # Update stylesheet for alignment in the combo box itself
            current_style = self.month_combo.styleSheet()
            new_style = current_style.replace("text-align: right;", "text-align: left;").replace("text-align: center;", "text-align: left;")
            self.month_combo.setStyleSheet(new_style)

            current_style = self.day_combo.styleSheet()
            new_style = current_style.replace("text-align: right;", "text-align: left;").replace("text-align: center;", "text-align: left;")
            self.day_combo.setStyleSheet(new_style)


        # Always set the year input with the determined current year
        self.year_input.setText(current_year_to_set)


        # Force update of comboboxes to reflect new direction
        self.month_combo.update()
        self.day_combo.update()
        self.year_input.update()
        self.repaint()


    def _update_month_dropdown(self):
        """Updates the month dropdown based on the selected conversion type."""
        self.month_combo.clear()
        conversion_type_text = self.conversion_type_combo.currentText()

        if conversion_type_text == "شمسی به میلادی": 
            self.month_combo.addItems(Config.PERSIAN_MONTH_NAMES)
        else: # "میلادی به شمسی"
            self.month_combo.addItems(Config.GREGORIAN_MONTH_NAMES)
        
        # Select the first item by default if there are items
        if self.month_combo.count() > 0:
            self.month_combo.setCurrentIndex(0)
        
        self._set_initial_year_and_dropdown_direction() # Call this BEFORE _update_day_dropdown
        self._update_day_dropdown() # Call the new function here after year and direction are set
        
        self.month_combo.update() # Explicitly update the month combo box
        self.repaint() # Ensure the window repaints after month dropdown updates
        QApplication.processEvents() # Force immediate event processing

    def _update_day_dropdown(self):
        """Updates the day dropdown based on the selected month and year,
        and performs basic validation, attempting to preserve the selected day."""
        
        # Store the currently selected day before clearing the dropdown
        current_day_text_on_display = self.day_combo.currentText()
        current_day_int = -1
        # Convert the current day text from potentially Persian digits to English int
        if current_day_text_on_display and current_day_text_on_display != '...':
            english_str = from_persian_digits(current_day_text_on_display)
            if english_str.isdigit():
                current_day_int = int(english_str)

        self.day_combo.clear()
        self.status_message.setText("")

        # Ensure year_text is processed correctly, converting Persian digits if present
        year_text = self.year_input.text().strip()
        year_text_english = from_persian_digits(year_text) # Convert any Persian digits in input to English
        year = None
        # Allow 1, 2, 3 or 4 digits for validation
        if year_text_english.isdigit() and len(year_text_english) in [1, 2, 3, 4]: 
            year = int(year_text_english)
        else:
            # If year is not valid (e.g., empty or partial), use current calendar's year for dropdown population
            if self.conversion_type_combo.currentText() == "شمسی به میلادی": 
                 year = jdatetime.date.today().year
            else:
                 year = datetime.date.today().year

        month_index = self.month_combo.currentIndex()
        month = None
        if month_index != -1:
            month = month_index + 1

        conversion_type_text = self.conversion_type_combo.currentText()
        days_in_month = 0

        # Attempt to determine days_in_month if year and month are valid
        if year is not None and month is not None:
            try:
                if conversion_type_text == "شمسی به میلادی": 
                    if month == 12: # Esfand
                        days_in_month = 30 if is_jalali_leap_year(year) else 29
                    elif month <= 6:
                        days_in_month = 31
                    else: # Months 7-11
                        days_in_month = 30
                else: # "میلادی به شمسی"
                    if month in [1, 3, 5, 7, 8, 10, 12]:
                        days_in_month = 31
                    elif month in [4, 6, 9, 11]:
                        days_in_month = 30
                    else: # February
                        days_in_month = 28
                        if is_gregorian_leap_year(year):
                            days_in_month = 29
            except Exception:
                days_in_month = 31 # Default to max days for safety
        else:
            days_in_month = 31 # Default days if year/month inputs are not yet valid

        # Populate day dropdown with digits based on conversion type
        for day_num in range(1, days_in_month + 1):
            if conversion_type_text == "شمسی به میلادی": 
                self.day_combo.addItem(to_persian_digits(str(day_num)))
            else:
                self.day_combo.addItem(str(day_num)) # Normal digits for Gregorian

        # Try to restore the previously selected day
        if current_day_int != -1 and 1 <= current_day_int <= days_in_month:
            # Convert to appropriate string format for finding text
            day_to_find = to_persian_digits(str(current_day_int)) if conversion_type_text == "شمسی به میلادی" else str(current_day_int) 
            index = self.day_combo.findText(day_to_find)
            if index != -1:
                self.day_combo.setCurrentIndex(index)
            else:
                # If the day is no longer valid (e.g., 31st in a 30-day month), default to 1st
                if self.day_combo.count() > 0:
                    self.day_combo.setCurrentIndex(0)
        else:
            # Fallback to 1st day if no previous selection or invalid integer conversion
            if self.day_combo.count() > 0:
                self.day_combo.setCurrentIndex(0)
        
        self.day_combo.update() # Explicitly update the day combo box
        self.year_input.update() # Also update year input if text changes affect dropdowns
        self.repaint() # Ensure the window repaints after day dropdown updates
        QApplication.processEvents() # Force immediate event processing


    def _convert_date(self):
        """Performs the date conversion and updates output labels."""
        # Always clear results and hide specific result widgets at the start
        self._clear_results() 

        # Make the separator visible upon conversion attempt
        self.middle_divider.setVisible(True)

        conversion_type_text = self.conversion_type_combo.currentText()
        
        # Convert year input from Persian digits to English if necessary before validation
        year_text = self.year_input.text().strip()
        year_text_english = from_persian_digits(year_text) # Convert any Persian digits

        # Validate year input to be 1, 2, 3 or 4 digits
        if not year_text_english.isdigit() or len(year_text_english) not in [1, 2, 3, 4]: 
            self.status_message.setText("خطا: سال باید یک عدد 1 تا 4 رقمی باشد.") 
            self.status_message.setVisible(True) # Make error message visible
            # Calculate height needed for input area + button + separator + error message
            self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20) 
            self.status_message.repaint()
            return
        year = int(year_text_english) # Use the English digit version for internal logic

        month_index = self.month_combo.currentIndex()
        if month_index == -1:
            self.status_message.setText("خطا: ماه را انتخاب کنید.")
            self.status_message.setVisible(True)
            self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20)
            self.status_message.repaint()
            return
        month = month_index + 1

        day_index = self.day_combo.currentIndex()
        if day_index == -1:
            self.status_message.setText("خطا: روز را انتخاب کنید.")
            self.status_message.setVisible(True)
            self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20)
            self.status_message.repaint()
            return
        
        # Convert day from Persian digits to English if necessary for internal logic
        day_text_on_display = self.day_combo.currentText()
        day_text_english = from_persian_digits(day_text_on_display)
        day = int(day_text_english)


        target_jalali_date = None
        target_gregorian_date = None
        is_input_year_leap = False # Initialize it here

        try:
            if conversion_type_text == "شمسی به میلادی": 
                try:
                    target_jalali_date = jdatetime.date(year, month, day)
                except ValueError:
                    self.status_message.setText("خطا: تاریخ شمسی وارد شده معتبر نیست.")
                    self.status_message.setVisible(True)
                    self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20)
                    self.status_message.repaint()
                    return
                
                target_gregorian_date = target_jalali_date.togregorian()
                is_input_year_leap = is_jalali_leap_year(year)

            else: # "میلادی به شمسی"
                try:
                    target_gregorian_date = datetime.date(year, month, day)
                except ValueError:
                    self.status_message.setText("خطا: تاریخ میلادی وارد شده معتبر نیست.")
                    self.status_message.setVisible(True)
                    self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20)
                    self.status_message.repaint()
                    return

                target_jalali_date = jdatetime.date.fromgregorian(
                    year=target_gregorian_date.year,
                    month=target_gregorian_date.month,
                    day=target_gregorian_date.day
                )
                is_input_year_leap = is_gregorian_leap_year(year)

        except Exception as e:
            self.status_message.setText(f"خطا در تبدیل تاریخ: {e}")
            self.status_message.setVisible(True)
            self.setFixedSize(650, self.initial_window_height + self.divider_height + self.divider_spacing_after + self.status_message.sizeHint().height() + 20)
            self.status_message.repaint()
            return

        # If conversion is successful, display results and hide error message
        self.status_message.setVisible(False) # Hide error message on success
        self.dynamic_content_widget.setVisible(True) # Show the widget containing results
        self.setFixedSize(650, 550) # Expand window to show all content (assuming 620 is enough for full results)

        # --- Display Results ---
        if target_jalali_date:
            jalali_year_pd = to_persian_digits(str(target_jalali_date.year))
            jalali_month_pd = to_persian_digits(f"{target_jalali_date.month:02d}")
            jalali_day_pd = to_persian_digits(f"{target_jalali_date.day:02d}")
            
            jalali_weekday_name = get_persian_weekday_name(target_jalali_date.weekday())
            jalali_month_name = Config.PERSIAN_MONTH_NAMES[target_jalali_date.month - 1]

            self.jalali_date_value_1.setText(f"{jalali_year_pd}/{jalali_month_pd}/{jalali_day_pd}")
            self.jalali_date_value_2.setText(f"{jalali_weekday_name} - {jalali_day_pd} {jalali_month_name} {jalali_year_pd}")
        else:
            self.jalali_date_value_1.setText("N/A")
            self.jalali_date_value_2.setText("N/A")


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


        # Elapsed Time and Leap Year status for the *input* year - ALWAYS IN PERSIAN
        elapsed_text_full = ""
        leap_year_status_full = ""
        
        if target_gregorian_date: # We need a valid gregorian date to calculate elapsed time
            today_gregorian = datetime.date.today()
            
            delta = today_gregorian - target_gregorian_date
            total_days = abs(delta.days)

            years = total_days // 365
            remaining_days_after_years = total_days % 365
            months = remaining_days_after_years // 30
            days = remaining_days_after_years % 30

            elapsed_text_prefix = "فاصله زمانی:"
            elapsed_time_str = f"{to_persian_digits(str(years))} سال {to_persian_digits(str(months))} ماه {to_persian_digits(str(days))} روز"
            
            elapsed_text_full = f"{elapsed_text_prefix} {elapsed_time_str} {'گذشته' if delta.days >= 0 else 'مانده'}"

            # Determine the input calendar's leap year status and present in Persian
            # Get original input year (English digits) from the input field after converting any Persian digits
            input_year_val = int(from_persian_digits(self.year_input.text())) 
            
            calendar_type_str = ""
            if conversion_type_text == "شمسی به میلادی": 
                is_input_year_leap = is_jalali_leap_year(input_year_val)
                calendar_type_str = "شمسی"
            else: # میلادی به شمسی
                is_input_year_leap = is_gregorian_leap_year(input_year_val)
                calendar_type_str = "میلادی"

            # Updated text for leap year status
            leap_year_status_full = f"سال {calendar_type_str} {to_persian_digits(str(input_year_val))} یک سال {'کبیسه است' if is_input_year_leap else 'کبیسه نیست'}"
            
            if delta.days == 0:
                elapsed_text_full = "تاریخ انتخاب شده، امروز است."
                leap_year_status_full = "" # No leap year status if it's today's date

        self.elapsed_text.setText(elapsed_text_full)
        self.leap_year_status.setText(leap_year_status_full)

        # Adjust leap_year_status opacity using QGraphicsOpacityEffect
        # The font size is now set once in _apply_styles
        if is_input_year_leap:
            self.leap_year_status_opacity_effect.setOpacity(1.0) # Full opacity for leap years
        else:
            self.leap_year_status_opacity_effect.setOpacity(0.5) # Reduced opacity for non-leap years (changed to 0.5 for clearer demonstration)

        # Force updates to ensure all changes are rendered
        self.jalali_date_value_1.update()
        self.jalali_date_value_2.update()
        self.gregorian_date_value_1.update()
        self.gregorian_date_value_2.update()
        self.elapsed_text.update()
        self.leap_year_status.update()
        self.status_message.update()
        self.repaint()


# ================== MAIN ==================

def main():
    """Main entry point for the standalone Date Converter application."""
    app = QApplication(sys.argv)
    
    # Apply a global stylesheet for QToolTip and general scrollbars
    app.setStyleSheet(
        f"QToolTip {{ background-color: {Config.INPUT_BG_COLOR}; color: {Config.ACCENT_COLOR}; border: 1px solid #606060; "
        f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}"
        # Global Scrollbar styling (this will apply to any QAbstractScrollArea in the app)
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
        f"    height: 0px;" # Hide the arrows
        f"}}"
        f"QScrollBar::add-page:vertical,"
        f"QScrollBar::sub-page:vertical {{"
        f"    background: none;" # Hide the page buttons
        f"}}"
    )

    converter_window = DateConverterWindow()
    converter_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
