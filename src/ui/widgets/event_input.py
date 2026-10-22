"""
Event Input Widget
------------------

This module provides `EventInputWidget`, an overlay panel used within the
calendar window and the event manager for adding or editing user events.
It includes a text area, a recurrence selector (one-time / monthly / yearly),
an auto-delete checkbox for one-time events, plus save/cancel buttons.

The event's date is picked through `DateSelectorRow`, the shared
year/month/day row the module owns: the event manager's «افزودن رویداد»
flow shows it (where the event date is not inherited from a clicked
calendar cell) and so does its edit flow, prefilled with the event's real
anchor date. It is hidden for the calendar so that flow behaves exactly
as before. The year is a text input (Persian or Latin digits) rather than
a bounded dropdown, so the flow keeps working no matter how far ahead the
user plans.

The module also owns the shared recurrence wording: ``recurrence_label`` and
the ``delete_confirmation_message`` built from it, which the calendar's
date-level card and the event manager's per-row dialog both ask.
"""
import datetime
import jdatetime
from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import QColor, QPainter, QRegularExpressionValidator, QTextOption
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from config import APP_CONFIG
from utils.date_utils import (days_in_gregorian_month, days_in_jalali_month,
                              from_persian_digits, to_persian_digits, year_range_hint)
from utils.event_io import (RECURRENCE_MONTHLY, RECURRENCE_NONE, RECURRENCE_YEARLY,
                            recurrence_of_key)
from utils.ui_helpers import (DigitsFirstCombo, YearRangeValidationMixin,
                              accent_button_stylesheet, center_combo_items,
                              combo_stylesheet, danger_button_stylesheet,
                              fit_combo_width)
from .checkbox import CustomCheckbox

# Combo index <-> recurrence mode mapping (kept explicit for signal safety).
_RECURRENCE_VALUES = (RECURRENCE_NONE, RECURRENCE_MONTHLY, RECURRENCE_YEARLY)
_RECURRENCE_LABELS = ("بدون تکرار", "ماهانه", "سالانه")

# One-time events are only useful inside the range the calendar UI can reach
# (the go-to-date popup allows the same span, read from APP_CONFIG like this
# module), so the typed year is bounded to that range instead of accepting
# unreachable outliers like 3213.
MIN_EVENT_YEAR = APP_CONFIG.SUPPORTED_MIN_YEAR
MAX_EVENT_YEAR = APP_CONFIG.SUPPORTED_MAX_YEAR
# Shown next to the year field whenever the typed year leaves that range:
# the red border says "wrong", this label says what "right" is (one shared
# template lives in date_utils so the surfaces cannot drift apart).
YEAR_RANGE_HINT = year_range_hint(MIN_EVENT_YEAR, MAX_EVENT_YEAR)
# A Jalali year starts in the Gregorian year this much later (1405 begins in
# 2026), so the Gregorian row spans the same supported stretch of history.
JALALI_TO_GREGORIAN_YEAR_OFFSET = 621


def recurrence_label(mode: str) -> str:
    """Persian label for a recurrence mode."""
    return _RECURRENCE_LABELS[_RECURRENCE_VALUES.index(mode)] if mode in _RECURRENCE_VALUES else _RECURRENCE_LABELS[0]


def _join_fa(items: list) -> str:
    """Persian list wording: «الف، ب و ج» (no separator before the last item)."""
    if len(items) <= 1:
        return items[0] if items else ""
    return "، ".join(items[:-1]) + " و " + items[-1]


def delete_confirmation_message(keys: Iterable[str]) -> str:
    """The delete ask for ``keys`` - every key the answer would remove.

    A date-level delete covers every entry sharing that visible date and a
    recurring key covers every occurrence of its series, so the wording cannot
    be read off the single event the card previews: a monthly event would ask
    like a one-off deletion and its other occurrences would go unmentioned.
    Both surfaces ask from the same key model here (beside the recurrence
    labels it reuses), so the calendar's date-level card and the event
    manager's per-row card cannot drift into saying different things.
    """
    keys = list(keys)
    modes = [recurrence_of_key(key) for key in keys]
    if len(modes) <= 1:
        if not modes or modes[0] == RECURRENCE_NONE:
            return "این رویداد حذف شود؟"
        return (f"این رویداد تکرارشونده {recurrence_label(modes[0])} است و تمام "
                "تکرارهای آن حذف خواهند شد. آیا مطمئن هستید؟")
    # Kinds in use, told apart by recurrence: a date holds at most one event per
    # mode, so the list is what the user is about to lose rather than a count
    # they cannot check.
    labels = _join_fa(list(dict.fromkeys(
        recurrence_label(mode) for mode in modes)))
    return (f"این روز {to_persian_digits(len(keys))} رویداد دارد ({labels})؛ "
            "همه حذف میشوند و تکرارهای رویدادهای تکرارشونده هم پاک میشود. "
            "آیا مطمئن هستید؟")


