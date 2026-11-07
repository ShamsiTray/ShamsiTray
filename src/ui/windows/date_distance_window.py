"""
Date Distance Window
--------------------

`DateDistanceWindow`, the «فاصله دو تاریخ» tool: the gap between two
arbitrary dates, in either calendar. The caption row's `CalendarSwitch` picks
Jalali (the default) or Gregorian; each calendar owns its own pair of
`DateSelectorRow`s («از تاریخ» / «تا تاریخ») and switching carries the two
dates across (the same two days, so the day total never changes - only the
years/months/days split does, since the month lengths differ).

Layout, top to bottom: the caption row (close/minimize, and the switch at the
far edge), the two rows with their fields in numeric-date order (year, month,
day from the left edge; months numbered «۰۶ - شهریور» like the converter and
go-to-date), and one result card. The card leads with the day total as its hero
line, then - under a hairline - the calendar breakdown, the same span in whole
months, and the whole-weeks reading. Each is only shown when it says something
the lines above do not: the breakdown needs a month or a year
(``has_calendar_units``), the months line needs a year (``has_month_total``;
without one it would repeat the breakdown), the weeks line needs a whole week
(``has_full_weeks``).

Every result line is a copy target: a click copies the sentence shown (in Latin
digits, the app-wide copy convention) and flashes the app-wide «✓ کپی شد» at the
cursor in the success tone, as the converter's rows do. One «کپی همه» glyph is
pinned inside the card's top-right corner (the RTL reading-start corner) and
copies every line the card currently shows as one clipboard block, shown and
hidden with the results.

The measurement is direction-agnostic. The numbers are the absolute gap, so the
order of the two rows never changes what is shown, and the sentences come from
the shared neutral formatters (no «مانده/گذشته»: neither date is asserted to be
today, and a swapped pair measures the same distance). Equality answers
«دو تاریخ یکسان هستند.», not the converter's «تاریخ امروز است.», and is decided
by the engine's own ``is_today`` verdict, as everywhere else. An empty year is
an error like a wrong one (red border plus the range message): the measure
cannot answer without it, so it says why instead of going quiet.
"""
import datetime

import jdatetime
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QStackedWidget, QVBoxLayout, QWidget)

from config import APP_CONFIG
from ui.widgets.calendar_switch import CALENDAR_GREGORIAN, CalendarSwitch
from ui.widgets.event_input import DateSelectorRow, GregorianDateSelectorRow
from ui.widgets.tooltip import COPIED_TEXT, CustomTooltip, TooltipButton
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.date_utils import (describe_date_distance, describe_gregorian_distance,
                              format_distance_total_months, format_distance_units,
                              format_distance_weeks, from_persian_digits,
                              to_persian_digits, year_range_hint)
from utils.logger import setup_logging
from utils.ui_helpers import error_color, legible_on, mix_colors
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

# The hero number is large text: WCAG asks 3:1 of it (4.5:1 is for body text).
HERO_MIN_CONTRAST = 3.0
COPIED_MESSAGE = COPIED_TEXT
# The «کپی همه» glyph is an absolute child of the result card, pinned inside
# its top-right corner - the RTL reading-start corner; this inset is the only
# number that moves it.
COPY_ALL_CORNER_INSET_PX = 10
# 32px square hit area (icon stays small), 8px radius.
COPY_ALL_BUTTON_PX = 32
COPY_ALL_BUTTON_RADIUS_PX = 8
# The copy lines' focus ring shares the button's language: an accent border
# that exists only on the :focus state, at the button's radius.
FOCUS_RING_RADIUS_PX = 8
# The distance pages span each library's true edges, not the app's support
# span (1200..1600 stays the event editor's constraint): jdatetime expresses
# Jalali 1..9377 - no Jalali year 0, and 9377 is the last year whose Gregorian
# twin stays inside datetime.date's 9999 - while the Gregorian page takes
# datetime.date's whole 1..9999. A held date with no twin in the other
# calendar (a Gregorian date before Jalali year 1, say) is not forbidden; the
# flip restarts that row from today like any out-of-span carry.
JALALI_YEAR_MIN, JALALI_YEAR_MAX = 1, 9377
GREGORIAN_YEAR_MIN, GREGORIAN_YEAR_MAX = 1, 9999


