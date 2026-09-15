"""
Event Input Widget
------------------

This module provides `EventInputWidget`, an overlay panel used within the
calendar window and the event manager for adding or editing user events.
It includes a text area, a recurrence selector (one-time / monthly / yearly),
an auto-delete checkbox for one-time events, plus save/cancel buttons.

An optional date-selector row (year input / month / day combos) can be shown
for the event manager's «افزودن رویداد» flow, where the event date is not
inherited from a clicked calendar cell. It is hidden for the calendar and
for regular edits so those flows behave exactly as before. The year is a
text input (Persian or Latin digits) rather than a bounded dropdown, so the
flow keeps working no matter how far ahead the user plans.
"""
import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import QColor, QPainter, QRegularExpressionValidator, QTextOption
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from config import APP_CONFIG
from utils.date_utils import days_in_jalali_month, from_persian_digits, to_persian_digits
from utils.event_io import RECURRENCE_MONTHLY, RECURRENCE_NONE, RECURRENCE_YEARLY
from utils.ui_helpers import (accent_button_stylesheet, center_combo_items,
                              combo_stylesheet, danger_button_stylesheet,
                              error_line_edit_stylesheet, fit_combo_width,
                              line_edit_stylesheet)
from .checkbox import CustomCheckbox

# Combo index <-> recurrence mode mapping (kept explicit for signal safety).
_RECURRENCE_VALUES = (RECURRENCE_NONE, RECURRENCE_MONTHLY, RECURRENCE_YEARLY)
_RECURRENCE_LABELS = ("بدون تکرار", "ماهانه", "سالانه")

# One-time events are only useful inside the range the calendar UI can reach
# (the go-to-date popup allows 1200..1600), so the typed year is bounded to
# the same range instead of accepting unreachable outliers like 3213.
MIN_EVENT_YEAR = 1200
MAX_EVENT_YEAR = 1600
# Shown next to the year field whenever the typed year leaves that range:
# the red border says "wrong", this label says what "right" is.
YEAR_RANGE_HINT = f"سال باید بین {to_persian_digits(MIN_EVENT_YEAR)} و {to_persian_digits(MAX_EVENT_YEAR)} باشد"