class RTLTextEdit(QTextEdit):
    """A QTextEdit with right-to-left layout and placeholder text support."""
    def __init__(self, placeholder_text=""):
        super().__init__()
        self.placeholder_text = placeholder_text
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.textChanged.connect(self.viewport().update)

    def paintEvent(self, event):
        super().paintEvent(event)
        # QTextEdit does not support placeholders in RTL reliably, so we manually draw it when the document is empty.
        if not self.toPlainText() and self.placeholder_text:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(128, 128, 128))
            rect = self.viewport().rect()
            rect.adjust(5, 5, -5, -5)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self.placeholder_text)

class DateSelectorRow(YearRangeValidationMixin, QWidget):
    """The Jalali year/month/day picking row, as its own widget.

    The build, the day refill and the picked-date reading live here once so
    every surface with a date selector composes the same row - and inherits
    the shared red-border year validation with it. The recurrence answers
    (which dimensions an event's key actually drops) stay with the editor;
    a surface without that layer takes the row exactly as built. When the
    red border should come with its explanation, the caller hands the mixin
    its own hint label through ``set_hint_label``: the editor keeps its
    label as a layout row of its own, and a row-owned placement would
    re-shape that overlay. ``label_text`` relabels the leading caption
    (the distance window splits two rows into «از تاریخ» / «تا تاریخ»).
    """

    changed = pyqtSignal()  # any dimension moved; the picked date may differ

    ROW_LABEL = "تاریخ:"
    # Geometry of the ``ltr_date_order`` row (the distance window): the
    # caption is fixed and the day field's width is a floor, so the day and
    # month fields share the row's remaining slack in a balanced row.
    LTR_LABEL_WIDTH_PX = 56
    LTR_DAY_WIDTH_PX = 68

    # Field metrics a composing window can tune for its own look (the compact
    # event-editor values below are the default; the distance window matches
    # the converter's taller fields and lighter caption instead).
    FIELD_HEIGHT_PX = 34
    YEAR_WIDTH_PX = 92
    ROW_LABEL_SIZE_PX = 13
    ROW_LABEL_BOLD = True

    # What differs between the Jalali row and its Gregorian subclass; the
    # build, the refill and the reading above these hooks are shared.
    YEAR_MIN = MIN_EVENT_YEAR
    YEAR_MAX = MAX_EVENT_YEAR
    MONTH_NAMES = APP_CONFIG.PERSIAN_MONTHS

    def __init__(self, parent=None, label_text: Optional[str] = None, *,
                 ltr_date_order: bool = False, numbered_months: bool = False,
                 flag_empty_year: bool = False):
        super().__init__(parent)
        # ``ltr_date_order`` lays the fields out the way a numeric date reads,
        # year, month, day from the left edge. The default keeps the editor's
        # historical order (the row mirrors under RTL, so adding order is the
        # reverse of what shows).
        self.ltr_date_order = ltr_date_order
        # ``numbered_months`` labels the months «۰۶ - شهریور» like the converter
        # and go-to-date do; the default keeps the editor's bare names.
        self.numbered_months = numbered_months
        # ``flag_empty_year`` gives an EMPTY year the same red border and hint as
        # a wrong one. The shared mixin treats empty as "not out of range" (a
        # form still being filled in); a surface that measures live answers
        # nothing for an empty year, so it must say why.
        self.flag_empty_year = flag_empty_year
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        self.row_label = QLabel(self.ROW_LABEL if label_text is None else label_text)
        self.row_label.setObjectName("DateRowLabel")
        row_layout.addWidget(self.row_label)
        # Text input rather than a dropdown: no artificial year cap.
        self.year_input = QLineEdit()
        self.year_input.setValidator(QRegularExpressionValidator(QRegularExpression("^[0-9۰-۹]{0,4}$")))
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_combo = DigitsFirstCombo() if numbered_months else QComboBox()
        self.day_combo = QComboBox()
        if ltr_date_order:
            row_layout.addWidget(self.day_combo, 1)
            row_layout.addWidget(self.month_combo, 1)
            row_layout.addWidget(self.year_input)
        else:
            row_layout.addWidget(self.year_input)
            row_layout.addWidget(self.month_combo, 1)
            row_layout.addWidget(self.day_combo, 1)

        # Only set_date turns the announcement guard off: its field writes
        # are setup, not selections (see set_date).
        self._announce = True
        # Maintenance before announcement: an emit always finds the day combo
        # refilled for the new anchor, so a listener never reads a stale day.
        self.year_input.textChanged.connect(self._on_anchor_changed)
        self.year_input.textChanged.connect(self._update_year_error_state)
        self.month_combo.currentIndexChanged.connect(self._on_anchor_changed)
        self.year_input.textChanged.connect(self._emit_changed)
        self.month_combo.currentIndexChanged.connect(self._emit_changed)
        self.day_combo.currentIndexChanged.connect(self._emit_changed)

    def _emit_changed(self, *_args):
        if self._announce:
            self.changed.emit()

    def set_date(self, anchor) -> None:
        """Show ``anchor`` as one completed selection.

        The intermediate field writes stay silent: the year lands before the
        month and day catch up, so a mid-write emission hands a listener an
        incomplete date and the later writes never announce the finished
        one. ``changed`` fires exactly once here, after the row holds the
        whole anchor.
        """
        self._announce = False
        try:
            self.year_input.setText(self._digits(anchor.year))
            self.month_combo.blockSignals(True)
            self.month_combo.clear()
            for number in range(1, 13):
                self.month_combo.addItem(self._month_label(number), number)
            center_combo_items(self.month_combo)
            self.month_combo.setCurrentIndex(anchor.month - 1)
            self.month_combo.blockSignals(False)
            self._repopulate_days(anchor.year, anchor.month, anchor.day)
        finally:
            self._announce = True
        self.changed.emit()

    def _repopulate_days(self, year: int, month: int, keep_day: int):
        """Fill the day combo with valid days for the year/month, clamping ``keep_day``."""
        max_day = self._days_in_month(year, month)
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        for day in range(1, max_day + 1):
            self.day_combo.addItem(self._digits(day), day)
        center_combo_items(self.day_combo)
        self.day_combo.setCurrentIndex(min(max(keep_day, 1), max_day) - 1)
        self.day_combo.blockSignals(False)

    def _picked_year(self) -> "int | None":
        """The typed year as an int inside the supported range, or None while
        the text is empty/incomplete/out of range."""
        text = self.year_input.text().strip()
        if not text:
            return None
        try:
            year = int(from_persian_digits(text))
        except (ValueError, TypeError):
            return None
        lo, hi = self._year_bounds()
        return year if lo <= year <= hi else None

    def picked(self):
        """The picked date, or None while any dimension is missing or invalid.

        The editor layers its own fallbacks on top (a recurring key drops the
        year, a hidden row means "no picker at all"); a whole-row consumer
        wants the strict answer.
        """
        year, month, day = (self._picked_year(), self.month_combo.currentData(), self.day_combo.currentData())
        if None in (year, month, day):
            return None
        try:
            return self._make_date(year, month, day)
        except ValueError:
            return None

    def set_hint_label(self, label) -> None:
        """Route the mixin's error explanation to a caller-owned label (its
        visibility and text still follow the red border)."""
        self.year_hint_label = label

    # --- YearRangeValidationMixin host hooks ---

    def _year_bounds(self):
        return self.YEAR_MIN, self.YEAR_MAX

    def _year_is_out_of_range(self) -> bool:
        if self.flag_empty_year and not self.year_input.text().strip():
            return True
        return super()._year_is_out_of_range()

    def _year_style_kwargs(self, errored: bool) -> dict:
        return {"padding": "4px 8px", "center_text": True}

    # --- calendar hooks (the Gregorian subclass overrides these) ---

    def _digits(self, value) -> str:
        return to_persian_digits(value)

    def _month_label(self, number: int) -> str:
        name = self.MONTH_NAMES[number - 1]
        if self.numbered_months:
            return f"{self._digits(str(number).zfill(2))} - {name}"
        return name

    def _days_in_month(self, year: int, month: int) -> int:
        return days_in_jalali_month(year, month)

    def _make_date(self, year: int, month: int, day: int):
        return jdatetime.date(year, month, day)

    def _on_anchor_changed(self, *_args):
        year = self._picked_year()
        month = self.month_combo.currentData()
        if year is None or month is None:
            return
        keep_day = self.day_combo.currentData() or 1
        self._repopulate_days(year, month, keep_day)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        label_weight = "bold" if self.ROW_LABEL_BOLD else "normal"
        self.row_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: {self.ROW_LABEL_SIZE_PX}px; font-weight: {label_weight}; "
            f"border: none; background: transparent;")
        self.year_input.setFixedHeight(self.FIELD_HEIGHT_PX)
        self.year_input.setFixedWidth(self.YEAR_WIDTH_PX)
        # _apply_year_style keeps the red error border when the typed year is
        # out of range, so the shared style goes through it instead of QSS.
        self._apply_year_style()
        for combo in (self.month_combo, self.day_combo):
            combo.setStyleSheet(combo_stylesheet(palette, padding="4px 8px", center_text=True))
            combo.setFixedHeight(self.FIELD_HEIGHT_PX)
            combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            center_combo_items(combo)
        fit_combo_width(self.month_combo)
        if self.ltr_date_order:
            self.row_label.setFixedWidth(self.LTR_LABEL_WIDTH_PX)
            # A floor, not a pin: the day field flexes next to the month
            # dropdown, so the row reads balanced - a fixed day beside the
            # month that swallowed all slack left the month's pill twice wide.
            self.day_combo.setMinimumWidth(self.LTR_DAY_WIDTH_PX)


