import ctypes.wintypes
import datetime
import json
import os
import sys
import winreg
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt5.QtCore import (QAbstractNativeEventFilter, QCoreApplication,
                          QPoint, QRectF, QSettings, Qt, QTimer, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QIcon, QMouseEvent, QMovie, QPainter,
                         QPainterPath, QPixmap, QTextOption)
from PyQt5.QtWidgets import (QApplication, QBoxLayout, QGridLayout,
                             QHBoxLayout, QLabel, QMenu, QMessageBox,
                             QPushButton, QSystemTrayIcon,
                             QVBoxLayout, QWidget, QWidgetAction, 
                             QTextEdit, QGraphicsDropShadowEffect)

from config import (APP_CONFIG, is_jalali_leap_year,
                    load_fonts, persian_month_name, persian_weekday_name,
                    setup_logging, to_persian_digits, verify_assets)
try:
    from dateconverter import DateConverterWindow
except ImportError:
    logger = setup_logging(__name__)
    logger.warning("dateconverter.py not found. Date conversion feature will be disabled.")
    class DateConverterWindow(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setWindowTitle("Date Converter (Unavailable)")
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel("Date converter feature is not available."))
        def show(self):
            QMessageBox.warning(None, "Feature Unavailable", "The date conversion feature is not available. Please ensure 'dateconverter.py' is in the correct directory.")
            super().show()
        def update_styles(self):
            pass


logger = setup_logging(__name__)

# ==================== BASE CLASSES & UTILITIES ====================

class BaseFramelessWindow(QWidget):
    """A base class for frameless windows with custom drag and paint logic."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_position: Optional[QPoint] = None
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        painter.setClipPath(path)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 40:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.screenAt(event.globalPos()).availableGeometry()
            
            min_x, max_x = screen_geometry.left(), screen_geometry.right() - self.width()
            clamped_x = max(min_x, min(new_pos.x(), max_x))

            min_y, max_y = screen_geometry.top(), screen_geometry.bottom() - 50
            clamped_y = max(min_y, min(new_pos.y(), max_y))

            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        event.accept()

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    """Native event filter to detect system time changes (WM_TIMECHANGE on Windows)."""
    def __init__(self, on_time_change_callback):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback
        logger.debug("TimeChangeEventFilter initialized with direct callback.")

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
                WM_TIMECHANGE = 0x001E
                if msg.message == WM_TIMECHANGE:
                    logger.info("⏰ System time changed (WM_TIMECHANGE detected). Calling direct callback.")
                    if callable(self.on_time_change_callback):
                        self.on_time_change_callback()
            except Exception as e:
                logger.error(f"Error processing Windows message in native event filter: {e}")
        return False, 0

# ==================== CUSTOM WIDGETS ====================

class CustomCheckbox(QWidget):
    """A custom checkbox widget using a FontAwesome icon and a label."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_checked = is_checked
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.LeftToRight)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        fa_font = QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14)
        self.icon_label.setFont(fa_font)
        self.icon_label.setFixedWidth(22)
        
        self.text_label = QLabel(text)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

        self.update_visuals()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._is_checked)
            self.toggled.emit(self._is_checked)
        super().mousePressEvent(event)

    def isChecked(self) -> bool:
        return self._is_checked

    def setChecked(self, checked: bool):
        if self._is_checked != checked:
            self._is_checked = checked
            self.update_visuals()

    def update_visuals(self):
        palette = APP_CONFIG.get_current_palette()
        icon = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID if self._is_checked else APP_CONFIG.FAS.FA_SQUARE_REGULAR
        icon_color = palette['ACCENT_COLOR'] if self._is_checked else palette['TEXT_COLOR']
        
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {icon_color}; background: transparent;")
        self.text_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            "font-size: 13px; font-weight: bold; background: transparent;"
        )
class RTLTextEdit(QTextEdit):
    def __init__(self, placeholder_text=""):
        super().__init__()
        self.placeholder_text = placeholder_text
        self.setLayoutDirection(Qt.RightToLeft)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.toPlainText() == "" and self.placeholder_text:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(128, 128, 128))
            rect = self.viewport().rect()
            rect.adjust(5, 5, -5, -5)
            painter.drawText(rect, Qt.AlignRight | Qt.AlignTop, self.placeholder_text)

