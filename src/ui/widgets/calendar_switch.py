"""
Calendar Switch
---------------

The «شمسی | میلادی» segmented control of the date tools' caption rows: the
converter picks which calendar its input row speaks with it, the distance
window which calendar both of its date rows are read in.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from config import APP_CONFIG
from utils.ui_helpers import palette_on_accent_text

CALENDAR_JALALI = "jalali"
CALENDAR_GREGORIAN = "gregorian"


class CalendarSwitch(QFrame):
    """The شمسی | میلادی segmented control of the caption row."""
    calendar_changed = Signal(str)  # CALENDAR_JALALI / CALENDAR_GREGORIAN

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CalendarSwitch")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        self.jalali_button = QPushButton("شمسی")
        self.gregorian_button = QPushButton("میلادی")
        self._calendar = CALENDAR_JALALI
        for button, calendar in ((self.jalali_button, CALENDAR_JALALI),
                                 (self.gregorian_button, CALENDAR_GREGORIAN)):
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, c=calendar: self.set_calendar(c))
            layout.addWidget(button)
        self._sync_checked()

    @property
    def calendar(self) -> str:
        return self._calendar

    def set_calendar(self, calendar: str) -> None:
        if calendar == self._calendar:
            self._sync_checked()  # a click on the checked segment must not uncheck it
            return
        self._calendar = calendar
        self._sync_checked()
        self.calendar_changed.emit(calendar)

    def _sync_checked(self) -> None:
        self.jalali_button.setChecked(self._calendar == CALENDAR_JALALI)
        self.gregorian_button.setChecked(self._calendar == CALENDAR_GREGORIAN)

    def update_styles(self) -> None:
        palette = APP_CONFIG.get_current_palette()
        font = f"font-family: '{APP_CONFIG.FONT_FAMILY}';"
        self.setStyleSheet(
            f"QFrame#CalendarSwitch {{ background-color: {palette['INPUT_BG_COLOR']}; "
            f"border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 11px; }}"
            f"QPushButton {{ {font} font-size: 14px; font-weight: bold; padding: 5px 20px; "
            f"border: none; border-radius: 8px; background: transparent; "
            f"color: {palette['WEEKDAY_NAMES_COLOR']}; }}"
            f"QPushButton:hover:!checked {{ color: {palette['TEXT_COLOR']}; }}"
            f"QPushButton:checked {{ background-color: {palette['ACCENT_COLOR']}; "
            f"color: {palette_on_accent_text(palette)}; }}")
