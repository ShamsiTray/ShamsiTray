"""
Calendar Day Cell Widget
----------------------

This module provides `ClickableLabel`, a QLabel subclass that emits signals
for left-clicks and context menu requests. It's used for the calendar day
cells to handle date selection and event management.
"""
from typing import Optional

import jdatetime
from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent, QCursor
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget, QWidgetAction

from config import APP_CONFIG
from utils.date_utils import format_gregorian_numeric, format_jalali_numeric
from utils.ui_helpers import clamp_popup_to_work_area
from .menu_widgets import (CenteredTextMenu, MENU_ITEM_PADDING_H,
                           MENU_ITEM_PADDING_V, MenuActionWidget)
from .tooltip import CustomTooltip

# Clipboard payloads of the «کپی تاریخ» submenu entries, built from the
# right-clicked day's own Jalali date (the Gregorian half derives from it).
_COPY_MODES = ("jalali", "gregorian", "both")

_COPY_ACTION_TEXTS = ("تاریخ شمسی", "تاریخ میلادی", "هر دو")

# Its own group, after «کپی تاریخ»: this asks a question about the day rather
# than acting on it, so it reads as a separate kind of row.
DISTANCE_ACTION_TEXT = "فاصله تا امروز"


def _copy_text_for_mode(mode: str, jdate: jdatetime.date) -> str:
    """Clipboard text for one «کپی تاریخ» entry.

    «تاریخ شمسی» copies the Jalali date only, «تاریخ میلادی» the Gregorian one,
    and «هر دو» both on separate lines (ready to paste into a message).
    Formatting comes from the shared date_utils helpers - the same numeric
    convention the tray tooltip uses - not a format invented here.
    """
    if mode == "jalali":
        return format_jalali_numeric(jdate)
    if mode == "gregorian":
        return format_gregorian_numeric(jdate)
    return f"{format_jalali_numeric(jdate)}\n{format_gregorian_numeric(jdate)}"


def _menu_stylesheet(palette: dict) -> str:
    """The shared day-cell menu stylesheet (parent menu AND submenus, so a
    submenu never falls back to the stock Qt popup look).

    The item rules mirror MenuActionWidget's own row look so the native
    «کپی تاریخ» rows and the custom add/remove-event rows read as one menu: the
    same Vazirmatn 14px bold text, the same 15px/6px inner box (the widget's
    layout margins) - hence the same 34px row height - and the same rounded
    MENU_HOVER_COLOR hover (HoverWidget paints exactly this RGBA).

    The item text itself is drawn ``transparent`` here: QSS cannot center
    QMenu::item text (no text-align support) and Qt's stylesheet engine paints
    CE_MenuItem entirely itself, so CenteredTextMenu paints the glyphs instead.
    The padding numbers come from the shared menu_widgets constants the painter
    uses, so QSS box and painted text cannot drift.

    Separator rows only provide spacing (11px, the same as the tray menu's
    dividers) and draw nothing themselves: CenteredTextMenu paints each line on
    the device-pixel grid, so the day menu's dividers come out the same thickness
    as the tray menu's instead of being drawn by QSS at a fractional position.

    There are deliberately NO arrow subcontrol rules: handing the arrow back to
    the style primitives proved invisible under some Windows styles/themes (the
    primitive is drawn in a color the custom background swallows), so
    CenteredTextMenu paints the indicator itself.
    """
    hover = palette["MENU_HOVER_COLOR"]
    hover_css = f"rgba({hover[0]}, {hover[1]}, {hover[2]}, {hover[3]})"
    return (
        f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; }}"
        f"QMenu::item {{ padding: {MENU_ITEM_PADDING_V}px {MENU_ITEM_PADDING_H}px; color: transparent; }}"
        f"QMenu::item:disabled {{ color: transparent; }}"
        f"QMenu::item:selected {{ background-color: {hover_css}; border-radius: 6px; }}"
        f"QMenu::separator {{ height: 11px; background-color: transparent; }}")