def recurrence_label(mode: str) -> str:
    """Persian label for a recurrence mode."""
    return _RECURRENCE_LABELS[_RECURRENCE_VALUES.index(mode)] if mode in _RECURRENCE_VALUES else _RECURRENCE_LABELS[0]


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
        self.date_row = QWidget(self)
        date_layout = QHBoxLayout(self.date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(6)
        date_label = QLabel("تاریخ:")
        date_label.setObjectName("DateRowLabel")
        date_layout.addWidget(date_label)
        # A text input instead of a year dropdown: no artificial ±10-year cap,
        # and typing 1407 is faster than scrolling a list.
        self.year_input = QLineEdit()
        self.year_input.setValidator(QRegularExpressionValidator(QRegularExpression("^[0-9۰-۹]{0,4}$")))
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_combo = QComboBox()
        self.day_combo = QComboBox()
        date_layout.addWidget(self.year_input)
        date_layout.addWidget(self.month_combo, 1)
        date_layout.addWidget(self.day_combo, 1)
        self.date_row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.date_row.hide()
        main_layout.addWidget(self.date_row)

        # Inline explanation for the red year border: "3213 is invalid" is
        # only useful once the user knows which years are valid.
        self.year_hint_label = QLabel(YEAR_RANGE_HINT)
        self.year_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.year_hint_label.hide()
        main_layout.addWidget(self.year_hint_label)

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
        # Plain combo with a measured minimum width (fit_combo_width below):
        # the same configuration as the date converter, whose dropdown the
        # user confirmed renders without dead space. AdjustToContents was
        # removed everywhere for that reason.
        for label in _RECURRENCE_LABELS:
            self.recurrence_combo.addItem(label)
        center_combo_items(self.recurrence_combo)
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
        self.year_input.textChanged.connect(self._on_date_anchor_changed)
        self.year_input.textChanged.connect(self._update_year_error_state)
        self.month_combo.currentIndexChanged.connect(self._on_date_anchor_changed)

        self._year_error = False  # live flag: typed year is complete but out of range
        self.update_styles()
        self._update_save_button_state()

    # --- date selector (optional row) ---

    def set_date_selector_visible(self, visible: bool):
        """Show the date picker (manager add-flow) and reset it to today."""
        if not visible:
            self.date_row.hide()
            # Editing an existing event drops the picker; a stale red hint from
            # a previous add attempt must not survive into that flow.
            self._set_year_error(False)
            return
        today = jdatetime.date.today()
        self.year_input.setText(to_persian_digits(today.year))

        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        for i, name in enumerate(APP_CONFIG.PERSIAN_MONTHS, start=1):
            self.month_combo.addItem(name, i)
        center_combo_items(self.month_combo)
        self.month_combo.setCurrentIndex(today.month - 1)
        self.month_combo.blockSignals(False)

        self._repopulate_days(today.year, today.month, today.day)
        self.date_row.show()

    def _repopulate_days(self, year: int, month: int, keep_day: int):
        """Fill the day combo with valid days for the year/month, clamping ``keep_day``."""
        max_day = days_in_jalali_month(year, month)
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        for day in range(1, max_day + 1):
            self.day_combo.addItem(to_persian_digits(day), day)
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
        return year if MIN_EVENT_YEAR <= year <= MAX_EVENT_YEAR else None

    def _year_is_out_of_range(self) -> bool:
        """True when the text forms a complete year but outside the supported
        range (e.g. 3213) - the case that deserves a visible error."""
        text = self.year_input.text().strip()
        if not text:
            return False
        try:
            year = int(from_persian_digits(text))
        except (ValueError, TypeError):
            return False
        return not (MIN_EVENT_YEAR <= year <= MAX_EVENT_YEAR)

    def _update_year_error_state(self, *_args):
        """Keep the red 'invalid year' border in sync with the typed text."""
        self._set_year_error(self._year_is_out_of_range())

    def _set_year_error(self, errored: bool):
        if self._year_error == errored:
            return
        self._year_error = errored
        self._apply_year_style()
        self.year_hint_label.setVisible(errored)

    def _apply_year_style(self):
        """Style the year input, switching to the shared error look when flagged."""
        palette = APP_CONFIG.get_current_palette()
        style = (error_line_edit_stylesheet(palette, padding="4px 8px", center_text=True)
                 if self._year_error
                 else line_edit_stylesheet(palette, padding="4px 8px", center_text=True))
        self.year_input.setStyleSheet(style)

    def _on_date_anchor_changed(self, *_args):
        year = self._picked_year()
        month = self.month_combo.currentData()
        if year is None or month is None:
            return
        keep_day = self.day_combo.currentData() or 1
        self._repopulate_days(year, month, keep_day)

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
        year, month, day = (self._picked_year(), self.month_combo.currentData(), self.day_combo.currentData())
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
        # center_text keeps the closed label centered too; center_combo_items
        # gives every dropdown row the centered alignment role.
        self.recurrence_combo.setStyleSheet(combo_stylesheet(palette, padding="4px 8px", center_text=True))
        self.recurrence_combo.setFixedHeight(34)
        self.recurrence_combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        center_combo_items(self.recurrence_combo)
        # The QSS font lands after Qt's sizeHint, so enforce a measured width
        # or the closed combo elides «بدون تکرار» to "بدو...رار".
        fit_combo_width(self.recurrence_combo)

        date_row_label = self.date_row.findChild(QLabel, "DateRowLabel")
        if date_row_label:
            date_row_label.setStyleSheet(
                f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.year_input.setFixedHeight(34)
        self.year_input.setFixedWidth(92)
        # _apply_year_style keeps the red error border when the typed year is
        # out of range, so the shared style goes through it instead of QSS.
        self._apply_year_style()
        self.year_hint_label.setStyleSheet(
            f"color: {palette['HOLIDAY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            f"font-size: 12px; font-weight: bold; background: transparent; border: none;")
        for combo in (self.month_combo, self.day_combo):
            combo.setStyleSheet(combo_stylesheet(palette, padding="4px 8px", center_text=True))
            combo.setFixedHeight(34)
            combo.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            center_combo_items(combo)
        fit_combo_width(self.month_combo)

        self.remove_after_finish_checkbox.update_visuals()

        self.cancel_button.setStyleSheet(danger_button_stylesheet(palette))
        self.save_button.setStyleSheet(accent_button_stylesheet(palette))

    def set_data(self, text, recurrence, remove_after_finish):
        """Prefill the editor. Unknown recurrence values fall back to one-time."""
        self.text_edit.setText(text)
        self.recurrence_combo.setCurrentIndex(
            _RECURRENCE_VALUES.index(recurrence) if recurrence in _RECURRENCE_VALUES else 0)
        self.remove_after_finish_checkbox.setChecked(remove_after_finish)
        self._on_recurrence_changed()

    def recurrence(self) -> str:
        return _RECURRENCE_VALUES[self.recurrence_combo.currentIndex()]

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
        self.year_input.setToolTip("" if is_one_time else "برای رویداد تکرارشونده نیازی به سال نیست")
        monthly = mode == RECURRENCE_MONTHLY
        self.month_combo.setEnabled(not monthly)
        self.month_combo.setToolTip("برای رویداد ماهانه فقط روز مهم است" if monthly else "")
        self._apply_year_style()

    def _on_save(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        # In the manager's add flow a one-time event needs a complete in-range
        # date; an out-of-range year gets the red error border and blocks the
        # save so an unreachable event (e.g. year 3213) can never be created.
        if self.date_row.isVisible() and self.event_date() is None:
            self._set_year_error(self._year_is_out_of_range())
            self.year_input.setFocus()
            return
        self.saved.emit(text, self.recurrence(), self.remove_after_finish_checkbox.isChecked())