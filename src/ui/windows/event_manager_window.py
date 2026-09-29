"""
Event Manager Window
--------------------

`EventManagerWindow` is a full management surface for user events, opened
from the tray menu («مدیریت رویدادها»). It complements the day-cell context
menu in the calendar: every event in the store is listed with its date and
recurrence, and can be searched, filtered, edited, deleted, imported and
exported.

The window operates directly on the controller's live ``user_events`` dict
(single source of truth) and persists through the controller's save path;
after every mutation it emits ``events_changed`` so the tray icon and the
calendar popup refresh.

Editing rules:
- One event per calendar date (same rule as the calendar editor): saving an
  event onto a date that already holds another event replaces that event
  (with a confirmation).
- The date of an existing event can be changed from the edit overlay: the
  date selector opens prefilled with the event's anchor (for recurring
  events with their next occurrence), and saving re-anchors the store key
  accordingly. Switching an event's recurrence keeps the month/day anchor
  shown in the selector; one-time events keep their full date. Monthly
  events ignore month/year (they repeat every month), yearly ones ignore
  the year.
- Saving without touching either the date or the recurrence leaves the
  stored key alone, so an event opened on a clamped occurrence (a day-31
  monthly event shown on the 30th) never drifts off its anchor.
- New events added here pick their date from the editor's year/month/day
  selector.
"""
from typing import Dict, Optional

import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from config import APP_CONFIG
from ui.widgets.checkbox import CustomCheckbox
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.event_input import EventInputWidget, recurrence_label
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.date_utils import days_in_jalali_month, persian_month_name, to_persian_digits
from utils.event_io import (RECURRENCE_MONTHLY, RECURRENCE_NONE,
                            RECURRENCE_YEARLY, events_sorted_by_next_occurrence,
                            make_event_key, next_occurrence_jdate, parse_event_key,
                            recurrence_of_key)
from utils.logger import setup_logging
from utils.ui_helpers import (accent_button_stylesheet, center_combo_items,
                              combo_stylesheet, fit_combo_width,
                              ghost_button_stylesheet, line_edit_stylesheet,
                              scrollbar_stylesheet)
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

_MONTH_ANY = 0  # «همه ماه‌ها» filter value
_TYPE_PAST = "past"  # «گذشته» filter value: only already-passed one-time events

# Badge on rows whose one-time event is flagged to delete itself once its
# date has passed (the «حذف پس از گذشت تاریخ» checkbox in the editor).
AUTO_DELETE_BADGE = "حذف خودکار"
AUTO_DELETE_TOOLTIP = "این رویداد پس از گذشت تاریخ به‌صورت خودکار حذف می‌شود"


# Recurrence-from-key now lives in event_io.recurrence_of_key: the key model
# belongs to the module that owns make_event_key/parse_event_key.


def _event_date_label(key: str) -> str:
    """Short Persian label for an event key ('1404-05-05', '0000-05-05', '0000-00-05')."""
    parsed = parse_event_key(key)
    if parsed is None:
        return str(key)
    year, month, day = parsed
    if year is None and month is None:
        return f"هر ماه - روز {to_persian_digits(day)}"
    if year is None:
        return f"هر سال - {to_persian_digits(day)} {persian_month_name(month)}"
    return to_persian_digits(f"{year:04d}/{month:02d}/{day:02d}")


def _event_anchor_month(key: str) -> Optional[int]:
    """Anchor month used by the month filter; monthly events match every month."""
    parsed = parse_event_key(key)
    if parsed is None:
        return None
    return parsed[1]  # None for monthly events -> they match any month filter


