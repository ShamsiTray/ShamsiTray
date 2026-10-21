"""
Holiday Viewer Window
---------------------

`HolidayViewerWindow` is a read-only browser for the loaded holiday data,
opened from the tray menu («مشاهده تعطیلات»). Holidays are shown for one
Jalali year at a time (selectable, defaulting to the current year), grouped
under Persian month headers as badge rows: a day badge carrying the weekday,
the title with an optional muted inline lunar date, and — only in the current
year — the next upcoming holiday tinted, every upcoming row tagged with a countdown
(«امروز» / «فردا» / «۲۳ روز دیگر» / «۱ ماه و ۴ روز دیگر»; the nearest tag filled,
the rest muted) while past rows dim. The year can also be stepped with «❯» / «❮» buttons flanking
the combo box.

The data comes straight from the in-memory holiday cache the calendar uses,
so what is shown here is exactly what the calendar highlights; updated data
pulled by the auto-updater appears here the next time the window is opened.
"""
import re
from html import escape
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from config import APP_CONFIG
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.date_utils import (describe_date_distance, persian_month_name,
                              persian_weekday_name, to_persian_digits)
from utils.logger import setup_logging
from utils.ui_helpers import (ReservedRailScrollArea, SCROLL_BOTTOM_PAD_PX,
                              center_combo_items, combo_stylesheet,
                              fit_combo_width, scrollbar_stylesheet)
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

# Holiday descriptions conventionally carry their lunar date in brackets
# («تاسوعای حسینی [ ۹ محرم ]»); the row renders that muted, inline after the
# title it belongs to.
_LUNAR_RE = re.compile(r"\s*\[\s*(.+?)\s*\]")


# Qt rich text has no inline margin, so the extra gap before the lunar date is
# a no-break space set in a tiny font: a space is ~0.25em wide, so 6px is ~1.5px.
_LUNAR_GAP_FONT_PX = 6

# Space above a month's hairline, so the last row of the previous month doesn't touch it.
MONTH_GAP_ABOVE_LINE_PX = 8


def split_lunar_date(text: str) -> Tuple[str, str]:
    """Split «تاسوعای حسینی [ ۹ محرم ]» into ("تاسوعای حسینی", "۹ محرم")."""
    subs = [m.strip() for m in _LUNAR_RE.findall(text)]
    return _LUNAR_RE.sub("", text).strip(), " · ".join(subs)


def format_countdown(target, today) -> str:
    """Friendly «time until» wording for a holiday row.

    امروز / فردا / پس‌فردا for the first three days, plain days while less than a
    whole month away («۲۳ روز دیگر»), and calendar units after that
    («۱ ماه و ۴ روز دیگر», «۳ ماه دیگر»). Jalali months are 29-31 days long, so
    the split comes from ``describe_date_distance`` rather than dividing by 30.
    """
    distance = describe_date_distance(target, today=today)
    total = distance.total_days
    if total == 0:
        return "امروز"
    if total == 1:
        return "فردا"
    if total == 2:
        return "پس‌فردا"
    if distance.has_calendar_units:
        parts = [f"{to_persian_digits(count)} {unit}" for count, unit in
                 ((distance.years, "سال"), (distance.months, "ماه"), (distance.days, "روز"))
                 if count]
        return f"{' و '.join(parts)} دیگر"
    return f"{to_persian_digits(total)} روز دیگر"


def _rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class HolidayMonthHeader(QWidget):
    """Month name with a small count pill, separated from the previous month by a hairline."""

    def __init__(self, name: str, count: int, first: bool):
        super().__init__()
        self.setObjectName("MonthHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # let QSS draw the hairline
        self.setProperty("first", first)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0 if first else 10, 6, 2)
        lay.setSpacing(8)
        self.name_label = QLabel(name)
        self.name_label.setObjectName("MonthName")
        self.count_label = QLabel(to_persian_digits(count))
        self.count_label.setObjectName("MonthCount")
        lay.addWidget(self.name_label)
        lay.addWidget(self.count_label)
        lay.addStretch(1)