class DistanceRowMetrics:
    """The distance rows borrow the converter's field look - 40px fields and a
    regular 14px caption - instead of the event editor's compact defaults.

    Attribute-only: the shared ``DateSelectorRow`` render path reads these
    knobs, so this mixin carries the override without inheriting anything."""

    FIELD_HEIGHT_PX = 40
    ROW_LABEL_SIZE_PX = 14
    ROW_LABEL_BOLD = False


class DistanceJalaliRow(DistanceRowMetrics, DateSelectorRow):
    """«از تاریخ» / «تا تاریخ» row: Jalali months, Persian digits."""

    YEAR_MIN = JALALI_YEAR_MIN
    YEAR_MAX = JALALI_YEAR_MAX


class DistanceGregorianRow(DistanceRowMetrics, GregorianDateSelectorRow):
    """The same row with English months and Latin digits."""

    YEAR_MIN = GREGORIAN_YEAR_MIN
    YEAR_MAX = GREGORIAN_YEAR_MAX


def copy_with_flash(text: str, at: QPoint | None = None) -> None:
    """Put ``text`` on the clipboard and flash the app-wide «✓ کپی شد» at
    ``at``: the converter's copy rows confirm a click the same way, so a mouse
    caller leaves ``at`` at the cursor, while a keyboard activation passes the
    widget it was launched from.

    The clipboard gets Latin digits, not the Persian digits on screen: that is
    the app-wide copy convention (the calendar's «کپی تاریخ» and the converter
    both copy Latin), so a result pastes the same wherever it was copied from.
    """
    if not text:
        return
    QApplication.clipboard().setText(from_persian_digits(text))
    anchor = at if at is not None else QCursor.pos()
    CustomTooltip.instance().flash_copied(anchor)


class CopyLabel(QLabel):
    """A result line that copies its own text: clicked, or tabbed to and
    launched with Enter or Space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            copy_with_flash(self.text())
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            copy_with_flash(self.text(), self.mapToGlobal(self.rect().center()))
        else:
            super().keyPressEvent(event)


class CopyRow(QWidget):
    """The hero line: the number and its unit are two labels (two sizes), but
    one copy target - clicked, or tabbed to and launched with Enter or Space -
    that copies them as the sentence they form. Clicks on the child labels
    bubble up here because a plain QLabel ignores them."""

    def __init__(self, days_label: QLabel, unit_label: QLabel, parent=None):
        super().__init__(parent)
        # The name is the hover sheet's styling hook; the attribute is the
        # styled-background opt-in a custom QWidget subclass owes before any
        # stylesheet background paints (only an exact-QWidget literal draws
        # one without it).
        self.setObjectName("CopyRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.days_label, self.unit_label = days_label, unit_label
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        row = QHBoxLayout(self)
        # The hover pill's inset around the 58px sentence: the band paints the
        # row's whole rect, so the breathing room must come from the layout's
        # margins - QSS padding cannot inset a widget's layout the way it
        # insets a QLabel's text. The vertical pair is deliberately uneven
        # (top +10 on the bottom): the ink rides ~5px above a centered rect's
        # center, so equal margins would leave 10px more air under the
        # baseline than over the caps.
        row.setContentsMargins(10, 12, 10, 2)
        row.setSpacing(8)
        row.addWidget(days_label, alignment=Qt.AlignmentFlag.AlignBaseline)
        row.addWidget(unit_label, alignment=Qt.AlignmentFlag.AlignBaseline)

    def copy_text(self) -> str:
        days = self.days_label.text()
        return f"{days} {self.unit_label.text()}" if days else ""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            copy_with_flash(self.copy_text())
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            copy_with_flash(self.copy_text(), self.mapToGlobal(self.rect().center()))
        else:
            super().keyPressEvent(event)


class ResultCard(QFrame):
    """The result card. Its «کپی همه» control is an absolute child pinned
    inside the top-right corner (the RTL reading-start corner), so the control
    costs the layout nothing; one resizeEvent reposition keeps it there."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.corner_button = None

    def attach_corner_button(self, button):
        self.corner_button = button
        button.setParent(self)
        self._place_corner_button()

    def _place_corner_button(self):
        if self.corner_button is not None:
            self.corner_button.move(self.width() - self.corner_button.width()
                                    - COPY_ALL_CORNER_INSET_PX,
                                    COPY_ALL_CORNER_INSET_PX)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_corner_button()


