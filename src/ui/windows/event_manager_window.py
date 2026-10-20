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
- The manager is its OWN replacement flow: saving an event onto a date that
  already holds another event replaces that event, after a confirmation naming
  it. The calendar's day editor is keyed instead and edits one event at a time,
  so this stricter date-level rule is deliberately not shared with it.
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
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QStackedWidget, QVBoxLayout,
                             QWidget)

from config import APP_CONFIG
from ui.widgets.checkbox import CustomCheckbox
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.event_input import (EventInputWidget, delete_confirmation_message,
                                   recurrence_label)
from ui.widgets.tooltip import TooltipButton, TooltipLabel
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.date_utils import (days_in_jalali_month, normalize_search_text,
                              persian_month_name, to_persian_digits)
from utils.event_io import (RECURRENCE_MONTHLY, RECURRENCE_NONE,
                            RECURRENCE_YEARLY, events_sorted_by_next_occurrence,
                            keys_share_visible_date, make_event_key,
                            next_occurrence_jdate, parse_event_key,
                            recurrence_of_key)
from utils.logger import setup_logging
from utils.ui_helpers import (SCROLL_BOTTOM_PAD_PX, accent_button_stylesheet,
                              center_combo_items, combo_stylesheet,
                              fit_combo_width, ghost_button_stylesheet,
                              line_edit_stylesheet, scrollbar_stylesheet)
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

_MONTH_ANY = 0  # «همه ماه‌ها» filter value
_TYPE_PAST = "past"  # «گذشته» filter value: only already-passed one-time events

# Marker on rows whose one-time event is flagged to delete itself once its
# date has passed (the «حذف پس از گذشت تاریخ» checkbox in the editor).
AUTO_DELETE_MARKER = "حذف خودکار"
AUTO_DELETE_TOOLTIP = "این رویداد پس از گذشت تاریخ به‌صورت خودکار حذف می‌شود"