class EventInputWidget(QWidget):
    """An integrated widget for adding or editing a user event."""
    saved = pyqtSignal(str, bool)
    canceled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.RightToLeft)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        self.title_label = QLabel("افزودن/ویرایش رویداد")
        main_layout.addWidget(self.title_label)
        
        self.text_edit = RTLTextEdit("رویداد خود را وارد کنید")
        text_option = QTextOption()
        text_option.setTextDirection(Qt.RightToLeft)
        self.text_edit.document().setDefaultTextOption(text_option)
        main_layout.addWidget(self.text_edit)

        checkbox_container_layout = QHBoxLayout()
        self.yearly_checkbox = CustomCheckbox("رویداد سالانه (تکرار هر سال)")
        checkbox_container_layout.addWidget(self.yearly_checkbox)
        checkbox_container_layout.addStretch()
        main_layout.addLayout(checkbox_container_layout)

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("ذخیره")
        self.cancel_button = QPushButton("لغو")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.save_button.clicked.connect(self._on_save)
        self.cancel_button.clicked.connect(self.canceled)
        
        self.update_styles()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet(f"""
            EventInputWidget {{
                background-color: {palette['BACKGROUND_COLOR']};
                border: 1px solid {palette['MENU_BORDER_COLOR']};
                border-radius: 15px;
            }}
        """)
        
        self.title_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 16px; font-weight: bold; border: none;")

        self.text_edit.setStyleSheet(
            f"background-color: {palette['INPUT_BG_COLOR']};"
            f"color: {palette['TEXT_COLOR']};"
            f"border: 1px solid {palette['CALENDAR_BORDER_COLOR']};"
            f"border-radius: 8px; padding: 5px;"
            f"font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px;"
        )
        
        self.yearly_checkbox.update_visuals()
        
        button_style = (
            f"QPushButton {{ background-color: transparent; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['GREY_COLOR']}; "
            f"border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {palette['HOVER_BG']}; border-color: {palette['TEXT_COLOR']}; }}"
        )
        self.cancel_button.setStyleSheet(button_style)
        
        save_button_style = (
            f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; "
            f"border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).lighter(110).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}")
        
        self.save_button.setStyleSheet(save_button_style)
        
        shadow = QGraphicsDropShadowEffect(blurRadius=25, xOffset=0, yOffset=5, color=QColor(0, 0, 0, 50))
        self.setGraphicsEffect(shadow)

    def set_data(self, text, is_yearly):
        self.text_edit.setText(text)
        self.yearly_checkbox.setChecked(is_yearly)

    def _on_save(self):
        self.saved.emit(self.text_edit.toPlainText().strip(), self.yearly_checkbox.isChecked())

class ClickableLabel(QLabel):
    """A QLabel that emits signals for clicks and context menu actions."""
    clicked = pyqtSignal(object)
    add_event_requested = pyqtSignal(object)
    remove_event_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None
        self.has_user_event = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QMouseEvent):
        if not self.jalali_date or not self.text(): return

        menu = QMenu(self)
        palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']};"
            f"  border-radius: 8px; padding: 5px; color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QMenu::item:disabled {{ color: {palette['GREY_COLOR']}; }}"
            f"QMenu::item:selected {{ background-color: {palette['HOVER_BG']}; }}"
            f"QMenu::separator {{ height: 1px; background-color: {palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
        )

        add_action_text = "ویرایش رویداد" if self.has_user_event else "افزودن رویداد"
        add_event_widget = MenuActionWidget(add_action_text, menu)
        add_action = QWidgetAction(menu)
        add_action.setDefaultWidget(add_event_widget)
        menu.addAction(add_action)

        menu.addSeparator()

        remove_event_widget = MenuActionWidget("حذف رویداد", menu)
        remove_action = QWidgetAction(menu)
        remove_action.setDefaultWidget(remove_event_widget)
        menu.addAction(remove_action)
        remove_action.setEnabled(self.has_user_event)
        remove_event_widget.setEnabled(self.has_user_event)

        add_event_widget.triggered.connect(lambda: self._trigger_add_event_and_close_menu(menu, self.jalali_date))
        remove_event_widget.triggered.connect(lambda: self._trigger_remove_event_and_close_menu(menu, self.jalali_date))

        menu.exec_(self.mapToGlobal(event.pos()))

    def _trigger_add_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        QTimer.singleShot(50, lambda: self.add_event_requested.emit(jdate))

    def _trigger_remove_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        QTimer.singleShot(50, lambda: self.remove_event_requested.emit(jdate))


class HoverWidget(QWidget):
    """Base widget for menu items that handles hover effects."""
    triggered = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")

    def paintEvent(self, event):
        if self._is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, QColor(*APP_CONFIG.current_palette["MENU_HOVER_COLOR"]))
        super().paintEvent(event)
        
    def enterEvent(self, event): self._is_hovered = True; self.update()
    def leaveEvent(self, event): self._is_hovered = False; self.update()
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton: self.triggered.emit()

class MenuActionWidget(HoverWidget):
    """Custom widget for a simple text-based menu action."""
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 6, 15, 6)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addStretch()
        self._update_style()

    def setEnabled(self, enabled: bool):
        """Overrides setEnabled to update the visual style."""
        super().setEnabled(enabled)
        self._update_style()

    def _update_style(self):
        """Updates the label's style based on whether the widget is enabled."""
        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR'] if self.isEnabled() else palette['GREY_COLOR']
        
        self.label.setStyleSheet(
            f"color: {text_color}; font-family: '{APP_CONFIG.FONT_FAMILY}';"
            f"font-size: 14px; font-weight: bold; background: transparent; border: none;"
        )


class IconCheckboxActionWidget(HoverWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_checked = is_checked
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 5, 10, 5); layout.setSpacing(8)
        self.icon_label = QLabel(); self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14)); self.icon_label.setFixedWidth(22)
        self.text_label = QLabel(text)
        layout.addWidget(self.icon_label); layout.addWidget(self.text_label); layout.addStretch()
        self.update_visuals()

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self.toggled.emit(self.is_checked)
            self.update_visuals()

    def setChecked(self, checked: bool):
        if self.is_checked != checked: self.is_checked = checked; self.update_visuals()

    def update_visuals(self):
        icon = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID if self.is_checked else APP_CONFIG.FAS.FA_SQUARE_REGULAR
        self.icon_label.setText(icon)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self.text_label.setStyleSheet(
            f"color: {color}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            "font-size: 14px; font-weight: bold; background: transparent;"
        )