class DateDistanceWindow(BaseFramelessWindow):
    """A tool window measuring the distance between two picked dates."""
    TASKBAR_ICON = True  # show in the taskbar so a minimized window is reachable
    # A form: a picked field must stop reading as held once the user moves on
    # to the result card, where no click can move the focus ring away itself.
    CLEAR_FOCUS_ON_BLANK_CLICK = True
    # The result block is static (nothing wraps), so the window is a fixed size.
    # A slot of 64px for the hero cell is the floor: the 58px Vazirmatn line box
    # (90px: ascent 59 + descent 31) must NOT be squeezed under the label's
    # rect, or the digit tops flat-cut at that rect - a cut the hover band's
    # top edge rides along (substitute-font metrics hid this until the band).
    # 380 gave the hero 48px; 404 gives it 64 (ink clearance 7px, row hint 98
    # per layout scan at both platforms' matching 90px metrics).
    # addStretch keeps whatever remains centered.
    WINDOW_WIDTH = 440
    INITIAL_HEIGHT = 404

    def __init__(self):
        super().__init__()
        self.setWindowTitle("فاصله دو تاریخ")
        self.setFixedSize(self.WINDOW_WIDTH, self.INITIAL_HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 22)
        main_layout.setSpacing(12)

        main_layout.addLayout(self._create_title_bar())

        # «از تاریخ» is the measure's origin and «تا تاریخ» its target; the
        # count is the absolute gap, so which row is which only labels them.
        # One pair of rows per calendar, stacked: the switch flips the page.
        def make_pair(row_class):
            options = dict(ltr_date_order=True, numbered_months=True, flag_empty_year=True)
            return (row_class(label_text="از تاریخ", **options),
                    row_class(label_text="تا تاریخ", **options))

        self.from_row, self.to_row = make_pair(DistanceJalaliRow)
        self.greg_from_row, self.greg_to_row = make_pair(DistanceGregorianRow)
        self.rows_stack = QStackedWidget()
        for pair in ((self.from_row, self.to_row), (self.greg_from_row, self.greg_to_row)):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(10)
            for row in pair:
                page_layout.addWidget(row)
            self.rows_stack.addWidget(page)
        main_layout.addWidget(self.rows_stack)

        # --- result card ---
        self.result_card = ResultCard()
        self.result_card.setObjectName("DistanceCard")
        card_layout = QVBoxLayout(self.result_card)
        card_layout.setContentsMargins(18, 12, 18, 12)
        card_layout.setSpacing(4)
        card_layout.addStretch(1)
        center = Qt.AlignmentFlag.AlignHCenter

        # The range message lives in the card, where the result would be: while
        # it shows there is no result to push around. A window-level verdict
        # and not a mixin hint label, because two rows sharing one external
        # label would hide it the moment the healthy row clears its own state.
        self.year_hint_label = QLabel("")
        self.year_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.year_hint_label.hide()
        card_layout.addWidget(self.year_hint_label)

        self.result_days = QLabel("")
        self.result_unit = QLabel("")
        # «کپی همه»: the card's one control for the whole answer, an absolute
        # child of the card corner (see ResultCard) so it costs the layout
        # nothing. It is always parented before being shown - a parentless
        # show() would flash the glyph as a stray top-level window for the
        # frames before the window opens - and the states with no result offer
        # no copy: shown beside the results (_recompute), hidden in
        # _reset_result, so the first open starts hidden.
        self.copy_all_button = TooltipButton(APP_CONFIG.FAS.FA_COPY)
        self.copy_all_button.setToolTip("کپی همه")
        self.copy_all_button.setAccessibleName("کپی همه")
        self.copy_all_button.setFixedSize(COPY_ALL_BUTTON_PX, COPY_ALL_BUTTON_PX)
        self.copy_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_all_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.copy_all_button.clicked.connect(self._copy_all)
        self.result_card.attach_corner_button(self.copy_all_button)
        self.hero_row = CopyRow(self.result_days, self.result_unit)
        card_layout.addWidget(self.hero_row, alignment=center)
        self.result_message = QLabel("")
        self.result_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_message.hide()
        card_layout.addWidget(self.result_message)

        self.result_divider = QFrame()
        self.result_divider.setFixedHeight(1)
        card_layout.addSpacing(4)
        card_layout.addWidget(self.result_divider)
        card_layout.addSpacing(4)

        # The secondary lines, in the order they are read: calendar breakdown,
        # the same span in whole months, whole weeks. Each one is a copy target.
        self.result_breakdown = CopyLabel()
        self.result_months = CopyLabel()
        self.result_weeks = CopyLabel()
        for line in (self.result_breakdown, self.result_months, self.result_weeks):
            card_layout.addWidget(line, alignment=center)
        card_layout.addStretch(1)
        main_layout.addWidget(self.result_card, 1)

        for row in self._all_rows():
            row.changed.connect(self._recompute)
        self.calendar_switch.calendar_changed.connect(self._on_calendar_changed)
        self.from_row.set_date(jdatetime.date.today())
        self.to_row.set_date(jdatetime.date.today())
        self.greg_from_row.set_date(datetime.date.today())
        self.greg_to_row.set_date(datetime.date.today())
        # Styles come after the rows are filled: the fitted month width needs
        # the items to exist before it can measure them.
        self.update_styles()
        self._recompute()
        self._apply_windows_styles()

    # --- shared chrome (same shape as the converter) ---

    def _create_title_bar(self):
        self.title_bar = WindowTitleBar(self.close, self.showMinimized)
        # After the bar's own stretch, so the switch sits at the far edge.
        self.calendar_switch = CalendarSwitch()
        self.title_bar.addWidget(self.calendar_switch)
        return self.title_bar

    def _apply_windows_styles(self):
        apply_windows_styles(self)

    def _all_rows(self):
        return (self.from_row, self.to_row, self.greg_from_row, self.greg_to_row)

    def active_rows(self):
        """The (from, to) rows of the calendar currently chosen."""
        if self.calendar_switch.calendar == CALENDAR_GREGORIAN:
            return self.greg_from_row, self.greg_to_row
        return self.from_row, self.to_row

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.title_bar.update_styles()
        self.calendar_switch.update_styles()
        for row in self._all_rows():
            row.update_styles()
        self._equalize_field_widths()
        font = f"font-family: '{APP_CONFIG.FONT_FAMILY}';"
        plain = "background: transparent; border: none;"
        # The copy lines' :focus ring rides their own per-state clause, the
        # same rule pattern the «کپی همه» button paints its ring with.
        focus_ring = (f"border: 1px solid {palette['ACCENT_COLOR']}; "
                      f"border-radius: {FOCUS_RING_RADIUS_PX}px;")
        # One raised surface in both themes, halfway between the window and
        # the input fill. Secondary text uses the weekday-name tone (the
        # palette's legible muted colour); GREY_COLOR is too faint on the card.
        card_bg = mix_colors(palette['BACKGROUND_COLOR'], palette['INPUT_BG_COLOR'], 0.5)
        muted = palette['WEEKDAY_NAMES_COLOR']
        # The copy lines wear the converter's copy-row wash (its update_styles
        # owns the recipe): a hover affordance on the lines that copy, and
        # nothing on the message or the year hint, which copy nothing.
        is_dark = QColor(palette['BACKGROUND_COLOR']).lightness() < 128
        hover = "rgba(255, 255, 255, 0.05)" if is_dark else "rgba(0, 0, 0, 0.04)"
        self.result_card.setStyleSheet(
            f"QFrame#DistanceCard {{ background-color: {card_bg}; "
            f"border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 18px; }}")
        self.year_hint_label.setStyleSheet(
            f"color: {error_color(palette)}; {font} font-size: 16px; font-weight: bold; {plain}")
        self.result_days.setStyleSheet(
            f"color: {legible_on(palette['ACCENT_COLOR'], card_bg)}; {font} "
            f"font-size: 58px; font-weight: bold; {plain}")
        self.result_unit.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; {font} font-size: 22px; font-weight: bold; {plain}")
        # One band over the whole sentence, not half-washes behind each label:
        # the children keep their inert sheets and the pointer lights the row
        # from either one (hover walks the widget chain, as the manager's and
        # viewer's rows already rely on).
        self.hero_row.setStyleSheet(
            "QWidget#CopyRow { border-radius: 6px; background: transparent; }"
            f"QWidget#CopyRow:hover {{ background: {hover}; }}"
            f"QWidget#CopyRow:focus {{ {focus_ring} }}")
        self.result_message.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; {font} font-size: 20px; font-weight: bold; {plain}")
        self.result_divider.setStyleSheet(
            f"background-color: {palette['CALENDAR_BORDER_COLOR']}; border: none;")
        # The secondary lines are standalone pills like the converter's elapsed
        # span: their AlignHCenter shrink-wrap already keeps the wash to one
        # line's shape, so the padding is just the band's own text inset.
        self.result_breakdown.setStyleSheet(
            f"CopyLabel {{ color: {palette['TEXT_COLOR']}; {font} font-size: 16px; "
            f"font-weight: bold; {plain} border-radius: 6px; padding: 2px 6px; }}"
            f"CopyLabel:hover {{ background: {hover}; }}"
            f"CopyLabel:focus {{ {focus_ring} }}")
        self.result_months.setStyleSheet(
            f"CopyLabel {{ color: {palette['TEXT_COLOR']}; {font} font-size: 14px; "
            f"{plain} border-radius: 6px; padding: 2px 6px; }}"
            f"CopyLabel:hover {{ background: {hover}; }}"
            f"CopyLabel:focus {{ {focus_ring} }}")
        self.result_weeks.setStyleSheet(
            f"CopyLabel {{ color: {muted}; {font} font-size: 13px; "
            f"{plain} border-radius: 6px; padding: 2px 6px; }}"
            f"CopyLabel:hover {{ background: {hover}; }}"
            f"CopyLabel:focus {{ {focus_ring} }}")
        # The button's text is a Font Awesome glyph, so it carries that family:
        # the card's text font (Vazirmatn) lacks U+F0C5, and the glyph fallback
        # search for it walks legacy raster fonts (Fixedsys and friends), each
        # logging a DirectWrite failure through QPA.
        # Same look as the title bar's minimize/close buttons (transparent,
        # hairline border, 8px radius, hover wash) so the window has one
        # button language; the icon is the same small size, not a heavy glyph.
        self.copy_all_button.setStyleSheet(
            f"QPushButton {{ color: {palette['TEXT_COLOR']}; "
            f"font-family: '{APP_CONFIG.FONT_AWESOME_FAMILY}'; font-size: 13px; "
            f"border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; "
            f"border-radius: {COPY_ALL_BUTTON_RADIUS_PX}px; background-color: transparent; }}"
            f"QPushButton:hover {{ background-color: {palette['HOVER_BG']}; }}"
            f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}"
            f"QPushButton:focus {{ border: 1px solid {palette['ACCENT_COLOR']}; }}")
        self._equalize_field_widths()

    def _equalize_field_widths(self):
        """One month width for both pages: the two calendars' widest labels
        («۰۶ - شهریور» vs «09 September») fit to different minimums, and the
        ltr row turns the month fit into the day box's share of the slack -
        so different fits read as the field columns jumping sideways on the
        flip. Each row's own fit has just run, so the wider one binds both
        pages (the day boxes equalize through it, with nothing to set); the
        shorter page gains a few pixels of padding instead."""
        fitted = {row.month_combo.minimumWidth() for row in self._all_rows()}
        if not fitted:
            return
        width = max(fitted)
        for row in self._all_rows():
            row.month_combo.setFixedWidth(width)
            row.month_combo.view().setMinimumWidth(width)

    # --- calendar switch ---

    def _on_calendar_changed(self, calendar: str):
        """Carry the two dates across (the same days in the other calendar) and
        flip the rows page. A row that holds no valid date, or whose date falls
        outside the target calendar's span - or cannot exist in it at all (a
        Gregorian date before Jalali year 1 has no Jalali twin) - restarts
        from today."""
        if calendar == CALENDAR_GREGORIAN:
            pairs = ((self.from_row, self.greg_from_row), (self.to_row, self.greg_to_row))
            convert = lambda date: date.togregorian()  # noqa: E731
            today = datetime.date.today()
        else:
            pairs = ((self.greg_from_row, self.from_row), (self.greg_to_row, self.to_row))
            convert = lambda date: jdatetime.date.fromgregorian(date=date)  # noqa: E731
            today = jdatetime.date.today()
        for source, target in pairs:
            picked = source.picked()
            try:
                carried = convert(picked) if picked is not None else None
            except ValueError:
                carried = None  # no twin: jdatetime has no Jalali year 0 to carry into
            lo, hi = target._year_bounds()
            target.set_date(carried if carried is not None and lo <= carried.year <= hi else today)
        self.rows_stack.setCurrentIndex(1 if calendar == CALENDAR_GREGORIAN else 0)
        self._recompute()

    # --- result ---

    def _recompute(self, *_args):
        """Re-answer from the active rows: live on every dimension change."""
        gregorian = self.calendar_switch.calendar == CALENDAR_GREGORIAN
        first_row, second_row = self.active_rows()
        out_of_range = first_row._year_is_out_of_range() or second_row._year_is_out_of_range()
        if out_of_range:
            self.year_hint_label.setText(year_range_hint(*first_row._year_bounds(),
                                                         persian_digits=not gregorian))
        else:
            self.year_hint_label.setText("")
        self.year_hint_label.setVisible(out_of_range)
        self._reset_result()

        first, second = first_row.picked(), second_row.picked()
        if first is None or second is None:
            return

        describe = describe_gregorian_distance if gregorian else describe_date_distance
        distance = describe(second, today=first)
        if distance.is_today:
            self.result_message.setText("دو تاریخ یکسان هستند.")
            self.result_message.show()
            return

        self.result_days.setText(to_persian_digits(abs(distance.total_days)))
        self.result_unit.setText("روز")
        self.hero_row.show()
        self.copy_all_button.show()
        # Each secondary line is shown only when it adds something the lines
        # above do not already say.
        if distance.has_calendar_units:
            self.result_breakdown.setText(format_distance_units(distance))
        if distance.has_month_total:
            self.result_months.setText(format_distance_total_months(distance))
        if distance.has_full_weeks:
            self.result_weeks.setText(format_distance_weeks(distance))
        for line in (self.result_breakdown, self.result_months, self.result_weeks):
            line.setVisible(bool(line.text()))
        self.result_divider.setVisible(any(line.text() for line in
                                           (self.result_breakdown, self.result_months,
                                            self.result_weeks)))

    def _reset_result(self):
        for label in (self.result_days, self.result_unit, self.result_message,
                      self.result_breakdown, self.result_months, self.result_weeks):
            label.setText("")
        self.hero_row.hide()
        self.copy_all_button.hide()
        self.result_message.hide()
        for line in (self.result_breakdown, self.result_months, self.result_weeks):
            line.hide()
        self.result_divider.hide()

    def _copy_all(self):
        """The whole answer on one clipboard: every result line the card
        currently shows, hero first, empty (hidden) lines skipped."""
        copy_with_flash("\n".join(t for t in (
            self.hero_row.copy_text(), self.result_breakdown.text(),
            self.result_months.text(), self.result_weeks.text()) if t))
