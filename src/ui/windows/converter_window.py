"""
Date Converter Window
---------------------

This module provides the `DateConverterWindow`, a tool for converting dates
between Jalali (Shamsi) and Gregorian calendars. It features input validation,
dynamic day/month population, and calculates elapsed time from the present.
"""
import datetime

import jdatetime
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QColor, QFont, QPalette, QRegularExpressionValidator, QCursor
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout,
                            QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QVBoxLayout, QWidget, QGraphicsOpacityEffect)

from config import APP_CONFIG
from ui.widgets.calendar_switch import CALENDAR_JALALI, CalendarSwitch
from utils.date_utils import (describe_date_distance, format_distance_breakdown,
                              format_distance_units, format_gregorian_long,
                              format_gregorian_numeric, format_jalali_long,
                              format_jalali_numeric, from_persian_digits,
                              to_persian_digits, is_gregorian_leap_year,
                              is_jalali_leap_year, days_in_jalali_month,
                              days_in_gregorian_month, validate_year_range,
                              gregorian_weekday_name, persian_weekday_name)
from utils.logger import setup_logging
from utils.ui_helpers import (DigitsFirstCombo, YearRangeValidationMixin,
                              accent_button_stylesheet, combo_stylesheet)
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from .base_window import BaseFramelessWindow
from ui.widgets.tooltip import CustomTooltip

logger = setup_logging(__name__)