# recurrence_of_key() in event_io owns this: the key model stays in one module,
# next to make_event_key/parse_event_key.


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
    """One event inside the manager list: title, date line, icon actions."""
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, key: str, entry: dict, is_expired_one_time: bool, parent=None):
        super().__init__(parent)
        self.key = key
        self._expired = is_expired_one_time
        # Only a one-time event can carry the flag (the editor drops it for a
        # recurring one), so the marker below has exactly one meaning.
        self._auto_delete = (recurrence_of_key(key) == RECURRENCE_NONE
                             and bool(entry.get("remove_after_finish", False)))
        self.setObjectName("EventRow")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(6)

        # Pin to the right regardless of the text's own direction (an English
        # title would otherwise jump to the left in this RTL row).
        right = (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                 | Qt.AlignmentFlag.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.text_label = QLabel(str(entry.get("text", "")))
        self.text_label.setWordWrap(True)
        self.text_label.setObjectName("EventTextLabel")
        self.text_label.setAlignment(right)
        text_box.addWidget(self.text_label)

        # The date line spells the recurrence out («هر سال - ۵ مهر»), so the row
        # carries no second badge repeating it. Only the auto-delete marker has
        # nowhere else to live - without it the row looks like any other
        # one-time event until it silently disappears.
        self.date_label = TooltipLabel()
        self.date_label.setTextFormat(Qt.TextFormat.RichText)
        self.date_label.setObjectName("EventDateLabel")
        self.date_label.setAlignment(right)
        if self._auto_delete:
            self.date_label.setToolTip(AUTO_DELETE_TOOLTIP)
        text_box.addWidget(self.date_label)
        row.addLayout(text_box, 1)

        self.edit_button = TooltipButton(APP_CONFIG.FAS.FA_PEN)
        self.edit_button.setToolTip("ویرایش")
        self.delete_button = TooltipButton(APP_CONFIG.FAS.FA_TRASH)
        self.delete_button.setToolTip("حذف")
        for button in (self.edit_button, self.delete_button):
            button.setFixedSize(34, 34)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button)
        # The buttons' own text is a private-use glyph, which is all a screen
        # reader could make of it; the name says what the icon means. The themed
        # tooltip is what shows it here.
        self.edit_button.setAccessibleName("ویرایش")
        self.delete_button.setAccessibleName("حذف")
        # The trash glyph is red, so the tooltip that explains it uses the same
        # colour: this is the row's only destructive action, and the warning
        # should land before the click does. Edit changes nothing on its own and
        # stays neutral.
        self.delete_button.TOOLTIP_TONE = "danger"

        self._tooltip_widgets = (self.date_label, self.edit_button, self.delete_button)

        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(self.key))
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.key))
        self.update_styles()

    def cancel_pending_tooltip(self):
        """Drop this row's tooltips; the list calls it whenever it scrolls."""
        for widget in self._tooltip_widgets:
            widget.cancel_pending_tooltip()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        font = APP_CONFIG.FONT_FAMILY
        self.setStyleSheet(
            f"QFrame#EventRow {{ background-color: {palette['INPUT_BG_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 10px; }}"
            f"QFrame#EventRow:hover {{ border-color: {palette['SCROLLBAR_HANDLE_COLOR']}; }}"
            f"QFrame#EventRow QLabel {{ border: none; background: transparent; }}")

        self.text_label.setStyleSheet(
            f"color: {palette['GREY_COLOR'] if self._expired else palette['TEXT_COLOR']}; "
            f"font-family: '{font}'; font-size: 14px; font-weight: bold;")

        date_color = palette['GREY_COLOR'] if self._expired else palette['ACCENT_COLOR']
        meta = f"<span style='color:{date_color}; font-weight:bold'>{_event_date_label(self.key)}</span>"
        if self._auto_delete:
            meta += (f"<span style='color:{palette['GREY_COLOR']}'> · </span>"
                     f"<span style='color:{palette['HOLIDAY_COLOR']}'>{AUTO_DELETE_MARKER}</span>")
        self.date_label.setText(meta)
        self.date_label.setStyleSheet(f"font-family: '{font}'; font-size: 12px;")

        red = QColor(palette['HOLIDAY_COLOR'])
        red_hover = f"rgba({red.red()}, {red.green()}, {red.blue()}, 40)"
        icon_base = (f"font-family: '{APP_CONFIG.FONT_AWESOME_FAMILY}'; font-size: 14px; "
                     "border: none; border-radius: 17px; background: transparent;")
        self.edit_button.setStyleSheet(
            f"QPushButton {{ color: {palette['GREY_COLOR']}; {icon_base} }}"
            f"QPushButton:hover {{ color: {palette['TEXT_COLOR']}; background-color: {palette['HOVER_BG']}; }}")
        self.delete_button.setStyleSheet(
            f"QPushButton {{ color: {palette['HOLIDAY_COLOR']}; {icon_base} }}"
            f"QPushButton:hover {{ background-color: {red_hover}; }}")


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
        # The scrollbar's rail hangs in the left padding band instead of the
        # margin line the header rows keep: 8px off the glass, matching the
        # 8px gutter it keeps from the rows on its other side. Content rows
        # that must stay on the old 18px line compensate with a trailing
        # addSpacing (under RTL that pads the row's LEFT end).
        main_layout.setContentsMargins(8, 14, 18, 14)
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
        header_row.addSpacing(10)           # back to the header's 18px margin line
        main_layout.addLayout(header_row)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        # Short placeholder: the bar shares the row with two combos and the
        # past-events checkbox, so the long caption got elided to a stub.
        self.search_input.setPlaceholderText("جستجو…")
        self.search_input.setClearButtonEnabled(True)
        # An empty RTL line edit puts the caret on its visual left edge, so the
        # caret is pinned right, where typing starts. AlignAbsolute matters: in an
        # RTL window bare AlignRight reads as "trailing" and lands on the visual
        # LEFT, taking the placeholder with it.
        self.search_input.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        self.search_input.textChanged.connect(self.refresh_list)
        filter_row.addWidget(self.search_input, 1)

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
        filter_row.addSpacing(10)           # back to the header's 18px margin line
        main_layout.addLayout(filter_row)

        self.list_container = QWidget()
        self.rows_layout = QVBoxLayout(self.list_container)
        # The scrollbar track hangs in the window's left padding band (8px
        # off the glass, matching the gutter on its other side — see the
        # main_layout comment) rather than on the margin line the rows'
        # headers keep. The gutter is the row column's only horizontal
        # inset, and the right edge stays flush with the header's margin
        # line (a mirrored inset misaligned the list with the header for
        # its whole height). The bottom pad and the track's matching margin
        # both come from SCROLL_BOTTOM_PAD_PX.
        self.rows_layout.setContentsMargins(8, 0, 0, SCROLL_BOTTOM_PAD_PX)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.list_container)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._dismiss_row_tooltips)

        self.empty_label = QLabel("رویدادی یافت نشد.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # One slot for the list and the «nothing found» label. Two siblings
        # toggled independently would collapse the hidden one to zero height,
        # and with nothing else asking for the stretch Qt hands the freed space
        # to the title row - the header moves whenever a filter empties the
        # list. A QStackedWidget reports a constant size whichever page is
        # current.
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.scroll_area)
        self.content_stack.addWidget(self.empty_label)
        main_layout.addWidget(self.content_stack, 1)

        footer_row = QHBoxLayout()
        # Deliberately text-only buttons: icon attempts here looked bad on
        # Windows, and the labels say everything.
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
        # The rows about to be rebuilt may be the ones a hover tooltip belongs
        # to; a row that is deleted would otherwise leave its tooltip floating.
        self._dismiss_row_tooltips()
        # Both sides of the comparison are normalized: pasting Arabic-Indic digits or
        # typing Arabic yeh/kaf must find the stored Persian text instead of
        # silently matching nothing.
        search_text = normalize_search_text(self.search_input.text().strip())
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
            if search_text:
                # The haystack carries the displayed label PLUS the anchor
                # month's name, so typing «مهر» or a year finds an event whose
                # numeric label (۱۴۰۵/۰۸/۰۱) names no month.
                text_haystack = normalize_search_text(str(entry.get("text", "")))
                date_haystack = normalize_search_text(_event_date_label(key))
                if parsed is not None and parsed[1] is not None:
                    date_haystack += " " + normalize_search_text(persian_month_name(parsed[1]))
                if search_text not in text_haystack and search_text not in date_haystack:
                    continue
            if is_expired and not show_past and selected_type != _TYPE_PAST:
                continue
            row = EventRow(key, entry, is_expired)
            row.edit_requested.connect(self._on_edit_requested)
            row.delete_requested.connect(self._on_delete_requested)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            shown += 1

        total = len(self.user_events)
        # An unchecked show-past filter DOES hide rows, so it counts as narrowing -
        # except under the «گذشته» type filter, where the checkbox is
        # irrelevant and never hides anything. Without that exception the
        # counter read «۲ رویداد» while one row was on screen.
        filtered = (bool(search_text)
                    or selected_month != _MONTH_ANY
                    or selected_type is not None
                    or (not show_past and selected_type != _TYPE_PAST))
        if total and filtered:
            # While a filter narrows the list, show "X of Y" so the counter
            # cannot contradict the rows below it.
            self.count_label.setText(
                f"{to_persian_digits(shown)} از {to_persian_digits(total)} رویداد")
        else:
            self.count_label.setText(f"{to_persian_digits(total)} رویداد" if total else "")
        self.content_stack.setCurrentWidget(self.empty_label if shown == 0 else self.scroll_area)
        self._restyle_dynamic_children()

    def _dismiss_row_tooltips(self):
        """Drop the rows' hover tooltips when the list moves under them.

        A wheel scroll slides a row out from under a stationary cursor without
        an enter/leave pair, so nothing else would tell the row (or its pending
        timer) that the cursor is no longer pointing at it. Each row drops only
        what it owns, leaving a «کپی شد» flash alone - the shared tooltip has one
        window for the whole app.
        """
        for row in self.list_container.findChildren(EventRow):
            row.cancel_pending_tooltip()

    # --- mutations ---

    def _confirm_delete(self, key: str) -> bool:
        """Ask before deleting; red must never delete without a question.

        Themed in-app dialog: the stock QMessageBox ignored the palette and
        its wording was long-winded for a yes/no ask. The question is built
        from the key, so a recurring event is asked about as its whole series
        rather than as the single row it was reached from."""
        text = str(self.user_events[key].get("text", ""))
        preview = text if len(text) <= 40 else text[:40] + "…"
        return ConfirmDialog.ask(
            self, "حذف رویداد", delete_confirmation_message([key]), detail=preview,
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

        # Snapshot for the guard below: the replace ask runs a nested event loop
        # over a store the rest of the app shares.
        store_at_ask = dict(self.user_events)
        collisions = []
        if editing_key is None:
            if picked_date is None:
                return
            # The store owns the verdict on which key this add lands on, exactly
            # as EventService.add() does: an event of ANOTHER recurrence on the
            # same visible date is a different logical event and stays where it
            # is. Only landing on the key that is already there is a duplicate,
            # and that still asks first.
            new_key = self.event_store.target_key(picked_date, recurrence)
            if new_key in self.user_events:
                if not self._confirm_replace([new_key]):
                    return
                collisions = [new_key]
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
            # Moving onto a date that already holds another event replaces it; ask.
            if new_key != editing_key:
                collisions = self._colliding_keys(new_key, exclude=editing_key)
                if collisions and not self._confirm_replace(collisions):
                    return

        # The confirmation above waited inside a nested event loop, and the
        # store is shared: the background expiry pass can delete an event while
        # the dialog is up. ``collisions``, ``editing_key`` and ``new_key`` all
        # describe the snapshot the user was shown, so acting on them now would
        # replace or drop an event that changed under the dialog. The save bails
        # and the editor stays up, so the next press works from the live store.
        if self.user_events != store_at_ask:
            logger.info("Event store changed while the replace confirmation was open; "
                        "not saving the edit.")
            return

        self._hide_event_input_widget()
        replace_keys = list(collisions)
        if editing_key is not None and new_key != editing_key:
            replace_keys.append(editing_key)
        entry = {"text": text, "recurrence": recurrence, "remove_after_finish": remove_after_finish}
        # Through the service: one transactional save, so a failed save rolls the
        # store back here too. Writing the store dict directly would keep the
        # mutated state that never reached the disk.
        if self.event_store.upsert(new_key, entry, replace_keys=replace_keys):
            action = "added" if editing_key is None else "updated"
            logger.info(f"Event {new_key!r} {action} via the event manager.")
            self.events_changed.emit()
            self.refresh_list()

    def _colliding_keys(self, new_key: str, exclude: Optional[str] = None) -> list:
        """Stored keys other than ``exclude`` that show on a date ``new_key`` shows on."""
        return [key for key in self.user_events
                if key != exclude and keys_share_visible_date(new_key, key)]

    def _confirm_replace(self, keys: list) -> bool:
        """Adding onto a date that already holds events replaces them; ask first.

        The save removes EVERY key the answer covers, so the ask has to name
        all of them: a dialog that previewed one event while the save deleted
        two would replace an event the user never saw.
        """
        texts = [str(self.user_events[key].get("text", "")) for key in keys]
        if len(keys) == 1:
            message = "برای این تاریخ از قبل رویدادی ثبت شده است؛ جایگزین شود؟"
        else:
            message = f"برای این تاریخ از قبل {len(keys)} رویداد ثبت شده است؛ همه جایگزین شوند؟"
        return ConfirmDialog.ask(
            self, "رویداد تکراری", message, detail="\n".join(texts),
            confirm_text="جایگزینی", cancel_text="انصراف", danger=False)

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
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; }"
                                       + scrollbar_stylesheet(palette,
                                                              bottom_margin=SCROLL_BOTTOM_PAD_PX))
        self.list_container.setStyleSheet("background: transparent;")
        self._restyle_dynamic_children()
        self.event_input_widget.update_styles()