class HolidayRowWidget(QFrame):
    """One holiday: day badge (number + full weekday), title line(s) — each
    with its lunar date inline and muted — and optional tag."""

    def __init__(self, day: int, weekday: Optional[int], title: str,
                 tag: str = "", is_past: bool = False, is_next: bool = False):
        super().__init__()
        self.setObjectName("HolidayRow")
        self.setProperty("next", is_next)
        self.is_past = is_past
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(10)

        self.badge = QFrame()
        self.badge.setObjectName("DayBadge")
        self.badge.setProperty("friday", weekday == 6)
        self.badge.setFixedSize(64, 44)
        badge_lay = QVBoxLayout(self.badge)
        badge_lay.setContentsMargins(0, 3, 0, 3)
        badge_lay.setSpacing(0)
        self.day_label = QLabel(to_persian_digits(day))
        self.day_label.setObjectName("DayNum")
        self.day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_lay.addWidget(self.day_label)
        self.weekday_label = QLabel(persian_weekday_name(weekday) if weekday is not None else "")
        self.weekday_label.setObjectName("DayName")
        self.weekday_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_lay.addWidget(self.weekday_label)
        lay.addWidget(self.badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("RowTitle")
        self.title_label.setWordWrap(True)
        # The title arrives as muted spans joined with <br> (see _fill_year);
        # the payload can start with plain text, so the format is set
        # explicitly instead of left to auto-detection.
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        text_col.addWidget(self.title_label)
        lay.addLayout(text_col, 1)

        self.tag_label = None
        if tag:
            self.tag_label = QLabel(tag)
            self.tag_label.setObjectName("RowTag")
            lay.addWidget(self.tag_label, 0, Qt.AlignmentFlag.AlignVCenter)

        if is_past:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(0.45)
            self.setGraphicsEffect(effect)


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

        Applying the new cache in place keeps an open viewer from showing stale
        data after a live holiday auto-update. The currently browsed year is
        restored when the new data still offers it.
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
        # The scrollbar's rail hangs in the left padding band instead of the
        # margin line the header rows keep (the constraint is owned by the
        # manager's main_layout comment); content compensation is the same
        # trailing addSpacing there.
        main_layout.setContentsMargins(8, 14, 18, 14)
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
        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self._fill_year)
        header_row.addWidget(self.title_label)
        header_row.addStretch()
        header_row.addWidget(self.prev_year_btn)
        header_row.addWidget(self.year_combo)
        header_row.addWidget(self.next_year_btn)
        header_row.addSpacing(10)           # back to the header's 18px margin line
        main_layout.addLayout(header_row)

        self.count_label = QLabel("")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.count_label)
        self._next_row: Optional[QWidget] = None
        self._next_header: Optional[QWidget] = None
        self._summary: Optional[Tuple[int, int, int]] = None

        self.list_container = QWidget()
        self.rows_layout = QVBoxLayout(self.list_container)
        # The rail sits out at the glass (8px padding band, like the
        # manager's list) and keeps the same gutter inside it; the bottom
        # pad pairs with the scrollbar's track margin (SCROLL_BOTTOM_PAD_PX)
        # so the thumb ends at the last card.
        self.rows_layout.setContentsMargins(8, 0, 0, SCROLL_BOTTOM_PAD_PX)
        self.rows_layout.setSpacing(1)
        self.rows_layout.addStretch(1)

        self.scroll_area = ReservedRailScrollArea()
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
        # Whenever the nearest upcoming holiday lives in a later year (this
        # year's are used up, or it has no data at all), open there so the
        # viewer lands on it with its countdown instead of on a dimmed or empty
        # list. With nothing upcoming anywhere it opens on "now".
        default_year = current_year
        upcoming = self._find_next_holiday()
        if upcoming is not None and upcoming[0] != current_year:
            default_year = upcoming[0]
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in years:
            self.year_combo.addItem(to_persian_digits(year), year)
        center_combo_items(self.year_combo)
        self.year_combo.setCurrentIndex(years.index(default_year))
        self.year_combo.blockSignals(False)

    def _find_next_holiday(self) -> Optional[Tuple[int, Tuple[int, int]]]:
        """(year, (month, day)) of the first holiday dated today or later,
        searching this year and every later year in the cache; None if none."""
        today = jdatetime.date.today()
        for year in sorted(y for y in self.holidays_cache if y >= today.year):
            for md in sorted(self.holidays_cache[year]):
                date = self._safe_date(year, md)
                if date is not None and date >= today:
                    return year, md
        return None

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
            self._summary = None
            return

        today = jdatetime.date.today()
        is_current = year == today.year
        dates = {md: self._safe_date(year, md) for md in year_holidays}
        # The highlighted "next" holiday is the nearest one overall, so it can
        # sit in a later year than the current one once this year is used up.
        nearest = self._find_next_holiday()
        next_md = nearest[1] if nearest is not None and nearest[0] == year else None
        fridays = sum(1 for d in dates.values() if d is not None and d.weekday() == 6)
        self._summary = (len(year_holidays), year, fridays)
        self._update_summary()

        self._next_row = None
        self._next_header = None
        first = True
        for month in range(1, 13):
            month_days = sorted((md, descs) for md, descs in year_holidays.items() if md[0] == month)
            if not month_days:
                continue
            header = HolidayMonthHeader(persian_month_name(month), len(month_days), first)
            if not first:
                # Air between the previous month's last row and the hairline
                # (the line is the header's own top border, so the gap has to
                # be a separate spacer ahead of it).
                self.rows_layout.insertSpacing(self.rows_layout.count() - 1, MONTH_GAP_ABOVE_LINE_PX)
            first = False
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, header)

            for (month_no, day), descriptions in month_days:
                date = dates[(month_no, day)]
                parts = [split_lunar_date(d) for d in descriptions]
                # Every row reads the same way: one line per holiday, its
                # lunar date (if any) trailing the title muted and 11px, so
                # single- and multi-holiday days share one presentation. The
                # tone shift plus a hairline gap (_LUNAR_GAP_FONT_PX) separates
                # it from the title — no separator glyph.
                muted = APP_CONFIG.get_current_palette()["GREY_COLOR"]
                title = "<br>".join(
                    escape(t) + (f' <span style="font-size:{_LUNAR_GAP_FONT_PX}px;">&nbsp;</span>'
                                 f'<span style="color:{muted}; font-size:11px;">'
                                 f'{escape(x)}</span>' if x else "")
                    for t, x in parts) or "<br>".join(escape(d) for d in descriptions)
                is_next = (month_no, day) == next_md
                # Every upcoming holiday of the current year carries its
                # countdown; the nearest one's tag is filled (see the QSS),
                # the rest stay muted. Past rows get none, and other years only
                # tag the nearest holiday overall when it falls in them.
                tag = ""
                if date is not None and date >= today and (is_current or is_next):
                    tag = format_countdown(date, today)
                row = HolidayRowWidget(
                    day, date.weekday() if date is not None else None, title, tag,
                    is_past=is_current and date is not None and date < today,
                    is_next=is_next)
                if is_next:
                    self._next_row = row
                    self._next_header = header
                self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)

        self._restyle_dynamic_children()
        self.scroll_area.verticalScrollBar().setValue(0)
        if self._next_row is not None:
            QTimer.singleShot(0, self._scroll_to_next)

    @staticmethod
    def _safe_date(year: int, md: Tuple[int, int]):
        try:
            return jdatetime.date(year, md[0], md[1])
        except ValueError:
            return None

    def _scroll_to_next(self):
        """Bring the next upcoming holiday into view with its month header above it."""
        try:
            if self._next_row is not None:
                # Make sure the freshly added rows have their final geometry
                # before reading positions, then start exactly on the month
                # header of the next holiday (not a fixed offset above the row,
                # which showed the previous month's tail when the row was not
                # the first of its month).
                self.list_container.layout().activate()
                target = self._next_header if self._next_header is not None else self._next_row
                # Skip the header's top margin: that band holds the month's
                # hairline, and the view should start on the month name itself.
                skip = target.layout().contentsMargins().top() if target.layout() else 0
                self.scroll_area.verticalScrollBar().setValue(max(0, target.y() + skip))
        except RuntimeError:  # row was deleted by a rebuild before the timer fired
            pass

    def _update_summary(self):
        if not self._summary:
            return
        count, year, fridays = self._summary
        accent = APP_CONFIG.get_current_palette()["ACCENT_COLOR"]
        rlm = "\u200f"
        text = (f"<b style='color:{accent}'>{to_persian_digits(count)}</b> روز تعطیل در سال "
                f"{to_persian_digits(year)}{rlm}")
        if fridays:
            text += (f" &nbsp;|&nbsp; <b style='color:{accent}'>{to_persian_digits(fridays)}</b>"
                     f" مورد در جمعه")
        self.count_label.setText(text)

    # --- styling ---

    def _restyle_dynamic_children(self):
        p = APP_CONFIG.get_current_palette()
        font = APP_CONFIG.FONT_FAMILY
        accent, holiday = p["ACCENT_COLOR"], p["HOLIDAY_COLOR"]
        is_dark = QColor(p["BACKGROUND_COLOR"]).lightness() < 128
        hover = "rgba(255, 255, 255, 0.05)" if is_dark else "rgba(0, 0, 0, 0.04)"
        self.list_container.setStyleSheet(f"""
            QWidget {{ background: transparent; font-family: '{font}'; }}
            QFrame#HolidayRow {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
            QFrame#HolidayRow:hover {{ background: {hover}; }}
            QFrame#HolidayRow[next="true"] {{ background: {_rgba(accent, 0.14)}; border: 1px solid {accent}; }}
            QFrame#DayBadge {{ background: {p['CALENDAR_BORDER_COLOR']}; border: none; border-radius: 9px; }}
            QFrame#DayBadge[friday="true"] {{ background: {_rgba(holiday, 0.16)}; }}
            QLabel#DayNum {{ color: {p['TEXT_COLOR']}; font-size: 16px; font-weight: bold; }}
            QLabel#DayName {{ color: {p['WEEKDAY_NAMES_COLOR']}; font-size: 10px; }}
            QFrame#DayBadge[friday="true"] QLabel {{ color: {holiday}; }}
            QLabel#RowTitle {{ color: {p['TEXT_COLOR']}; font-size: 13px; }}
            QLabel#RowTag {{ background: {p['CALENDAR_BORDER_COLOR']}; color: {p['GREY_COLOR']}; border-radius: 9px; padding: 1px 9px; font-size: 11px; font-weight: bold; }}
            QFrame#HolidayRow[next="true"] QLabel#RowTag {{ background: {accent}; color: #ffffff; }}
            QWidget#MonthHeader {{ border-top: 1px solid {p['CALENDAR_BORDER_COLOR']}; }}
            QWidget#MonthHeader[first="true"] {{ border-top: none; }}
            QLabel#MonthName {{ color: {accent}; font-size: 15px; font-weight: bold; }}
            QLabel#MonthCount {{ background: {_rgba(accent, 0.16)}; color: {accent}; border-radius: 9px; padding: 0 9px; font-size: 11px; font-weight: bold; }}
        """)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.title_bar.update_styles()
        self.title_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        self.count_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; background: transparent; border: none;")
        self._update_summary()
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
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; }"
                                       + scrollbar_stylesheet(palette,
                                                              bottom_margin=SCROLL_BOTTOM_PAD_PX))
        self.list_container.setStyleSheet("background: transparent;")
        self.empty_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 15px; font-weight: bold; background: transparent;")
        self._restyle_dynamic_children()
