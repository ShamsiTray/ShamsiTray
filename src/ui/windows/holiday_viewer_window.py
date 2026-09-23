"""
Holiday Viewer Window
---------------------

`HolidayViewerWindow` is a read-only browser for the loaded holiday data,
opened from the tray menu («مشاهده تعطیلات»). Holidays are shown for one
Jalali year at a time (selectable, defaulting to the current year), grouped
under Persian month headers with one row per date and its descriptions.
The year can also be stepped with «❯» / «❮» buttons flanking the combo box.

The data comes straight from the in-memory holiday cache the calendar uses,
so what is shown here is exactly what the calendar highlights; updated data
pulled by the auto-updater appears here the next time the window is opened.
"""
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from config import APP_CONFIG
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.date_utils import persian_month_name, to_persian_digits
from utils.logger import setup_logging
from utils.ui_helpers import (center_combo_items, combo_stylesheet,
                              fit_combo_width, scrollbar_stylesheet)
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)


class HolidayViewerWindow(BaseFramelessWindow):
    """Read-only list of official holidays grouped by Persian month."""

    WIDTH, HEIGHT = 430, 560
    TASKBAR_ICON = True  # taskbar entry so a minimized viewer can be reopened

    def __init__(self, holidays_cache: Dict[int, Dict[Tuple[int, int], List[str]]]):
        super().__init__()
        self.holidays_cache = holidays_cache
        self.setWindowTitle("مشاهده تعطیلات")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._setup_ui()
        self.update_styles()
        apply_windows_styles(self)

    def set_holidays(self, holidays_cache: Dict[int, Dict[Tuple[int, int], List[str]]]):
        """Swap the holiday cache and rebuild the visible year.

        An open viewer used to keep showing the old data after a live holiday
        auto-update until it was closed and reopened. The currently browsed year
        is restored when the new data still offers it.
        """
        self.holidays_cache = holidays_cache
        previous_year = self._current_year()
        self._populate_years()
        if previous_year is not None:
            index = self.year_combo.findData(previous_year)
            if index >= 0:
                self.year_combo.setCurrentIndex(index)
        self._fill_year()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(10)

        self.title_bar = WindowTitleBar(self.close, self.showMinimized)
        main_layout.addLayout(self.title_bar)

        header_row = QHBoxLayout()
        self.title_label = QLabel("تعطیلات رسمی")
        # Year stepper buttons (older year on the right, like the calendar's
        # month arrows); the combo alone lists only years that have data.
        self.prev_year_btn = QPushButton("❯")
        self.prev_year_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_year_btn.clicked.connect(self._go_to_prev_year)
        self.next_year_btn = QPushButton("❮")
        self.next_year_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_year_btn.clicked.connect(self._go_to_next_year)
        # Plain combo; the dropdown renders without dead space thanks to the
        # vertical component in center_combo_items' item alignment.
        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self._fill_year)
        header_row.addWidget(self.title_label)
        header_row.addStretch()
        header_row.addWidget(self.prev_year_btn)
        header_row.addWidget(self.year_combo)
        header_row.addWidget(self.next_year_btn)
        main_layout.addLayout(header_row)

        self.count_label = QLabel("")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.count_label)

        self.list_container = QWidget()
        self.rows_layout = QVBoxLayout(self.list_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area, 1)

        self.empty_label = QLabel("داده‌ای برای نمایش وجود ندارد.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.empty_label)

        self._populate_years()
        self._fill_year()

    # --- data ---

    def _populate_years(self):
        """List every year with data plus the current year, opening on today.

        The current year is always inserted even when the holiday store has
        no data for it yet, so the viewer opens on "now" instead of on the
        newest year that happens to be in the file."""
        current_year = jdatetime.date.today().year
        years = sorted(set(self.holidays_cache.keys()) | {current_year}, reverse=True)
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in years:
            self.year_combo.addItem(to_persian_digits(year), year)
        center_combo_items(self.year_combo)
        self.year_combo.setCurrentIndex(years.index(current_year))
        self.year_combo.blockSignals(False)

    def _current_year(self) -> Optional[int]:
        return self.year_combo.currentData() if self.year_combo.count() else None

    def _go_to_prev_year(self):
        """Step to the next older year in the combo (right-hand «❯» button)."""
        index = self.year_combo.currentIndex() + 1
        if index < self.year_combo.count():
            self.year_combo.setCurrentIndex(index)

    def _go_to_next_year(self):
        """Step to the next newer year in the combo (left-hand «❮» button)."""
        index = self.year_combo.currentIndex() - 1
        if index >= 0:
            self.year_combo.setCurrentIndex(index)

    def _update_year_nav(self):
        """Dim the stepper buttons at either end of the year list."""
        at_newest = self.year_combo.currentIndex() <= 0
        at_oldest = self.year_combo.currentIndex() >= self.year_combo.count() - 1
        self.next_year_btn.setEnabled(not at_newest)
        self.prev_year_btn.setEnabled(not at_oldest)

    def _fill_year(self, *_args):
        """Rebuild the grouped month/row list for the selected year."""
        # The stepper state depends only on the combo position, so it must be
        # refreshed before any early return for data-less years.
        self._update_year_nav()
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        year = self._current_year()
        year_holidays = self.holidays_cache.get(year, {}) if year is not None else {}
        has_data = bool(year_holidays)
        self.scroll_area.setVisible(has_data)
        self.empty_label.setVisible(not has_data)
        if not has_data:
            self.count_label.setText("")
            return

        self.count_label.setText(
            f"{to_persian_digits(len(year_holidays))} روز تعطیل در سال {to_persian_digits(year)}")

        for month in range(1, 13):
            month_days = sorted((md, descs) for md, descs in year_holidays.items() if md[0] == month)
            if not month_days:
                continue
            month_header = QLabel(
                f"{persian_month_name(month)} - {to_persian_digits(len(month_days))} تعطیلی")
            month_header.setObjectName("MonthHeader")
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, month_header)

            for (month_no, day), descriptions in month_days:
                text = "، ".join(descriptions)
                row_label = QLabel(f"{to_persian_digits(day)} {persian_month_name(month_no)} - {text}")
                row_label.setObjectName("HolidayRow")
                row_label.setWordWrap(True)
                self.rows_layout.insertWidget(self.rows_layout.count() - 1, row_label)

        self._restyle_dynamic_children()

    # --- styling ---

    def _restyle_dynamic_children(self):
        palette = APP_CONFIG.get_current_palette()
        for child in self.list_container.findChildren(QLabel):
            if child.objectName() == "MonthHeader":
                child.setStyleSheet(
                    f"color: {palette['ACCENT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
                    f"font-size: 15px; font-weight: bold; background: transparent; border: none;")
            elif child.objectName() == "HolidayRow":
                child.setStyleSheet(
                    f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
                    f"font-size: 13px; background: transparent; border: none; padding: 0 8px;")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.title_bar.update_styles()
        self.title_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        self.count_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        self.year_combo.setStyleSheet(combo_stylesheet(palette, padding="4px 12px", center_text=True))
        self.year_combo.setFixedHeight(36)
        # QSS fonts land after Qt's sizeHint: without a measured minimum the
        # four Persian digits do not fit and the year shows as ellipses.
        fit_combo_width(self.year_combo)
        # The steppers read as real buttons (filled chip, accent on hover)
        # instead of bare glyphs floating next to the year combo; disabled
        # keeps the shape but fades, signalling the end of the year range.
        nav_style = (
            f"QPushButton {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {palette['ACCENT_COLOR']}; color: {palette['ACCENT_COLOR']}; }}"
            f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}"
            f"QPushButton:disabled {{ background-color: transparent; color: {palette['GREY_COLOR']}; border-color: {palette['CALENDAR_BORDER_COLOR']}; }}")
        for button in (self.prev_year_btn, self.next_year_btn):
            button.setStyleSheet(nav_style)
            button.setFixedSize(32, 36)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; }" + scrollbar_stylesheet(palette))
        self.list_container.setStyleSheet("background: transparent;")
        self.empty_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 15px; font-weight: bold; background: transparent;")
        self._restyle_dynamic_children()