class EventRow(QFrame):
    """One event inside the manager list: date badge, text, edit/delete buttons."""
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, key: str, entry: dict, is_expired_one_time: bool, parent=None):
        super().__init__(parent)
        self.key = key
        self._expired = is_expired_one_time
        self.setObjectName("EventRow")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        date_box = QVBoxLayout()
        date_box.setSpacing(0)
        self.date_label = QLabel(_event_date_label(key))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setObjectName("EventDateLabel")
        date_box.addWidget(self.date_label)
        if recurrence_of_key(key) != RECURRENCE_NONE:
            badge = QLabel(recurrence_label(recurrence_of_key(key)))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setObjectName("EventRecurrenceBadge")
            date_box.addWidget(badge)
        elif entry.get("remove_after_finish", False):
            # The event will silently disappear once its date passes - say so,
            # or the row looks like every other one-time event until it doesn't.
            badge = QLabel(AUTO_DELETE_BADGE)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setObjectName("EventAutoDeleteBadge")
            badge.setToolTip(AUTO_DELETE_TOOLTIP)
            date_box.addWidget(badge)
        row.addLayout(date_box)

        self.text_label = QLabel(str(entry.get("text", "")))
        self.text_label.setWordWrap(True)
        self.text_label.setObjectName("EventTextLabel")
        row.addWidget(self.text_label, 1)

        self.edit_button = QPushButton("ویرایش")
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button = QPushButton("حذف")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.edit_button)
        row.addWidget(self.delete_button)

        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(self.key))
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.key))
        self.update_styles()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet(
            f"QFrame#EventRow {{ background-color: {palette['INPUT_BG_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 10px; }}"
            f"QFrame#EventRow QLabel {{ border: none; background: transparent; }}")
        date_color = palette['GREY_COLOR'] if self._expired else palette['ACCENT_COLOR']
        self.date_label.setStyleSheet(
            f"color: {date_color}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold;")
        for child in self.findChildren(QLabel):
            if child.objectName() == "EventRecurrenceBadge":
                child.setStyleSheet(
                    f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 11px;")
            elif child.objectName() == "EventAutoDeleteBadge":
                child.setStyleSheet(
                    f"color: {palette['HOLIDAY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 11px;")
        self.text_label.setStyleSheet(
            f"color: {palette['GREY_COLOR'] if self._expired else palette['TEXT_COLOR']}; "
            f"font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold;")
        self.edit_button.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px 12px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {palette['ACCENT_COLOR']}; color: {palette['ACCENT_COLOR']}; }}")
        self.delete_button.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {palette['HOLIDAY_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 5px 12px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {palette['HOLIDAY_COLOR']}; }}")


class EventManagerWindow(BaseFramelessWindow):
    """List/search/filter/edit/delete window for all stored user events."""
    events_changed = pyqtSignal()
    TASKBAR_ICON = True  # taskbar entry so a minimized manager can be reopened

    WIDTH, HEIGHT = 580, 560

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._editing_key: Optional[str] = None
        # Date/recurrence the editor opened with, so a save that changed neither
        # can keep the stored key (and with it the recurring anchor).
        self._edit_initial: Optional[tuple] = None
        self.setWindowTitle("مدیریت رویدادها")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._setup_ui()
        self.update_styles()
        self.refresh_list()
        apply_windows_styles(self)

    # --- UI construction ---

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(10)

        self.title_bar = WindowTitleBar(self.close, self.showMinimized)
        main_layout.addLayout(self.title_bar)
        main_layout.addSpacing(2)

        header_row = QHBoxLayout()
        self.title_label = QLabel("مدیریت رویدادها")
        self.count_label = QLabel("")
        header_row.addWidget(self.title_label)
        header_row.addStretch()
        header_row.addWidget(self.count_label)
        header_row.addSpacing(10)
        self.add_button = QPushButton("افزودن رویداد")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._on_add_requested)
        header_row.addWidget(self.add_button)
        main_layout.addLayout(header_row)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        # Short placeholder: the bar shares the row with two combos and the
        # past-events checkbox, so the long caption got elided to a stub.
        self.search_input.setPlaceholderText("جستجو…")
        self.search_input.setClearButtonEnabled(True)
        # An empty RTL line edit would put the caret on its visual left edge;
        # explicit right alignment keeps the caret on the right (where typing
        # starts) before anything is typed, like the calendar's event editor.
        # AlignAbsolute matters: this window is RTL, and bare AlignRight is
        # read as "trailing" there - which lands on the visual LEFT, exactly
        # the misplaced «جستجو…» the user saw. The absolute flag pins the
        # placeholder (and the text/caret) to the physical right edge.
        self.search_input.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        self.search_input.textChanged.connect(self.refresh_list)
        filter_row.addWidget(self.search_input, 1)

        # Plain combos; the dropdown renders without dead space thanks to the
        # vertical component in center_combo_items' item alignment.
        self.month_combo = QComboBox()
        self.month_combo.addItem("همه ماه‌ها", _MONTH_ANY)
        for i, name in enumerate(APP_CONFIG.PERSIAN_MONTHS, start=1):
            self.month_combo.addItem(name, i)
        center_combo_items(self.month_combo)
        self.month_combo.currentIndexChanged.connect(self.refresh_list)
        filter_row.addWidget(self.month_combo)

        self.type_combo = QComboBox()
        self.type_combo.addItem("همه انواع", None)
        self.type_combo.addItem(recurrence_label(RECURRENCE_NONE), RECURRENCE_NONE)
        self.type_combo.addItem(recurrence_label(RECURRENCE_MONTHLY), RECURRENCE_MONTHLY)
        self.type_combo.addItem(recurrence_label(RECURRENCE_YEARLY), RECURRENCE_YEARLY)
        # «گذشته» narrows the list to one-time events whose date has already
        # passed - the complement of hiding past events.
        self.type_combo.addItem("گذشته", _TYPE_PAST)
        center_combo_items(self.type_combo)
        self.type_combo.currentIndexChanged.connect(self.refresh_list)
        filter_row.addWidget(self.type_combo)

        # Unticking hides one-time events whose date has already passed;
        # recurring events never "pass" so they are always listed.
        self.past_checkbox = CustomCheckbox("نمایش رویدادهای گذشته", is_checked=True)
        self.past_checkbox.toggled.connect(self.refresh_list)
        filter_row.addSpacing(6)
        filter_row.addWidget(self.past_checkbox)
        main_layout.addLayout(filter_row)

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

        self.empty_label = QLabel("رویدادی یافت نشد.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.empty_label)

        footer_row = QHBoxLayout()
        # Deliberately text-only buttons: two rounds of icons here (inline FA
        # glyphs, then pre-rendered QIcons) both looked bad on the user's
        # Windows machine, and the labels alone say everything.
        self.export_button = QPushButton("خروجی گرفتن")
        self.import_button = QPushButton("وارد کردن")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._on_import)
        self.export_button.clicked.connect(self._on_export)
        footer_row.addWidget(self.export_button)
        footer_row.addWidget(self.import_button)
        footer_row.addStretch()
        main_layout.addLayout(footer_row)

        # Inline editor overlay (the same widget the calendar popup uses).
        self.event_input_widget = EventInputWidget(self)
        self.event_input_widget.saved.connect(self._on_edit_saved)
        self.event_input_widget.canceled.connect(self._hide_event_input_widget)
        self.event_input_widget.hide()

        # Click-blocking scrim behind the editor, mirroring the calendar
        # popup: while «افزودن رویداد» is open the manager behind it must not
        # react to clicks; the translucent fill also signals the modal state.
        self.overlay_blocker = QWidget(self)
        self.overlay_blocker.setStyleSheet("background-color: rgba(0, 0, 0, 75); border-radius: 26px; margin: 1px;")
        self.overlay_blocker.hide()

    def hideEvent(self, event):
        """Hiding the window must also tear down the editor overlay, so a
        stale scrim can never eat clicks after the manager reopens."""
        if self.event_input_widget.isVisible():
            self.event_input_widget.hide()
        self._editing_key = None
        self.overlay_blocker.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_list()

    # --- data plumbing ---

    @property
    def user_events(self) -> Dict[str, dict]:
        return self.controller.user_events

    @property
    def event_store(self):
        """The EventService owning the store.

        The manager requests operations (delete/upsert) from the service instead
        of mutating persistence itself: transactional saves, rollback and the
        save-failure dialog are handled in one place.
        """
        return self.controller._events

    def refresh_list(self):
        """Rebuild the event rows from the live store, applying search + filters."""
        search_text = self.search_input.text().strip().lower()
        selected_month = self.month_combo.currentData()
        selected_type = self.type_combo.currentData()
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        today = jdatetime.date.today()
        show_past = self.past_checkbox.isChecked()
        shown = 0
        for key in events_sorted_by_next_occurrence(self.user_events):
            entry = self.user_events[key]
            recurrence = recurrence_of_key(key)
            parsed = parse_event_key(key)
            next_date = next_occurrence_jdate(key, today) if parsed else None
            is_expired = (
                recurrence == RECURRENCE_NONE
                and parsed is not None and parsed[0] is not None
                and next_date is not None and next_date < today
            )
            if selected_type == _TYPE_PAST:
                # «گذشته»: only one-time events whose date has passed; the
                # show-past checkbox is irrelevant here and never hides them.
                if not is_expired:
                    continue
            elif selected_type is not None and recurrence != selected_type:
                continue
            if selected_month != _MONTH_ANY:
                anchor = _event_anchor_month(key)
                if anchor is not None and anchor != selected_month:
                    continue
            if search_text and search_text not in str(entry.get("text", "")).lower():
                continue
            if is_expired and not show_past and selected_type != _TYPE_PAST:
                continue
            row = EventRow(key, entry, is_expired)
            row.edit_requested.connect(self._on_edit_requested)
            row.delete_requested.connect(self._on_delete_requested)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            shown += 1

        total = len(self.user_events)
        filtered = bool(search_text) or selected_month != _MONTH_ANY or selected_type is not None
        if total and filtered:
            # While a filter narrows the list, show "X of Y" so the counter
            # cannot contradict the rows below it.
            self.count_label.setText(
                f"{to_persian_digits(shown)} از {to_persian_digits(total)} رویداد")
        else:
            self.count_label.setText(f"{to_persian_digits(total)} رویداد" if total else "")
        self.empty_label.setVisible(shown == 0)
        self.scroll_area.setVisible(shown > 0)
        self._restyle_dynamic_children()

    # --- mutations ---

    def _confirm_delete(self, key: str) -> bool:
        """Ask before deleting; red must never delete without a question.

        Themed in-app dialog: the stock QMessageBox ignored the palette and
        its wording was long-winded for a yes/no ask."""
        text = str(self.user_events[key].get("text", ""))
        preview = text if len(text) <= 40 else text[:40] + "…"
        return ConfirmDialog.ask(
            self, "حذف رویداد", "این رویداد حذف شود؟", detail=preview,
            confirm_text="حذف", cancel_text="انصراف", danger=True)

    def _on_delete_requested(self, key: str):
        if key not in self.user_events:
            return
        if not self._confirm_delete(key):
            return
        # Through the service: the save is transactional, and on failure the
        # store rolls back while the themed error dialog fires via the service's
        # on_save_error hook - so no refresh happens here and the list still
        # matches what was persisted.
        if self.event_store.delete_key(key):
            logger.info(f"Event {key!r} deleted from the event manager.")
            self.events_changed.emit()
            self.refresh_list()

    def _on_add_requested(self):
        """Open the same editor the calendar uses, plus a date picker row."""
        if self.event_input_widget.isVisible():
            return
        self._editing_key = None
        self._edit_initial = None
        self.event_input_widget.set_title("افزودن رویداد جدید")
        self.event_input_widget.set_data("", RECURRENCE_NONE, False)
        self.event_input_widget.set_date_selector_visible(True)
        self._show_event_input_overlay()

    def _show_event_input_overlay(self):
        """Center the editor overlay over the window (size depends on mode)."""
        width = self.width() - 60
        # isHidden(): the overlay itself is still hidden here, so isVisible()
        # would always report False for the date row.
        height = 340 if not self.event_input_widget.date_row.isHidden() else 300
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2
        # Modal: the scrim below blocks every click on the manager and dims it.
        self.overlay_blocker.setGeometry(self.rect())
        self.overlay_blocker.show()
        self.overlay_blocker.raise_()
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _on_edit_requested(self, key: str):
        if key not in self.user_events or self.event_input_widget.isVisible():
            return
        self._editing_key = key
        self._edit_initial = None
        entry = self.user_events[key]
        recurrence = entry.get("recurrence", RECURRENCE_NONE)
        self.event_input_widget.set_title("ویرایش رویداد")
        self.event_input_widget.set_data(
            entry.get("text", ""), recurrence,
            entry.get("remove_after_finish", False))
        # The date selector is visible in edit mode too, prefilled with the
        # event's own anchor: one-time events keep their full date; recurring
        # ones open on their next occurrence (today or later), so switching
        # them to one-time lands on a sensible, already-visible date.
        today = jdatetime.date.today()
        if recurrence == RECURRENCE_NONE:
            parsed = parse_event_key(key)
            if parsed is not None:
                year, month, day = parsed
                try:
                    initial = jdatetime.date(year, month, day)
                except ValueError:
                    # A stored key that no longer forms a valid date (calendar
                    # data changed) - clamp instead of crashing the editor.
                    safe_day = min(day, days_in_jalali_month(year, month))
                    initial = jdatetime.date(year, month, safe_day)
            else:
                initial = today
        else:
            initial = next_occurrence_jdate(key) or today
        self.event_input_widget.set_date_selector_visible(True, initial)
        self._edit_initial = (initial, recurrence)
        self._show_event_input_overlay()

    def _on_edit_saved(self, text: str, recurrence: str, remove_after_finish: bool):
        editing_key = self._editing_key
        picked_date = self.event_input_widget.event_date()
        if recurrence != RECURRENCE_NONE:
            remove_after_finish = False

        if editing_key is None:
            # Add flow: the anchor comes from the date selector row.
            if picked_date is None:
                return
            new_key = make_event_key(picked_date, recurrence)
            if new_key in self.user_events and not self._confirm_replace(new_key):
                return
        else:
            if editing_key not in self.user_events:
                return
            # The date selector is visible while editing, so its picked date
            # (prefilled with the old anchor) decides the new store key -
            # that is how the event's date gets changed from the manager.
            # make_event_key drops the dimensions a recurring key ignores
            # (year for yearly, year+month for monthly), matching the
            # greyed-out fields in the editor.
            if picked_date is None:
                picked_date = next_occurrence_jdate(editing_key) or jdatetime.date.today()
            if self._edit_initial == (picked_date, recurrence):
                # Date and recurrence are both untouched. The selector may be
                # showing a clamped occurrence (day 31 of a 30-day month, 30
                # Esfand of a non-leap year), so re-deriving the key here would
                # silently move the anchor the user never meant to move.
                new_key = editing_key
            else:
                new_key = make_event_key(picked_date, recurrence)
            # Moving onto a date that already holds an event replaces it; ask.
            if new_key != editing_key and new_key in self.user_events \
                    and not self._confirm_replace(new_key):
                return

        self._hide_event_input_widget()
        replace_keys = []
        if editing_key is not None and new_key != editing_key:
            replace_keys.append(editing_key)
        entry = {"text": text, "recurrence": recurrence, "remove_after_finish": remove_after_finish}
        # Through the service: one transactional save. The manager no longer
        # writes the store dict directly, so a failed save rolls the store back
        # here too (previously the manager kept the mutated state that never
        # reached the disk).
        if self.event_store.upsert(new_key, entry, replace_keys=replace_keys):
            action = "added" if editing_key is None else "updated"
            logger.info(f"Event {new_key!r} {action} via the event manager.")
            self.events_changed.emit()
            self.refresh_list()

    def _confirm_replace(self, key: str) -> bool:
        """Adding onto a date that already holds an event replaces it; ask first."""
        text = str(self.user_events[key].get("text", ""))
        return ConfirmDialog.ask(
            self, "رویداد تکراری", "برای این تاریخ از قبل رویدادی ثبت شده است؛ جایگزین شود؟",
            detail=text, confirm_text="جایگزینی", cancel_text="انصراف", danger=False)

    def _hide_event_input_widget(self):
        self._editing_key = None
        self._edit_initial = None
        self.event_input_widget.hide()
        self.overlay_blocker.hide()

    def _on_import(self):
        if self.controller.import_events_from_dialog(parent=self):
            self.events_changed.emit()
            self.refresh_list()

    def _on_export(self):
        self.controller.export_events_to_dialog(parent=self)

    # --- styling ---

    def _restyle_dynamic_children(self):
        palette = APP_CONFIG.get_current_palette()
        for row in self.list_container.findChildren(EventRow):
            row.update_styles()
        self.empty_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 15px; font-weight: bold; background: transparent;")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.title_bar.update_styles()
        self.title_label.setStyleSheet(
            f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        self.count_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        self.add_button.setStyleSheet(accent_button_stylesheet(palette, padding="6px 14px"))
        self.search_input.setStyleSheet(line_edit_stylesheet(palette))
        self.search_input.setFixedHeight(38)
        combo_style = combo_stylesheet(palette, padding="4px 8px", center_text=True)
        for combo in (self.month_combo, self.type_combo):
            combo.setStyleSheet(combo_style)
            combo.setFixedHeight(38)
            # Width must be measured against the QSS font, not the default
            # widget font, or «همه ماه‌ها» / «همه انواع» end up elided.
            fit_combo_width(combo)
        self.past_checkbox.update_visuals()
        # Import/export are ordinary actions, not destructive ones: the neutral
        # outline style keeps red reserved for delete/cancel (bad UX to imply
        # "look at me" on export with a warning colour).
        ghost_style = ghost_button_stylesheet(palette)
        self.import_button.setStyleSheet(ghost_style)
        self.export_button.setStyleSheet(ghost_style)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; }" + scrollbar_stylesheet(palette))
        self.list_container.setStyleSheet("background: transparent;")
        self._restyle_dynamic_children()
        self.event_input_widget.update_styles()