class DateConverterWindow(YearRangeValidationMixin, BaseFramelessWindow):
    """A window for converting dates between Jalali and Gregorian calendars."""
    # The Jalali max rides the app's supported calendar range; the min stays
    # 1 on purpose: the converter is open to years the calendar UI never shows
    # (the popup's go-to-date span is 1200..1600), so only the max reads from
    # APP_CONFIG and a widening of the supported range widens the converter.
    MIN_JALALI_YEAR, MAX_JALALI_YEAR = 1, APP_CONFIG.SUPPORTED_MAX_YEAR
    # 623 is intentional (owner decision): the Gregorian input floor stays at
    # 623 even though Jalali year 1 technically begins on 622-03-21. Kept at
    # 623 on purpose - do not "fix" this back to 622 without asking.
    MIN_GREGORIAN_YEAR, MAX_GREGORIAN_YEAR = 623, 2200
    # The «نوع تبدیل» column left this much width; the three field columns
    # need ~390 and the pill bar ~280, so the window fits tightly at 470.
    WINDOW_WIDTH = 470
    TASKBAR_ICON = True  # show in the taskbar so a minimized window is reachable

    def __init__(self):
        super().__init__()
        self._initial_height = 220
        self.setWindowTitle("تبدیل تاریخ")
        self.setFixedSize(self.WINDOW_WIDTH, self._initial_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # Label identity -> clipboard payload, rebuilt by _display_results on
        # every conversion. Keyed by id() because the rows are created once and
        # never reparented, so their identity is stable for the window's life.
        self._copy_payloads: dict = {}

        self._setup_ui()
        self.update_styles()
        self._connect_signals()

        self._initialize_date_inputs()
        self._apply_windows_styles()

    def _input_is_jalali(self) -> bool:
        """The pill's verdict: which calendar the input row speaks."""
        return self.calendar_switch.calendar == CALENDAR_JALALI

    def _current_year_bounds(self):
        """(min, max) year for the active input mode (jalali vs gregorian)."""
        if self._input_is_jalali():
            return self.MIN_JALALI_YEAR, self.MAX_JALALI_YEAR
        return self.MIN_GREGORIAN_YEAR, self.MAX_GREGORIAN_YEAR

    # --- YearRangeValidationMixin host hooks ---

    def _year_bounds(self):
        return self._current_year_bounds()

    def _year_hint_text(self) -> str:
        """Live range message for the active mode: while the typed year is out
        of range, the error strip stays up and says what to enter - the red
        border alone left the user guessing."""
        lo, hi = self._current_year_bounds()
        if self._input_is_jalali():
            return f"سال شمسی باید بین {to_persian_digits(lo)} و {to_persian_digits(hi)} باشد."
        return f"سال میلادی باید بین {lo} و {hi} باشد."

    def _year_style_kwargs(self, errored: bool) -> dict:
        return {"center_text": True}

    def _update_convert_state(self, *_args):
        """Grey the تبدیل button in and out with the input's submittability.

        Driven by textChanged and the conversion-mode combo (plus one initial
        call), it covers every case the out-of-range flip cannot see: the empty
        state never changes the mixin's error state, so without this the button
        would stay enabled after clearing the field. The shared accent style dims
        disabled buttons.
        """
        self.convert_button.setEnabled(self._year_is_submittable())

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
        self.title_bar = WindowTitleBar(self.close, self.showMinimized)
        # Same seat as the distance window's switch: added after the bar's own
        # stretch, so the pill sits at the far edge in both windows.
        self.calendar_switch = CalendarSwitch()
        self.title_bar.addWidget(self.calendar_switch)
        return self.title_bar

    def _create_input_section(self) -> QHBoxLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(5)

        self.day_combo = QComboBox()
        # «۰۶ - شهریور» mixes digits with Persian text, which is bidi-ambiguous:
        # DigitsFirstCombo pins the digits-first order on every platform.
        self.month_combo = DigitsFirstCombo()
        self.year_input = QLineEdit()
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        regex = QRegularExpression("^[0-9۰-۹]{0,4}$")
        validator = QRegularExpressionValidator(regex)
        self.year_input.setValidator(validator)

        grid.addWidget(self.day_combo, 0, 0)
        grid.addWidget(self.month_combo, 0, 1)
        grid.addWidget(self.year_input, 0, 2)
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

        self.gregorian_date_value_1 = QLabel("...")
        self.gregorian_date_value_2 = QLabel("...")
        self.jalali_date_value_1 = QLabel("...")
        self.jalali_date_value_2 = QLabel("...")
        self.gregorian_weekday_label = QLabel("...")
        self.jalali_weekday_label = QLabel("...")

        for lbl in [self.gregorian_date_value_1, self.gregorian_date_value_2,
                self.jalali_date_value_1, self.jalali_date_value_2,
                self.gregorian_weekday_label, self.jalali_weekday_label]:
            self._make_copy_row(lbl)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        # The two calendars sit side by side, each in its own field card:
        # the stacked blocks lined six result lines up and read as one pile,
        # while bare columns were text on the flat fill with nothing to read
        # against - the same failure the viewer's summary chip fixed. The
        # weekday rides its own last line because the full long form is too
        # wide for two columns at this window's width.
        def result_card(title_text: str, value_a: QLabel, value_b: QLabel,
                        weekday: QLabel) -> QWidget:
            card = QWidget()
            # A named QWidget subclass paints no stylesheet background without
            # this attribute (the OverlayBlocker pixel lesson).
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setObjectName("ResultCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 6, 10, 8)
            card_layout.setSpacing(3)
            title = QLabel(title_text)
            title.setObjectName("OutputTitleLabel")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(title)
            card_layout.addWidget(value_a)
            card_layout.addWidget(value_b)
            card_layout.addWidget(weekday)
            return card

        self.gregorian_card = result_card(
            "تاریخ میلادی", self.gregorian_date_value_1,
            self.gregorian_date_value_2, self.gregorian_weekday_label)
        self.jalali_card = result_card(
            "تاریخ شمسی", self.jalali_date_value_1, self.jalali_date_value_2,
            self.jalali_weekday_label)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(12)
        # First added sits on the right edge under the window's RTL, the seat
        # the original two-column grid gave the Gregorian column.
        cards_row.addWidget(self.gregorian_card)
        cards_row.addWidget(self.jalali_card)
        layout.addLayout(cards_row)

        layout.addSpacing(10)

        self.elapsed_text = QLabel("...")
        # A copy row like the date values; its payload and cursor are
        # stamped per conversion (_update_elapsed_time), so «تاریخ امروز
        # است.» can opt the line out of copying.
        self._make_copy_row(self.elapsed_text)
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
        widget_palette = self.palette()
        palette = APP_CONFIG.get_current_palette()
        widget_palette.setColor(QPalette.ColorRole.WindowText, QColor(palette['TEXT_COLOR']))
        widget_palette.setColor(QPalette.ColorRole.Text, QColor(palette['TEXT_COLOR']))
        self.setPalette(widget_palette)
        for label in self.findChildren(QLabel):
            if not label.objectName():
                label.setStyleSheet(f"color: {palette['TEXT_COLOR']};")

        input_field_height = 40

        combo_style = combo_stylesheet(palette, center_text=True)
        self.title_bar.update_styles()
        self.calendar_switch.update_styles()
        self.day_combo.setFixedSize(80, input_field_height)
        self.month_combo.setFixedSize(140, input_field_height)
        for combo in [self.day_combo, self.month_combo]:
            combo.setStyleSheet(combo_style)
        self.year_input.setFixedSize(100, input_field_height)
        self._apply_year_style()
        self.convert_button.setFixedHeight(50)
        self.convert_button.setStyleSheet(accent_button_stylesheet(palette, padding="0px 18px", font_size=16))
        self.middle_divider.setStyleSheet(f"color: {palette['CALENDAR_BORDER_COLOR']};")
        for label in self.output_widget.findChildren(QLabel):
            if label.objectName() == "OutputTitleLabel":
                 label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 16, QFont.Weight.Bold))
                 label.setStyleSheet(f"color: {palette['ACCENT_COLOR']}; padding: 5px;")
        self.jalali_date_value_1.setFont(QFont(APP_CONFIG.FONT_FAMILY, 15, QFont.Weight.Bold))
        self.jalali_date_value_2.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
        self.gregorian_date_value_1.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 15, QFont.Weight.Bold))
        self.gregorian_date_value_2.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 14))
        # The weekday is the card's muted footnote line; the cards themselves
        # share the surface language of the form fields and the holiday
        # viewer's summary chip.
        for card in (self.gregorian_card, self.jalali_card):
            card.setStyleSheet(f"background: {palette['INPUT_BG_COLOR']};"
                               f" border: 1px solid {palette['CALENDAR_BORDER_COLOR']};"
                               f" border-radius: 10px;")
        self.gregorian_weekday_label.setFont(QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY, 12))
        self.jalali_weekday_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        for weekday_label in (self.gregorian_weekday_label,
                              self.jalali_weekday_label):
            weekday_label.setStyleSheet(f"color: {palette['WEEKDAY_NAMES_COLOR']};")
        self.elapsed_text.setFont(QFont(APP_CONFIG.FONT_FAMILY, 14))
        self.leap_year_status.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.status_message.setStyleSheet("color: red; font-weight: bold; font-size: 18px;")

    def _connect_signals(self):
        self.calendar_switch.calendar_changed.connect(self._on_calendar_changed)
        self.month_combo.currentIndexChanged.connect(self._update_day_dropdown)
        self.year_input.textChanged.connect(self._update_day_dropdown)
        self.year_input.textChanged.connect(self._update_year_error_state)
        self.day_combo.currentIndexChanged.connect(self._clear_results)
        self.month_combo.currentIndexChanged.connect(self._clear_results)
        self.year_input.textChanged.connect(self._clear_results)
        self.convert_button.clicked.connect(self._convert_date)
        # Enter goes through the BUTTON, not straight to _convert_date: a disabled
        # تبدیل then swallows the key on an empty or invalid year exactly like a
        # click would. _convert_date keeps its own guard for other callers.
        self.year_input.returnPressed.connect(self.convert_button.click)
        # The bounds are mode-dependent (_year_bounds defers to the switch), so
        # the button follows them automatically. Only the year text needs a
        # signal today: a calendar flip refills the field with today's date,
        # which is inside both ranges, so it never needs a separate re-derivation.
        self.year_input.textChanged.connect(self._update_convert_state)
        # Derive it once up front too, so the window never opens with a stale
        # button state.
        self._update_convert_state()
        self.day_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.month_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.year_input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    def _make_copy_row(self, label: QLabel):
        """Route a result label's left click through _copy_to_clipboard."""
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(False)
        label.mousePressEvent = (lambda event, label=label: self._copy_to_clipboard(label) if event.button() == Qt.MouseButton.LeftButton else None)

    def _copy_to_clipboard(self, label: QLabel):
        """Copy the row's clipboard payload and show a brief confirmation.

        The payload is the Latin-digit form from the shared formatters, not the
        Persian-digit text on screen; an unmapped label falls back to its own
        text so nothing silently copies nothing.
        """
        text = self._copy_payloads.get(id(label), label.text())
        if text and text != "...":
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            global_pos = QCursor.pos()
            CustomTooltip.instance().flash_tooltip("کپی شد", global_pos)

    def _apply_windows_styles(self):
        apply_windows_styles(self)

    def _initialize_date_inputs(self): self._on_calendar_changed()
    def _on_calendar_changed(self):
        self._clear_results()
        is_jalali_input = self._input_is_jalali()
        today = jdatetime.date.today() if is_jalali_input else datetime.date.today()
        if is_jalali_input:
            self.year_input.setText(to_persian_digits(str(today.year)))
            months = [f"{to_persian_digits(str(i+1).zfill(2))} - {name}" for i, name in enumerate(APP_CONFIG.PERSIAN_MONTHS)]
            self.day_combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.year_input.setText(str(today.year))
            months = [f"{i+1:02d} - {name}" for i, name in enumerate(APP_CONFIG.GREGORIAN_MONTHS)]
            self.day_combo.view().setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self._set_combo_items(self.month_combo, months)
        self.month_combo.setCurrentIndex(today.month - 1)
        self._update_day_dropdown()
        day_str_to_set = to_persian_digits(today.day) if is_jalali_input else str(today.day)
        if self.day_combo.findText(day_str_to_set) != -1:
            self.day_combo.setCurrentText(day_str_to_set)

        # The bounds changed with the mode; re-evaluate the year border now.
        self._update_year_error_state()

    def _update_day_dropdown(self, *args):
        """
        Rebuilds the day dropdown based on selected year, month, and calendar type.
        Preserves the currently selected day when possible.
        """
        current_day_text = self.day_combo.currentText()
        is_jalali_input = self._input_is_jalali()
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
            return days_in_jalali_month(year, month)
        return days_in_gregorian_month(year, month)

    def _clear_results(self, *args):
        self._hide_results()
        # While the year is out of range, KEEP the range message on screen -
        # every input change clears the results strip, and without this the
        # "what would a valid year look like" text vanished the moment the user
        # started fixing the year.
        if self._year_is_out_of_range():
            self._show_error(self._year_hint_text())

    def _hide_results(self):
        if self.status_message.isVisible():
            self.status_message.clear()
            self.status_message.hide()

        if self.output_widget.isVisible():
            self.output_widget.hide()
            self.middle_divider.hide()

        if self.height() != self._initial_height:
            self.setFixedSize(self.WINDOW_WIDTH, self._initial_height)

    def _show_error(self, message: str):
        self._hide_results()
        self.status_message.setText(message)
        self.status_message.show()
        new_height = self._initial_height + self.status_message.sizeHint().height() + 20
        self.setFixedSize(self.WINDOW_WIDTH, new_height)


    def _convert_date(self):
        """
        Validates input, performs calendar conversion, and updates the UI.
        All validation is done BEFORE creating date objects to prevent invalid states.
        """
        self._clear_results()
        is_jalali_input = self._input_is_jalali()

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
                error = validate_year_range(year, self.MIN_JALALI_YEAR, self.MAX_JALALI_YEAR, is_jalali=True)
                if error:
                    self._show_error(error)
                    return
                j_date = jdatetime.date(year, month, day)
                g_date = j_date.togregorian()
            else:
                error = validate_year_range(year, self.MIN_GREGORIAN_YEAR, self.MAX_GREGORIAN_YEAR, is_jalali=False)
                if error:
                    self._show_error(error)
                    return
                g_date = datetime.date(year, month, day)
                j_date = jdatetime.date.fromgregorian(date=g_date)

            self._display_results(j_date, g_date, is_jalali_input)
        except (ValueError, TypeError) as e:
            self._show_error("تاریخ ورودی نامعتبر است.")
            logger.warning(f"Date conversion failed: {e}")

    def _display_results(self, j_date: jdatetime.date, g_date: datetime.date, is_jalali_input: bool):
        self.jalali_date_value_1.setText(to_persian_digits(j_date.strftime("%Y/%m/%d")))
        self.jalali_date_value_2.setText(format_jalali_long(j_date, with_weekday=False))
        self.jalali_weekday_label.setText(persian_weekday_name(j_date.weekday()))
        self.gregorian_date_value_1.setText(g_date.strftime("%Y-%m-%d"))
        # The date part comes from the shared formatter, not strftime: %A/%B
        # follow the process locale, so the same line showed Persian names on
        # a Persian Windows install (the format_gregorian_long docstring).
        self.gregorian_date_value_2.setText(
            format_gregorian_long(g_date, persian_digits=False, with_weekday=False))
        self.gregorian_weekday_label.setText(gregorian_weekday_name(g_date.weekday()))
        # What each row puts on the clipboard, keyed by label identity and
        # rebuilt on every conversion: the labels show Persian digits, so
        # copying label.text() gave the user a date in a different numeral
        # system than the calendar's «کپی تاریخ» menu produces for the same day.
        # The payloads come from the shared formatters so both surfaces agree;
        # the weekday rows copy the names they display.
        self._copy_payloads = {
            id(self.jalali_date_value_1): format_jalali_numeric(j_date),
            id(self.jalali_date_value_2): format_jalali_long(j_date, persian_digits=False),
            id(self.jalali_weekday_label): persian_weekday_name(j_date.weekday()),
            id(self.gregorian_date_value_1): format_gregorian_numeric(j_date),
            id(self.gregorian_date_value_2): format_gregorian_long(g_date, persian_digits=False),
            id(self.gregorian_weekday_label): gregorian_weekday_name(g_date.weekday()),
        }

        self._update_elapsed_time(g_date)
        input_year = j_date.year if is_jalali_input else g_date.year
        is_leap = is_jalali_leap_year(input_year) if is_jalali_input else is_gregorian_leap_year(input_year)
        calendar_name = "شمسی" if is_jalali_input else "میلادی"
        self.leap_year_status.setText(f"سال {calendar_name} {to_persian_digits(input_year)} یک سال {'کبیسه است' if is_leap else 'کبیسه نیست'}")
        self.leap_year_status_opacity_effect.setOpacity(1.0 if is_leap else 0.5)
        self.middle_divider.show()
        self.output_widget.show()
        # The window follows the results' own measured height instead of a
        # guessed constant: a height cut wrong either way reads broken - the
        # last line on the floor when tight, dead space when generous.
        self.layout().activate()
        height = max(self._initial_height, self.layout().totalMinimumSize().height())
        self.setFixedSize(self.WINDOW_WIDTH, height)

    def _update_elapsed_time(self, target_date: datetime.date):
        """Show the gap between the converted date and today.

        The breakdown is Jalali, not Gregorian: this is a Persian calendar, and
        «۲ سال و ۲ ماه» means two Jalali years to the user reading it. That also
        means the line matches the calendar's own «فاصله تا امروز» notice, since
        both go through the shared date-distance helper.

        The line joins the copy rows: clicking it copies the span alone - the
        direction-free units the distance window's breakdown row shows - in
        Latin digits, and today's «تاریخ امروز است.» nothing, with the cursor
        dropping to the arrow to say so.
        """
        distance = describe_date_distance(
            jdatetime.date.fromgregorian(date=target_date))
        if distance.is_today:
            self.elapsed_text.setText("تاریخ امروز است.")
            self.elapsed_text.setCursor(Qt.CursorShape.ArrowCursor)
            # _copy_to_clipboard falls back to label.text() on a missing key,
            # so "nothing to copy" is a stamped-empty payload, not an absent one.
            self._copy_payloads[id(self.elapsed_text)] = ""
            return
        self.elapsed_text.setText(f"فاصله زمانی: {format_distance_breakdown(distance)}")
        self.elapsed_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_payloads[id(self.elapsed_text)] = from_persian_digits(
            format_distance_units(distance))