class GregorianDateSelectorRow(DateSelectorRow):
    """The same row for Gregorian dates: English month names, Latin digits,
    Gregorian month lengths, ``datetime.date`` out, and the Gregorian span of
    the app's supported years."""
    YEAR_MIN = MIN_EVENT_YEAR + JALALI_TO_GREGORIAN_YEAR_OFFSET
    YEAR_MAX = MAX_EVENT_YEAR + JALALI_TO_GREGORIAN_YEAR_OFFSET
    MONTH_NAMES = APP_CONFIG.GREGORIAN_MONTHS

    def _digits(self, value) -> str:
        return str(value)

    def _month_label(self, number: int) -> str:
        # A numbered label is «08 - August»; the combos paint it under an RTL
        # base, which would reorder it to «August - 08». A leading left-to-right
        # mark makes the whole label one LTR run, so it reads as written.
        label = super()._month_label(number)
        return "\u200e" + label if self.numbered_months else label

    def _days_in_month(self, year: int, month: int) -> int:
        return days_in_gregorian_month(year, month)

    def _make_date(self, year: int, month: int, day: int):
        return datetime.date(year, month, day)


class EventInputWidget(QWidget):
    """An integrated widget for adding or editing a user event."""
    saved = pyqtSignal(str, str, bool)  # text, recurrence, remove_after_finish
    canceled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.title_label = QLabel("افزودن/ویرایش رویداد")
        main_layout.addWidget(self.title_label)

        # Optional date selector (event manager "add" flow); hidden by default.
        self.date_row = DateSelectorRow(parent=self)
        main_layout.addWidget(self.date_row)
        # The row owns the picked widgets; the editor keeps them under the
        # names its interface has always had, so every reader (tests included)
        # reaches the same widgets it always did.
        self.year_input = self.date_row.year_input
        self.month_combo = self.date_row.month_combo
        self.day_combo = self.date_row.day_combo
        self.date_row.hide()

        # Inline explanation for the red year border: "3213 is invalid" is
        # only useful once the user knows which years are valid.
        self.year_hint_label = QLabel(YEAR_RANGE_HINT)
        self.year_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.year_hint_label.hide()
        main_layout.addWidget(self.year_hint_label)
        self.date_row.set_hint_label(self.year_hint_label)

        self.text_edit = RTLTextEdit("رویداد خود را وارد کنید")
        text_option = QTextOption()
        text_option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        self.text_edit.document().setDefaultTextOption(text_option)
        # The editor absorbs every spare pixel of the overlay; the floor only
        # guards against a squeezed two-line minimum. The actual size comes
        # from the overlay geometry of each host window.
        self.text_edit.setMinimumHeight(44)
        main_layout.addWidget(self.text_edit, 1)

        recurrence_row = QHBoxLayout()
        recurrence_label_widget = QLabel("تکرار:")
        recurrence_label_widget.setObjectName("RecurrenceLabel")
        self.recurrence_combo = QComboBox()
        for label in _RECURRENCE_LABELS:
            self.recurrence_combo.addItem(label)
        center_combo_items(self.recurrence_combo)
        # Modes this widget must not offer; empty until a caller says otherwise.
        self._disabled_recurrences: set[str] = set()
        recurrence_row.addWidget(recurrence_label_widget)
        recurrence_row.addWidget(self.recurrence_combo)
        recurrence_row.addStretch()
        main_layout.addLayout(recurrence_row)

        self.remove_after_finish_checkbox = CustomCheckbox("حذف پس از گذشت تاریخ")
        main_layout.addWidget(self.remove_after_finish_checkbox)

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("ذخیره")
        self.cancel_button = QPushButton("لغو")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.save_button.clicked.connect(self._on_save)
        self.cancel_button.clicked.connect(self.canceled)
        self.recurrence_combo.currentIndexChanged.connect(self._on_recurrence_changed)
        self.text_edit.textChanged.connect(self._update_save_button_state)

        self.update_styles()
        self._update_save_button_state()

    # --- date selector (optional row) ---

    def set_date_selector_visible(self, visible: bool,
                                  initial_date: Optional[jdatetime.date] = None):
        """Show the date picker; reset it to ``initial_date`` (default: today).

        The event manager passes the event's own anchor here so editing an
        existing event opens with its real date instead of today.
        """
        if not visible:
            self.date_row.hide()
            # Editing an existing event drops the picker; a stale red hint from
            # a previous add attempt must not survive into that flow.
            self.date_row._set_year_error(False)
            return
        anchor = initial_date if initial_date is not None else jdatetime.date.today()
        self.date_row.set_date(anchor)
        self.date_row.show()

    def event_date(self):
        """The picked jdatetime.date, or None when the selector is hidden or
        the date is incomplete (missing/out-of-range year for one-time events).

        For monthly/yearly events the typed year is dropped when the store key
        is built, so an unusable year (greyed-out field, leftover out-of-range
        text) falls back to today for anchoring - month/day stay as picked.

        Uses ``isHidden()`` (the widget's own state) rather than ``isVisible()``:
        while the overlay parent is still hidden, ``isVisible()`` would always
        be False and the picker would look unset.
        """
        if self.date_row.isHidden():
            return None
        year, month, day = (self.date_row._picked_year(), self.month_combo.currentData(), self.day_combo.currentData())
        if year is None and self.recurrence() != RECURRENCE_NONE:
            year = jdatetime.date.today().year  # dropped by make_event_key anyway
        if None in (year, month, day):
            return None
        try:
            return jdatetime.date(year, month, day)
        except ValueError:
            return None

    def set_title(self, title: str):
        """Override the panel caption (e.g. «افزودن رویداد جدید» in add mode)."""
        self.title_label.setText(title)

    def _update_save_button_state(self):
        self.save_button.setEnabled(bool(self.text_edit.toPlainText().strip()))

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet(f"EventInputWidget {{background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 15px;}}")

        self.title_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 16px; font-weight: bold; border: none;")
        self.text_edit.setStyleSheet(
            f"QTextEdit {{color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}"
            f"QTextEdit:focus {{border-color: {palette['ACCENT_COLOR']};}}")
        self.text_edit.viewport().setStyleSheet(f"background-color: {palette['INPUT_BG_COLOR']}; border-radius: 8px")

        recurrence_label_widget = self.findChild(QLabel, "RecurrenceLabel")
        if recurrence_label_widget:
            recurrence_label_widget.setStyleSheet(
                f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.recurrence_combo.setStyleSheet(combo_stylesheet(palette, padding="4px 8px", center_text=True))
        self.recurrence_combo.setFixedHeight(34)
        self.recurrence_combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        center_combo_items(self.recurrence_combo)
        # The QSS font lands after Qt's sizeHint, so enforce a measured width
        # or the closed combo elides «بدون تکرار» to "بدو...رار".
        fit_combo_width(self.recurrence_combo)
        # Re-stamp the disabled rows so a theme switch repaints them in this
        # theme's grey rather than the one the widget was built with.
        self._apply_recurrence_item_states()

        self.date_row.update_styles()
        self.year_hint_label.setStyleSheet(
            f"color: {palette['HOLIDAY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 12px; font-weight: bold; background: transparent; border: none;")

        self.remove_after_finish_checkbox.update_visuals()

        self.cancel_button.setStyleSheet(danger_button_stylesheet(palette))
        self.save_button.setStyleSheet(accent_button_stylesheet(palette))

    def set_data(self, text, recurrence, remove_after_finish):
        """Prefill the editor. Unknown recurrence values fall back to one-time."""
        self.text_edit.setText(text)
        self.recurrence_combo.setCurrentIndex(
            _RECURRENCE_VALUES.index(recurrence) if recurrence in _RECURRENCE_VALUES else 0)
        self.remove_after_finish_checkbox.setChecked(remove_after_finish)
        # Callers set the disabled modes before or after this, so the guard runs
        # here too and the year/month/checkbox rows are then built from the mode
        # that actually survives.
        self._select_enabled_recurrence()
        self._on_recurrence_changed()

    def recurrence(self) -> str:
        """The selected recurrence mode.

        An index of -1 (every item disabled) reads as one-time rather than
        indexing the tuple from the end, which would silently pick yearly.
        """
        index = self.recurrence_combo.currentIndex()
        if 0 <= index < len(_RECURRENCE_VALUES):
            return _RECURRENCE_VALUES[index]
        return RECURRENCE_NONE

    def set_disabled_recurrences(self, taken) -> None:
        """Grey out the recurrence modes that are already used on this date.

        A date can hold only one event per mode, so a mode already taken there
        would silently replace the existing event instead of adding one. The
        labels stay listed and readable, dimmed: the mode is a real choice this
        date already spent, not a hidden one.
        """
        self._disabled_recurrences = set(taken)
        self._apply_recurrence_item_states()

    def _apply_recurrence_item_states(self) -> None:
        """Paint each mode from ``_disabled_recurrences`` and keep the selection usable.

        The combo draws its popup straight from the model, so the disabled look
        has to be item data - ``combo_stylesheet`` has no ``::item:disabled``
        rule, and a row stays grey even while the enabled rows take the theme's
        text colour. Called from ``update_styles()`` too, so a theme switch
        repaints the dimmed rows in that theme's grey.
        """
        muted = QColor(APP_CONFIG.get_current_palette()["GREY_COLOR"])
        model = self.recurrence_combo.model()
        for index, mode in enumerate(_RECURRENCE_VALUES):
            item = model.item(index)
            if item is None:
                continue
            enabled = mode not in self._disabled_recurrences
            item.setEnabled(enabled)
            item.setData(None if enabled else muted, Qt.ItemDataRole.ForegroundRole)
        self._select_enabled_recurrence()

    def _select_enabled_recurrence(self) -> None:
        """Never leave the combo sitting on a mode this widget refuses.

        «بدون تکرار» is row 0, so the add path - which prefills one-time - would
        otherwise open on a disabled row whenever the date already holds a
        one-time event, and hand that disabled mode back on save.
        """
        combo = self.recurrence_combo
        current = combo.currentIndex()
        if current >= 0 and combo.model().item(current).isEnabled():
            return
        for index, mode in enumerate(_RECURRENCE_VALUES):
            if mode not in self._disabled_recurrences:
                combo.setCurrentIndex(index)
                return
        # Nothing is selectable, so there is no row to move to. Callers refuse
        # to open the add editor at all in that state; leaving the selection
        # alone beats showing an empty combo.

    def _on_recurrence_changed(self, *_args):
        mode = self.recurrence()
        # Recurring events repeat forever, so auto-delete only makes sense for one-time events.
        is_one_time = mode == RECURRENCE_NONE
        self.remove_after_finish_checkbox.setEnabled(is_one_time)
        if not is_one_time:
            self.remove_after_finish_checkbox.setChecked(False)
        # The checkbox draws itself, so the grey-out needs an explicit restyle.
        self.remove_after_finish_checkbox.update_visuals()
        # Monthly keys anchor to the day only and yearly keys to month/day, so
        # the dimensions the key drops are greyed out instead of letting the
        # user pick values that would silently be discarded:
        # - monthly («هر ماه، روز ۵»): no year AND no month -> both disabled
        # - yearly («هر سال، ۵ مرداد»): no year -> only the year disabled
        # The shared QSS :disabled rules supply the muted fill/text/border.
        self.year_input.setEnabled(is_one_time)
        monthly = mode == RECURRENCE_MONTHLY
        self.month_combo.setEnabled(not monthly)
        self.date_row._apply_year_style()

    def _on_save(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        # In the manager's add flow a one-time event needs a complete in-range
        # date; an out-of-range year gets the red error border and blocks the
        # save so an unreachable event (e.g. year 3213) can never be created.
        if self.date_row.isVisible() and self.event_date() is None:
            self.date_row._set_year_error(self.date_row._year_is_out_of_range())
            self.year_input.setFocus()
            return
        self.saved.emit(text, self.recurrence(), self.remove_after_finish_checkbox.isChecked())