class ThemeToggleActionWidget(MenuActionWidget):
    """Widget for the 'App Theme' toggle in the context menu."""
    def __init__(self, current_theme_getter, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.current_theme_getter = current_theme_getter
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.icon_label = QLabel(); self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14)); self.icon_label.setFixedWidth(22)
        self.label = QLabel("") 
        layout.addStretch(); layout.addWidget(self.icon_label); layout.addSpacing(0); layout.addWidget(self.label); layout.addStretch()
        self.update_display()

    def paintEvent(self, event): self.update_display(); super().paintEvent(event)
    def update_display(self):
        theme = self.current_theme_getter()
        icon = APP_CONFIG.FAS.FA_MOON_SOLID if theme == APP_CONFIG.Theme.DARK else APP_CONFIG.FAS.FA_SUN_SOLID
        text = "    تم برنامه: تیره" if theme == APP_CONFIG.Theme.DARK else "    تم برنامه: روشن"
        self.icon_label.setText(icon); self.label.setText(text)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;"); self._update_style()

# ==================== PERSIAN CALENDAR WIDGET ====================

class PersianCalendarWidget(BaseFramelessWindow):
    """Main calendar widget displaying a month of Persian (Jalali) dates."""
    ROWS, COLS = 6, 7
    event_added = pyqtSignal(object, str, bool)
    event_removed = pyqtSignal(object)

    def __init__(self, holidays_cache: dict, user_events: dict):
        super().__init__()
        self.holidays_cache = holidays_cache
        self.user_events = user_events
        self.holidays: Dict[Tuple[int, int], List[str]] = {}
        
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.selected_date = self.current_date
        self.editing_date: Optional[jdatetime.date] = None
        
        self.day_labels: List[List[ClickableLabel]] = []
        self._show_gregorian_mdy = True
        
        self._setup_ui()
        self.update_styles()
        self.fill_calendar_grid()

    def set_user_events(self, user_events: dict):
        self.user_events = user_events
        self.fill_calendar_grid()

    def _setup_ui(self):
        self.setFixedSize(APP_CONFIG.CALENDAR_WIDTH, APP_CONFIG.CALENDAR_HEIGHT)
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(15, 10, 15, 10); main_layout.setSpacing(0)
        main_layout.addLayout(self._create_header())
        main_layout.addLayout(self._create_gregorian_bar())
        self.weekdays_layout = self._create_weekdays_header()
        main_layout.addLayout(self.weekdays_layout)
        self.calendar_grid_layout = self._create_calendar_grid()
        main_layout.addLayout(self.calendar_grid_layout)
        
        # --- Integrated Event Input Widget ---
        self.event_input_widget = EventInputWidget(self)
        self.event_input_widget.saved.connect(self._handle_event_saved)
        self.event_input_widget.canceled.connect(self._handle_event_canceled)
        self.event_input_widget.hide()

    def _create_header(self) -> QHBoxLayout:
        self.left_arrow_btn = QPushButton("❮"); self.left_arrow_btn.clicked.connect(self.next_month)
        self.right_arrow_btn = QPushButton("❯"); self.right_arrow_btn.clicked.connect(self.prev_month)
        self.year_label = QLabel(); self.month_label = QLabel()
        month_year_layout = QHBoxLayout(); month_year_layout.setSpacing(5); month_year_layout.setContentsMargins(0, 0, 0, 0)
        month_year_layout.setAlignment(Qt.AlignCenter); month_year_layout.addWidget(self.year_label); month_year_layout.addWidget(self.month_label)
        month_year_container = QWidget(); month_year_container.setLayout(month_year_layout)
        header_layout = QHBoxLayout(); header_layout.setContentsMargins(0, 0, 0, -5); header_layout.setSpacing(10)
        header_layout.addWidget(self.left_arrow_btn); header_layout.addStretch(1); header_layout.addWidget(month_year_container); header_layout.addStretch(1); header_layout.addWidget(self.right_arrow_btn)
        return header_layout

    def _create_gregorian_bar(self) -> QHBoxLayout:
        self.gregorian_date_label = ClickableLabel(); self.gregorian_date_label.clicked.connect(self._toggle_gregorian_format)
        self.today_btn = QPushButton("امروز"); self.today_btn.clicked.connect(self.go_to_today)
        layout = QHBoxLayout(); layout.setContentsMargins(0, 0, 0, 10)
        layout.addWidget(self.gregorian_date_label); layout.addStretch(); layout.addWidget(self.today_btn)
        return layout

    def _create_weekdays_header(self) -> QHBoxLayout:
        layout = QHBoxLayout(); layout.setSpacing(5); layout.setContentsMargins(0, 0, 0, 10); layout.setDirection(QBoxLayout.RightToLeft)
        for day_name in APP_CONFIG.PERSIAN_WEEKDAYS_SHORT:
            label = QLabel(day_name); label.setObjectName("WeekdayLabel"); label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE); layout.addWidget(label)
        return layout

    def _create_calendar_grid(self):
        grid_layout = QGridLayout(); grid_layout.setSpacing(5); grid_layout.setOriginCorner(Qt.TopRightCorner)
        for row in range(self.ROWS):
            week_labels = []
            for col in range(self.COLS):
                label = ClickableLabel(); label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
                label.clicked.connect(self._on_day_clicked)
                label.add_event_requested.connect(self._show_event_input_widget)
                label.remove_event_requested.connect(self._remove_event)
                grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)
        return grid_layout
    
    def _get_nav_button_style(self, bg_color: str, is_today_button: bool = False) -> str:
        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR']
        if is_today_button:
            base_color = QColor(bg_color); hover_color = base_color.lighter(120).name(); pressed_color = base_color.darker(120).name()
            return (f"QPushButton {{ background-color: {base_color.name()}; color: white; border: none; border-radius: 8px; }}"
                    f"QPushButton:hover {{ background-color: {hover_color}; }}"
                    f"QPushButton:pressed {{ background-color: {pressed_color}; }}")
        else:
            hover_color = QColor(bg_color).darker(120).name() if bg_color != "transparent" else palette['HOVER_BG']
            return (f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border: none; border-radius: 8px; }}"
                    f"QPushButton:hover {{ background-color: {hover_color}; }}")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette(); text_color, accent_color = palette['TEXT_COLOR'], palette['ACCENT_COLOR']
        nav_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Bold); today_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Bold)
        self.left_arrow_btn.setFont(nav_button_font); self.right_arrow_btn.setFont(nav_button_font)
        self.left_arrow_btn.setStyleSheet(self._get_nav_button_style("transparent")); self.right_arrow_btn.setStyleSheet(self._get_nav_button_style("transparent"))
        self.left_arrow_btn.setFixedSize(30, 30); self.right_arrow_btn.setFixedSize(30, 30)
        self.today_btn.setFont(today_button_font); self.today_btn.setStyleSheet(self._get_nav_button_style(accent_color, is_today_button=True)); self.today_btn.setFixedSize(60, 30)
        header_style = f"color: {text_color}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';"
        self.year_label.setStyleSheet(header_style); self.month_label.setStyleSheet(header_style)
        self.gregorian_date_label.setStyleSheet(f"QLabel {{ color: {text_color}; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; background-color: {palette['HOVER_BG']}; font-family: '{APP_CONFIG.GREGORIAN_FONT_FAMILY}'; font-weight: bold; border-radius: 8px; padding: 3px 6px; }} QLabel:hover {{ background-color: {palette['GREGORIAN_DATE_HOVER_BG']}; }}")
        for i in range(self.weekdays_layout.count()):
            day_label = self.weekdays_layout.itemAt(i).widget()
            if isinstance(day_label, QLabel):
                is_friday = day_label.text() == 'ج'; color = palette['HOLIDAY_COLOR'] if is_friday else palette['WEEKDAY_NAMES_COLOR']
                day_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 16px; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}';")
        
        if self.event_input_widget:
            self.event_input_widget.update_styles()

        self.fill_calendar_grid()

    def _get_user_event_for_date(self, jdate: jdatetime.date) -> Tuple[Optional[str], bool]:
        """Checks for a specific or yearly event, returning the text and if it was yearly."""
        specific_key = jdate.strftime("%Y-%m-%d")
        if specific_key in self.user_events:
            event_data = self.user_events[specific_key]
            if isinstance(event_data, dict):
                return event_data.get("text"), event_data.get("yearly", False)
            else:
                return event_data, False

        yearly_key = jdate.strftime("0000-%m-%d")
        if yearly_key in self.user_events:
            event_data = self.user_events[yearly_key]
            return event_data.get("text"), True
            
        return None, False

    def fill_calendar_grid(self):
        self._update_header()
        self.holidays = self.holidays_cache.get(self.display_date.year, {})
        first_day = self.display_date.replace(day=1)
        start_day_of_week = first_day.weekday()

        current_day = first_day - datetime.timedelta(days=start_day_of_week)
        for row in range(self.ROWS):
            for col in range(self.COLS):
                label = self.day_labels[row][col]
                label.jalali_date = current_day
                label.setText(to_persian_digits(current_day.day))
                
                user_event_text, _ = self._get_user_event_for_date(current_day)
                label.has_user_event = bool(user_event_text)

                is_in_display_month = (current_day.month == self.display_date.month)
                stylesheet, tooltip = self._get_day_style(current_day, is_in_display_month)
                label.setStyleSheet(stylesheet)
                label.setToolTip(tooltip)
                current_day += datetime.timedelta(days=1)

    def _update_header(self):
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(self.display_date.year))
        greg_date = self.selected_date.togregorian()
        self.gregorian_date_label.setText(greg_date.strftime("%m/%d/%Y") if self._show_gregorian_mdy else greg_date.strftime("%b %d, %Y"))

    def _get_rgba_string(self, color_hex: str, alpha: float) -> str:
        color = QColor(color_hex)
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

    def _get_day_style(self, jdate: jdatetime.date, is_in_month: bool) -> Tuple[str, str]:
        user_event_text, _ = self._get_user_event_for_date(jdate)
        is_user_event = bool(user_event_text)
        is_today = (jdate == self.current_date)
        is_selected = (jdate == self.selected_date)
        is_friday = jdate.weekday() == 6
        holiday_reasons = self.holidays.get((jdate.month, jdate.day))
        is_holiday = bool(holiday_reasons)

        palette = APP_CONFIG.get_current_palette()

        # --- Tooltip Generation ---
        tooltip_parts = []
        if holiday_reasons:
            holiday_color = palette['HOLIDAY_COLOR']
            html_reasons = ", ".join(holiday_reasons).replace('<', '&lt;').replace('>', '&gt;')
            tooltip_parts.append(f'<span style="white-space: nowrap; color:{holiday_color};">{html_reasons}</span>')

        if is_user_event:
            event_color = palette['ACCENT_COLOR']
            html_event_text = user_event_text.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            tooltip_parts.append(f'<span style="color:{event_color};">{html_event_text}</span>')

        tooltip = "<br>".join(tooltip_parts)

        # --- Style Generation ---
        text_color = palette['TEXT_COLOR']
        background_color_rgba = "transparent"
        border_style = "none"
        font_size = APP_CONFIG.FONT_SIZE_LABEL
        hover_background_color_rgba = palette['HOVER_BG']
        base_color_hex = palette['TEXT_COLOR']

        if is_in_month:
            if is_user_event:
                base_color_hex = palette['ACCENT_COLOR']
                text_color = base_color_hex
            elif is_holiday or is_friday:
                base_color_hex = palette['HOLIDAY_COLOR']
                text_color = base_color_hex

            if is_today and is_selected:
                if is_user_event or is_holiday or is_friday:
                    background_color_rgba = self._get_rgba_string(base_color_hex, 0.6)
                    hover_background_color_rgba = self._get_rgba_string(base_color_hex, 0.7)
                else:
                    background_color_rgba = self._get_rgba_string(base_color_hex, 0.35)
                    hover_background_color_rgba = self._get_rgba_string(base_color_hex, 0.45)
            elif is_selected:
                if is_user_event or is_holiday or is_friday:
                    background_color_rgba = self._get_rgba_string(base_color_hex, 0.45)
                    hover_background_color_rgba = self._get_rgba_string(base_color_hex, 0.55)
                else: 
                    background_color_rgba = palette['CALENDAR_SELECTED_BG_COLOR']
                    hover_background_color_rgba = palette['CALENDAR_SELECTED_HOVER_BG_COLOR']
            elif is_today:
                if is_user_event or is_holiday or is_friday:
                    background_color_rgba = self._get_rgba_string(base_color_hex, 0.35)
                    hover_background_color_rgba = self._get_rgba_string(base_color_hex, 0.45)
                else: 
                    background_color_rgba = palette['CALENDAR_TODAY_BG_COLOR']
                    hover_background_color_rgba = palette['CALENDAR_TODAY_HOVER_BG_COLOR']
            elif is_user_event or is_holiday or is_friday:
                background_color_rgba = self._get_rgba_string(base_color_hex, 0.15)
                hover_background_color_rgba = self._get_rgba_string(base_color_hex, 0.3)

            if is_today or is_selected:
                border_style = f"1px solid {base_color_hex}"

            if is_today:
                font_size = 17
        else:
            text_color = palette['GREY_COLOR']
            if is_user_event:
                text_color = self._get_rgba_string(palette['ACCENT_COLOR'], 0.45)
                background_color_rgba = self._get_rgba_string(palette['ACCENT_COLOR'], 0.05)
                hover_background_color_rgba = self._get_rgba_string(palette['ACCENT_COLOR'], 0.10)
            elif is_holiday or is_friday:
                text_color = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.45)
                background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.05)
                hover_background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.10)
        
        style = (f"background-color: {background_color_rgba}; color: {text_color}; border: {border_style}; "
                 f"border-radius: 8px; font-size: {font_size}px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';")
        
        return f"QLabel {{ {style} }} QLabel:hover {{ background-color: {hover_background_color_rgba}; }}", tooltip

    def _navigate(self, months: int):
        new_year, new_month = self.display_date.year, self.display_date.month + months
        while new_month < 1: new_month += 12; new_year -= 1
        while new_month > 12: new_month -= 12; new_year += 1
        try: self.display_date = jdatetime.date(new_year, new_month, self.display_date.day)
        except ValueError:
            last_day = 31 if 1 <= new_month <= 6 else (30 if 7 <= new_month <= 11 else (30 if is_jalali_leap_year(new_year) else 29))
            self.display_date = jdatetime.date(new_year, new_month, last_day)
        self.fill_calendar_grid()

    def prev_month(self): self._navigate(-1)
    def next_month(self): self._navigate(1)
    
    def go_to_today(self):
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date; self.selected_date = self.current_date
        self.fill_calendar_grid()

    def _on_day_clicked(self, jdate: Optional[jdatetime.date]):
        if jdate and not self.event_input_widget.isVisible():
            self.selected_date = jdate
            if jdate.month != self.display_date.month: self.display_date = jdate
            self.fill_calendar_grid()

    def _toggle_gregorian_format(self, _):
        self._show_gregorian_mdy = not self._show_gregorian_mdy
        self._update_header()

    def _show_event_input_widget(self, jdate: jdatetime.date):
        if not jdate: return
        self.editing_date = jdate
        
        existing_text, is_yearly = self._get_user_event_for_date(jdate)
        self.event_input_widget.set_data(existing_text or "", is_yearly)
        
        width = self.width() - 40
        height = 200
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _handle_event_saved(self, text: str, is_yearly: bool):
        if self.editing_date:
            if text:
                self.event_added.emit(self.editing_date, text, is_yearly)
            else:
                self.event_removed.emit(self.editing_date)
        self._hide_event_input_widget()

    def _handle_event_canceled(self):
        self._hide_event_input_widget()

    def _hide_event_input_widget(self):
        self.editing_date = None
        self.event_input_widget.hide()

    def _remove_event(self, jdate: jdatetime.date):
        if not jdate: return
        self.event_removed.emit(jdate)