class ClickableLabel(QLabel):
    """A QLabel that emits signals for clicks and context menu actions."""
    clicked = pyqtSignal(object)
    add_event_requested = pyqtSignal(object)
    remove_event_requested = pyqtSignal(object)
    edit_event_requested_specific = pyqtSignal(object, str, dict)
    remove_event_requested_specific = pyqtSignal(str)
    distance_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None
        self.has_user_event = False
        self._tooltip_text = ""
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_custom_tooltip)
        self._context_menu_open = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

    def setToolTip(self, text: str):
        self._tooltip_text = text

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._tooltip_text and not self._context_menu_open:
            self._tooltip_timer.start(500)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._tooltip_timer.stop()
        CustomTooltip.instance().hide()

    def _cursor_inside(self) -> bool:
        """True only when the real cursor is inside this cell right now.

        Popup menus and overlay panels break the normal enter/leave chain, so
        the widget's own under-mouse state can go stale; the cursor position
        is the only source of truth (a stale pending timer must not pop a
        tooltip for a cell the user has long since moved off of - it would
        even float above the modal event editor).
        """
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _show_custom_tooltip(self):
        # The cursor check is what keeps a stale timer (menus and overlays
        # interrupt the enter/leave chain) from popping a tooltip for a cell
        # the cursor is no longer over - and from floating above the modal
        # event editor that opened since. The visibility check stops a timer
        # that outlived its whole window (calendar hidden mid-hover) from
        # floating the tooltip over unrelated applications.
        if not self.isVisible():
            return
        if self._tooltip_text and not self._context_menu_open and self._cursor_inside():
            global_pos = QCursor.pos()
            CustomTooltip.instance().show_tooltip(self._tooltip_text, global_pos)

    def cancel_pending_tooltip(self):
        """Stop a pending tooltip timer and dismiss the shared tooltip window.

        Closing the context menu re-arms the cell under the cursor (the menu's
        mouse grab interrupts the enter/leave chain), so a timer can fire while
        a modal surface - the event editor overlay or the delete confirmation -
        is already open, and the tooltip (a top-level ToolTip window) would
        float ON TOP of it. The host calendar calls this on every cell the
        moment such a surface opens; it is safe to call redundantly.
        """
        self._tooltip_timer.stop()
        CustomTooltip.instance().hide()

    def contextMenuEvent(self, event: QContextMenuEvent):
        if not self.jalali_date or not self.text():
            return

        self._context_menu_open = True
        CustomTooltip.instance().hide()

        palette = APP_CONFIG.get_current_palette()
        menu = CenteredTextMenu(self)
        menu.setStyleSheet(_menu_stylesheet(palette))
        # Persian app: the day menu presents RTL, and the copy submenu inherits
        # the direction below (Qt mirrors the popup side, the submenu arrow and
        # keyboard navigation from it). Layout direction changes which *side* a
        # row sits on, not the order: insertion order is the reading order here,
        # so this block is the menu as the user reads it - first the two ways to
        # take the day away with them (its text, how far off it is), then the two
        # that change the day itself.
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._build_copy_date_menu(menu)

        menu.addSeparator()

        distance_widget = MenuActionWidget(DISTANCE_ACTION_TEXT, menu)
        distance_action = QWidgetAction(menu)
        distance_action.setDefaultWidget(distance_widget)
        menu.addAction(distance_action)

        menu.addSeparator()

        from utils.event_io import events_on_date  # local import to avoid cycle

        day_events = events_on_date(self.window().user_events, self.jalali_date) if hasattr(self.window(), "user_events") else []
        self._day_events_list = day_events

        if len(day_events) <= 1:
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
        else:
            edit_menu = CenteredTextMenu(menu)
            edit_menu.setTitle("ویرایش رویداد")
            menu.addMenu(edit_menu)
            edit_menu.setStyleSheet(_menu_stylesheet(APP_CONFIG.get_current_palette()))
            edit_menu.setLayoutDirection(menu.layoutDirection())

            for key, entry in day_events:
                text = str(entry.get("text", ""))
                if len(text) > 30:
                    text = text[:30] + "…"
                rec = entry.get("recurrence", "none")
                if rec == "yearly":
                    label = f"{text} (سالانه)"
                elif rec == "monthly":
                    label = f"{text} (ماهانه)"
                else:
                    label = text
                action = edit_menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, k=key, e=entry: self._trigger_edit_specific_and_close(menu, k, e)
                )

            menu.addSeparator()

            del_menu = CenteredTextMenu(menu)
            del_menu.setTitle("حذف رویداد")
            menu.addMenu(del_menu)
            del_menu.setStyleSheet(_menu_stylesheet(APP_CONFIG.get_current_palette()))
            del_menu.setLayoutDirection(menu.layoutDirection())

            for key, entry in day_events:
                text = str(entry.get("text", ""))
                if len(text) > 30:
                    text = text[:30] + "…"
                rec = entry.get("recurrence", "none")
                if rec == "yearly":
                    label = f"{text} (سالانه)"
                elif rec == "monthly":
                    label = f"{text} (ماهانه)"
                else:
                    label = text
                action = del_menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, k=key: self._trigger_remove_specific_and_close(menu, k)
                )

        distance_widget.triggered.connect(lambda: self._trigger_distance_and_close_menu(menu, self.jalali_date))

        menu.exec(clamp_popup_to_work_area(menu, self.mapToGlobal(event.pos())))

        self._context_menu_open = False
        self.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        self.update()
        # The menu's grab interrupted the enter/leave chain; let the calendar
        # re-sync every cell's hover flag against the real cursor position
        # (decoupled: the cell must not depend on its host's concrete type).
        normalize_hover = getattr(self.window(), "normalize_day_hover", None)
        if callable(normalize_hover):
            normalize_hover()

    def _build_copy_date_menu(self, parent_menu: QMenu) -> QMenu:
        """Add the «کپی تاریخ» submenu to the day menu as a PLAIN Qt submenu.

        ``addMenu`` gives Qt full ownership of the row: hover-to-open, open/close,
        keyboard navigation, the submenu arrow, RTL mirroring and screen-edge
        placement are all native - no custom row widget and no click fallback (a
        hand-rolled arrow row proved unreliable at exactly these). The popup still
        gets the shared menu stylesheet, so it keeps the rounded palette-colored
        look of its parent, and its direction is pinned to the parent's
        (top-level popup windows do not reliably inherit it on every platform).

        The three entries are separated by hairline separators so they read as
        distinct options. The popup is a ``CenteredTextMenu`` so its rows' text is
        centered like the custom add/remove rows; it is built first and handed to
        ``addMenu`` because a class swap is impossible after ``addMenu(title)``
        constructed the popup internally.
        """
        copy_menu = CenteredTextMenu(parent_menu)
        copy_menu.setTitle("کپی تاریخ")
        parent_menu.addMenu(copy_menu)
        copy_menu.setStyleSheet(_menu_stylesheet(APP_CONFIG.get_current_palette()))
        copy_menu.setLayoutDirection(parent_menu.layoutDirection())

        for index, (mode, text) in enumerate(zip(_COPY_MODES, _COPY_ACTION_TEXTS)):
            if index:
                copy_menu.addSeparator()
            action = copy_menu.addAction(text)
            action.triggered.connect(
                lambda checked=False, mode=mode: self._copy_date_and_close(copy_menu, mode))
        return copy_menu

    def _copy_date_and_close(self, copy_menu: QMenu, mode: str):
        """Copy the right-clicked day's date(s) and close the menus.

        The payload always comes from ``self.jalali_date`` - the day the user
        actually right-clicked - never from today's date.
        """
        jdate = self.jalali_date
        if not jdate:
            copy_menu.close()
            return
        QApplication.clipboard().setText(_copy_text_for_mode(mode, jdate))
        # The feedback is a non-activating ToolTip window, so showing it while the
        # popup dismisses cannot steal focus or swallow the closing menu's grab.
        self._flash_copied_feedback()
        copy_menu.close()

    def _flash_copied_feedback(self):
        """Brief «کپی شد» confirmation, matching the converter's copy feedback."""
        CustomTooltip.instance().show_tooltip("کپی شد", QCursor.pos())
        QTimer.singleShot(600, CustomTooltip.instance().hide)

    def _trigger_add_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        # Delay emission slightly to ensure the context menu fully closes
        # before opening any new dialogs or widgets.
        QTimer.singleShot(50, lambda: self.add_event_requested.emit(jdate))

    def _trigger_remove_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        QTimer.singleShot(50, lambda: self.remove_event_requested.emit(jdate))

    def _trigger_edit_specific_and_close(self, menu: QMenu, key: str, entry: dict):
        menu.close()
        QTimer.singleShot(50, lambda: self.edit_event_requested_specific.emit(self.jalali_date, key, entry))

    def _trigger_remove_specific_and_close(self, menu: QMenu, key: str):
        menu.close()
        QTimer.singleShot(50, lambda: self.remove_event_requested_specific.emit(key))

    def _trigger_distance_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        # Same deferred emission as the event rows: the notice opens a modal
        # dialog, which must not appear while the menu still holds its grab.
        QTimer.singleShot(50, lambda: self.distance_requested.emit(jdate))