# ==================== TUTORIAL WINDOW ====================

class TutorialWindow(BaseFramelessWindow):
    """A window to display a first-time tutorial for the app."""
    tutorial_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("راهنمای شروع"); self.setFixedSize(500, 400)
        self._setup_ui(); self.update_styles(); self._apply_windows_styles()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20, 20, 20, 20); main_layout.setSpacing(15)
        self.message_label = QLabel("برای دسترسی آسان، می‌توانید آیکون برنامه را از بخش آیکون‌های پنهان ویندوز، به نوار وظیفه اصلی بکشید.")
        self.message_label.setWordWrap(True); self.message_label.setAlignment(Qt.AlignCenter); main_layout.addWidget(self.message_label)
        self.gif_label = QLabel(); self.gif_label.setAlignment(Qt.AlignCenter); main_layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)
        self._load_gif()
        main_layout.addStretch(1)
        self.close_button = QPushButton("بستن آموزش"); self.close_button.clicked.connect(self._close_tutorial); main_layout.addWidget(self.close_button)

    def _load_gif(self):
        gif_path = str(APP_CONFIG.TUTORIAL_GIF_PATH)
        if not os.path.exists(gif_path):
            logger.error(f"Tutorial GIF not found: {gif_path}"); self.gif_label.setText("فایل GIF یافت نشد."); return
        self.movie = QMovie(gif_path)
        if self.movie.isValid():
            self.gif_label.setMovie(self.movie); self.movie.setCacheMode(QMovie.CacheAll)
            self.movie.setSpeed(100); self.movie.loopCount = -1; self.movie.start()
        else: logger.warning(f"Failed to load GIF from {gif_path}.")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.message_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12)); self.message_label.setStyleSheet(f"color: {palette['TEXT_COLOR']};")
        self.close_button.setFixedHeight(50)
        self.close_button.setStyleSheet(f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }} QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}")

    def _close_tutorial(self):
        if hasattr(self, 'movie') and self.movie: self.movie.stop()
        self.tutorial_closed.emit(); self.close()

    def _apply_windows_styles(self):
        try:
            import win32con, win32gui
            hwnd = self.winId().__int__()
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU)
        except (ImportError, Exception) as e:
            logger.warning(f"Could not set Windows styles for tutorial: {e}")

# ==================== SYSTEM TRAY ICON (MAIN CONTROLLER) ====================

class SystemTrayIcon(QSystemTrayIcon):
    """The main application controller, managing the tray icon, windows, and settings."""

    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
        self.holidays_cache = self._load_holidays_from_file()
        self.user_events = self._load_user_events()
        
        self.calendar_widget = PersianCalendarWidget(self.holidays_cache, self.user_events)
        self.calendar_widget.event_added.connect(self.add_user_event)
        self.calendar_widget.event_removed.connect(self.remove_user_event)

        self.converter_window: Optional[DateConverterWindow] = None
        self.tutorial_window: Optional[TutorialWindow] = None

        self._load_settings() 
        self._validate_and_apply_startup_setting()
        self._apply_theme()
        self.activated.connect(self.on_tray_icon_activated)
        self._setup_timers()
        self.update_tray_icon(force=True)

    def _load_settings(self):
        self.is_open_at_login = self.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool)
        self.current_theme = self.settings.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.DARK, type=str)
        logger.info(f"Loaded settings: OpenAtLogin={self.is_open_at_login}, Theme={self.current_theme}")

    def _apply_theme(self):
        APP_CONFIG.set_theme(self.current_theme)
        QApplication.instance().setStyleSheet(self._build_global_stylesheet())
        self.update_tray_icon(force=True); self._setup_context_menu()
        if self.calendar_widget: self.calendar_widget.update_styles()
        if self.converter_window and self.converter_window.isVisible(): self.converter_window.update_styles()
        if self.tutorial_window and self.tutorial_window.isVisible(): self.tutorial_window.update_styles()
    
    def _setup_timers(self):
        self.minute_timer = QTimer(self)
        self.minute_timer.timeout.connect(lambda: self.update_tray_icon(force=False))
        self.minute_timer.start(60 * 1000)
        self.event_filter = TimeChangeEventFilter(self._handle_system_time_change)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)
        self.schedule_next_midnight_check()

    def _on_midnight_timer_triggered(self):
        logger.info("Midnight timer triggered. Updating tray icon for new day.")
        self.update_tray_icon(force=True); self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        now = datetime.datetime.now(); tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        millis_until_midnight = int((midnight - now).total_seconds() * 1000); buffer_ms = 500
        if hasattr(self, '_midnight_timer') and self._midnight_timer.isActive():
            self._midnight_timer.stop(); del self._midnight_timer
        self._midnight_timer = QTimer(self); self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight_timer_triggered)
        self._midnight_timer.start(millis_until_midnight + buffer_ms)
        logger.debug(f"Next midnight check scheduled in {millis_until_midnight + buffer_ms} ms.")

    def _handle_system_time_change(self):
        logger.info("System time change detected. Forcing tray icon update and rescheduling midnight check.")
        self.update_tray_icon(force=True); self.schedule_next_midnight_check()

    def _build_global_stylesheet(self) -> str:
        palette = APP_CONFIG.get_current_palette()
        return (f"QToolTip {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; font-size: 14px;}}"
                f"QScrollBar:vertical {{ border: none; background: {palette['SCROLLBAR_GROOVE_COLOR']}; width: 10px; margin: 0px; border-radius: 5px;}}"
                f"QScrollBar::handle:vertical {{ background: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: 5px; min-height: 20px;}}"
                f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
                f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}")
    
    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        try:
            with open(APP_CONFIG.HOLIDAYS_FILE_PATH, 'r', encoding='utf-8') as f: raw_data = json.load(f).get('holidays', {})
            holidays_data = {}
            for year_str, events in raw_data.items():
                year_int = int(year_str); holidays_data[year_int] = {}
                for month_day_str, desc in events.items():
                    month, day = map(int, month_day_str.split('-'))
                    holidays_data[year_int][(month, day)] = [desc] if isinstance(desc, str) else desc
            logger.info("Holidays loaded successfully."); return holidays_data
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load or parse holidays file: {e}"); return {}

    def _load_user_events(self) -> Dict[str, dict]:
        """Loads user events from QSettings and ensures they are in the new format."""
        events = self.settings.value(APP_CONFIG.USER_EVENTS_SETTING_KEY, {}, type=dict)
        migrated = False
        for key, value in events.items():
            if isinstance(value, str):
                events[key] = {"text": value, "yearly": False}
                migrated = True
        if migrated:
            logger.info("Migrated old event format to new format.")
            self.settings.setValue(APP_CONFIG.USER_EVENTS_SETTING_KEY, events)
        logger.info(f"Loaded {len(events)} user events.")
        return events

    def _save_user_events(self):
        self.settings.setValue(APP_CONFIG.USER_EVENTS_SETTING_KEY, self.user_events)
        logger.info(f"Saved {len(self.user_events)} user events.")

    def add_user_event(self, jdate: jdatetime.date, text: str, is_yearly: bool):
        if not jdate: return
        
        self.remove_user_event(jdate, save=False)

        key = jdate.strftime("0000-%m-%d") if is_yearly else jdate.strftime("%Y-%m-%d")
        self.user_events[key] = {"text": text, "yearly": is_yearly}
        
        self._save_user_events()
        self.calendar_widget.set_user_events(self.user_events)
        self.update_tray_icon(force=True)

    def remove_user_event(self, jdate: jdatetime.date, save: bool = True):
        if not jdate: return
        
        specific_key = jdate.strftime("%Y-%m-%d")
        yearly_key = jdate.strftime("0000-%m-%d")
        
        event_removed = False
        if specific_key in self.user_events:
            del self.user_events[specific_key]
            event_removed = True
        if yearly_key in self.user_events:
            del self.user_events[yearly_key]
            event_removed = True

        if event_removed and save:
            self._save_user_events()
            self.calendar_widget.set_user_events(self.user_events)
            self.update_tray_icon(force=True)
    
    def update_tray_icon(self, force: bool = False):
        new_date = jdatetime.date.today()
        if not force and hasattr(self.calendar_widget, 'current_date') and new_date == self.calendar_widget.current_date: return

        logger.info(f"Updating tray icon for new date: {new_date}")
        self.calendar_widget.current_date = new_date
        if self.calendar_widget.isVisible(): self.calendar_widget.fill_calendar_grid()

        screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96
        icon_size, font_size = (36, 20) if dpi >= 110 else (38, 26)
        
        pixmap = QPixmap(icon_size, icon_size); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
        
        day_str = to_persian_digits(new_date.day)
        
        user_event_text, _ = self.calendar_widget._get_user_event_for_date(new_date)
        is_user_event = bool(user_event_text)
        is_holiday = new_date.weekday() == 6 or self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day))
        
        color = APP_CONFIG.TRAY_ICON_DARK_COLOR if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.TRAY_ICON_LIGHT_COLOR
        if is_user_event: color = APP_CONFIG.current_palette['ACCENT_COLOR']
        elif is_holiday: color = APP_CONFIG.current_palette['HOLIDAY_COLOR']
        
        painter.setPen(QColor(color))
        painter.setFont(QFont(APP_CONFIG.FONT_FAMILY, font_size, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, day_str)
        painter.end()
        self.setIcon(QIcon(pixmap))

        weekday_name = persian_weekday_name(new_date.weekday()); month_name = persian_month_name(new_date.month)
        year_str, month_str, day_str2 = str(new_date.year), f"{new_date.month:02d}", f"{new_date.day:02d}"
        month_written = f"\u200F{day_str2} {month_name} {year_str}"
        tooltip_lines = [weekday_name, f"{year_str}/{month_str}/{day_str2}", month_written]

        if is_holiday:
            holiday_reasons = self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day), [])
            if holiday_reasons: tooltip_lines.append("تعطیلی:"); tooltip_lines.extend(holiday_reasons)
        if is_user_event:
            if is_holiday: tooltip_lines.append("---")
            tooltip_lines.append("رویداد:")
            tooltip_lines.extend(user_event_text.split('\n'))
                
        self.setToolTip("\n".join(tooltip_lines))

    def _setup_context_menu(self):
        menu = QMenu(); palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }} QMenu::separator {{ height: 1px; background-color: {palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}")
        self._add_menu_action(menu, "تبدیل تاریخ", self._open_date_converter); menu.addSeparator()
        self._add_theme_toggle_action(menu); menu.addSeparator()
        self._add_startup_action(menu); menu.addSeparator()
        self._add_menu_action(menu, "خروج", QApplication.quit)
        self.setContextMenu(menu)
    
    def _add_menu_action(self, menu, text, slot):
        action = QWidgetAction(self); widget = MenuActionWidget(text, parent=menu)
        widget.triggered.connect(slot); action.setDefaultWidget(widget); menu.addAction(action)

    def _add_theme_toggle_action(self, menu):
        action = QWidgetAction(self); widget = ThemeToggleActionWidget(lambda: self.current_theme, parent=menu)
        widget.triggered.connect(self._toggle_theme); action.setDefaultWidget(widget); menu.addAction(action)

    def _add_startup_action(self, menu):
        if not sys.platform.startswith('win'): return
        action = QWidgetAction(self); widget = IconCheckboxActionWidget("راه اندازی همراه با سیستم", self.is_open_at_login, parent=menu)
        widget.toggled.connect(self._toggle_open_at_boot); action.setDefaultWidget(widget); menu.addAction(action)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.calendar_widget.isVisible():
                if self.calendar_widget.event_input_widget.isVisible():
                    self.calendar_widget._hide_event_input_widget()
                else:
                    self.calendar_widget.hide()
            else:
                self.show_calendar()

    def show_calendar(self):
        self.calendar_widget.current_date = jdatetime.date.today()
        if self.calendar_widget.selected_date is None or self.calendar_widget.selected_date.month != self.calendar_widget.display_date.month:
             self.calendar_widget.display_date = jdatetime.date.today()
             self.calendar_widget.selected_date = jdatetime.date.today()
        self.calendar_widget.fill_calendar_grid(); self.calendar_widget.update_styles()
        screen = QApplication.primaryScreen().availableGeometry(); tray_geom = self.geometry()
        widget_size = self.calendar_widget.size()
        x = screen.right() - widget_size.width() - 10; y = screen.bottom() - widget_size.height() - 45 
        if tray_geom.isValid():
            x = tray_geom.center().x() - widget_size.width() // 2; y = tray_geom.top() - widget_size.height() - 5
            x = max(screen.left(), min(x, screen.right() - widget_size.width())); y = max(screen.top(), min(y, screen.bottom() - widget_size.height()))
        self.calendar_widget.move(int(x), int(y)); self.calendar_widget.show(); self.calendar_widget.activateWindow()

    def _toggle_theme(self):
        self.current_theme = APP_CONFIG.Theme.LIGHT if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.Theme.DARK
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, self.current_theme)
        logger.info(f"Theme toggled to: {self.current_theme}"); self._apply_theme()

    def _set_startup_registry(self, enable: bool):
        """
        Private helper to set or remove the Windows startup registry key.
        """
        if not sys.platform.startswith('win'):
            logger.warning("Auto-start is only supported on Windows.")
            return

        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                # Use sys.executable for PyInstaller builds, otherwise sys.argv[0]
                executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
                winreg.SetValueEx(key, APP_CONFIG.APP_NAME, 0, winreg.REG_SZ, f'"{executable_path}"')
                logger.info(f"Set startup registry key to: {executable_path}")
            else:
                winreg.DeleteValue(key, APP_CONFIG.APP_NAME)
                logger.info("Removed startup registry key.")
            winreg.CloseKey(key)
        except FileNotFoundError:
            if not enable:
                logger.warning("Could not remove startup key (it may not exist).")
            else:
                logger.error(f"Could not find registry key path: {key_path}")
        except Exception as e:
            logger.error(f"Error modifying Windows registry: {e}")


    def _toggle_open_at_boot(self, checked: bool):
        self.is_open_at_login = checked
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        logger.info(f"Setting 'Open at Login' to {checked}.")
        self._set_startup_registry(checked)

    def _validate_and_apply_startup_setting(self):
        """
        NEW: Verifies the startup setting is correctly applied in the registry.
        If the setting is true but the registry key is missing or incorrect, it fixes it.
        """
        if not sys.platform.startswith('win') or not self.is_open_at_login:
            return

        logger.info("Validating startup registry key...")
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        expected_value = f'"{executable_path}"'
        needs_update = True

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            current_value, _ = winreg.QueryValueEx(key, APP_CONFIG.APP_NAME)
            if current_value == expected_value:
                logger.info("Startup registry key is correct.")
                needs_update = False
            else:
                logger.warning(f"Startup registry key is incorrect. Found: '{current_value}', Expected: '{expected_value}'")
            winreg.CloseKey(key)
        except FileNotFoundError:
            logger.warning("Startup registry key not found.")
        except Exception as e:
            logger.error(f"Error reading startup registry key: {e}")

        if needs_update:
            logger.info("Re-applying startup registry key.")
            self._set_startup_registry(True)

    def _open_date_converter(self):
        if self.converter_window is None or not self.converter_window.isVisible():
            self.converter_window = DateConverterWindow(); self.converter_window.show(); self.converter_window.activateWindow()
        else: self.converter_window.activateWindow()

# ==================== MAIN APPLICATION ENTRY ====================

def main():
    """Initializes and runs the ShamsiTray application."""
    try: verify_assets()
    except FileNotFoundError as e: QMessageBox.critical(None, "خطا در فایل‌های برنامه", str(e)); sys.exit(1)

    if sys.platform == 'win32':
        myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True); QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    
    try: load_fonts()
    except (RuntimeError, FileNotFoundError) as e: QMessageBox.critical(None, "خطای فونت", str(e)); sys.exit(1)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "خطا", "هیچ System Tray در این سیستم یافت نشد."); sys.exit(1)

    tray_icon = SystemTrayIcon(); tray_icon.show()
    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run: Showing tutorial.")
        tutorial = TutorialWindow(); tray_icon.tutorial_window = tutorial; tutorial.show()
        screen_center = QApplication.primaryScreen().availableGeometry().center()
        tutorial.move(screen_center - tutorial.rect().center())
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()