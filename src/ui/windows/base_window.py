"""
Base Frameless Window
---------------------

This module provides `BaseFramelessWindow`, a reusable base class for all
frameless windows in the application (e.g., Calendar, Tutorial, Converter).

It handles common functionality such as:
- A custom-painted rounded-rectangle background.
- Mouse events for dragging the frameless window.
- Translucent background.
- A taskbar presence for tool windows (see ``TASKBAR_ICON``).
- Optional popup semantics for windows that opt in with
  ``CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED`` while they are not pinned.
"""
import time
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget

from config import APP_CONFIG
from utils.ui_helpers import FramelessDragMixin

class BaseFramelessWindow(FramelessDragMixin, QWidget):
    """A base class for frameless windows with custom drag and paint logic.

    Subclasses set ``TASKBAR_ICON = True`` to opt into a real top-level window
    type: plain ``Qt.WindowType.Tool`` windows never get a taskbar entry, so a
    minimized tool window cannot be brought back. The calendar popup and tutorial
    keep the Tool behaviour (a taskbar button for a quick popup would be noise);
    the converter and the other tool windows show in the taskbar.

    Dragging comes from ``FramelessDragMixin`` - including the Qt mouse-event
    routing: the top ``DRAGGABLE_AREA_HEIGHT`` pixels act as the grab strip, and
    the window keeps its historical vertical clamp (only the top 50 px must stay
    above the screen's bottom edge).
    """
    TASKBAR_ICON = False
    drag_strip_height = APP_CONFIG.DRAGGABLE_AREA_HEIGHT
    drag_bottom_keep_visible = 50

    # Windows that behave like a dropdown (the calendar popup) set this True so
    # that, once always-on-top is switched off, losing activation to something
    # outside them closes them like any other popup. Real tool windows (event
    # manager, holiday viewer, converter) leave it off: those are forms someone
    # can be mid-edit in, and losing focus to another app is routine there.
    CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tracks the WindowStaysOnTopHint state this window was built with (Tool
        # windows start pinned, taskbar windows do not) so callers can toggle it
        # later without having to know which style they are looking at.
        self._always_on_top = not self.TASKBAR_ICON
        # When the last outside-click dismissal happened (see
        # consume_outside_click_dismissal).
        self._outside_dismissed_at = None
        # Supplied by the controller: "is the cursor over the tray icon right
        # now?". The answer is taken when a dismissal is RECORDED, not when the
        # tray icon's click is delivered - the press hides the popup and that
        # click arrives on the release up to a second later, by which time the
        # cursor position can no longer tell this click's own press from a
        # separate tray click.
        self.cursor_over_tray_probe: Optional[Callable[[], bool]] = None
        self._outside_dismissed_over_tray = False
        if self.TASKBAR_ICON:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            if APP_CONFIG.ICON_PATH.exists():
                self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
        else:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_always_on_top(self, enabled: bool) -> None:
        """Add or remove ``WindowStaysOnTopHint`` on this window.

        Qt re-evaluates a native window's flags only when it is shown again, so
        a window that is currently up is hidden and re-shown at the same
        geometry; calling this before the first ``show()`` (for example straight
        after construction) only updates the flags and never flickers.

        Unpinning a popup that is not the active window dismisses it instead of
        leaving it around: an unpinned popup only stays up while it holds
        activation (see ``changeEvent``), and the tray menu that flipped this
        setting is itself an outside click. Leaving it on screen would produce a
        window that no later click can dismiss — a click elsewhere only raises
        that other window over it, because the activation change it needs has
        already happened.
        """
        self._always_on_top = enabled
        flags = self.windowFlags()
        if enabled:
            updated = flags | Qt.WindowType.WindowStaysOnTopHint
        else:
            updated = flags & ~Qt.WindowType.WindowStaysOnTopHint
        if updated == flags:
            return
        was_visible = self.isVisible()
        was_active = self.isActiveWindow()
        geometry = self.geometry()
        self.setWindowFlags(updated)  # hides the native window when it is up
        if not was_visible:
            return
        if self._dismisses_when_unpinned() and not was_active:
            self.hide()
            return
        self.setGeometry(geometry)
        self.show()
        if was_active:
            # The flag change dropped the native window's activation. Without
            # restoring it the popup would sit there inactive while still
            # showing, which is exactly the state no click can dismiss.
            self.raise_()
            self.activateWindow()

    def _dismisses_when_unpinned(self) -> bool:
        """Whether this window is currently an unpinned popup."""
        return self.CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED and not self._always_on_top

    @staticmethod
    def _is_owned_by(widget, owner) -> bool:
        """True when ``owner`` is ``widget`` or anywhere in its parent chain.

        Walks ``parentWidget()`` rather than ``QWidget.isAncestorOf``: the
        latter only looks inside one top-level window, while a themed dialog is
        its own top-level window that merely has this window as its Qt parent.
        """
        while widget is not None:
            if widget is owner:
                return True
            widget = widget.parentWidget()
        return False

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.ActivationChange
                and self._dismisses_when_unpinned()
                and self.isVisible()
                and not self.isActiveWindow()):
            # A dialog this window opened takes activation as well; only a
            # genuinely foreign window - or nothing at all - dismisses the popup.
            active = QApplication.activeWindow()
            if active is None or not self._is_owned_by(active, self):
                self._record_outside_dismissal()

    def _record_outside_dismissal(self) -> None:
        """Stamp the dismissal and the cursor-over-tray verdict at this moment."""
        self._outside_dismissed_at = time.monotonic()
        probe = self.cursor_over_tray_probe
        # No probe means no better knowledge: keep the historical conservative
        # reading, where the tray overlap is assumed (an invalid tray geometry
        # used to count as over-tray too).
        self._outside_dismissed_over_tray = probe() if probe is not None else True
        self.hide()

    def consume_outside_click_dismissal(self, max_age_s: float = 1.0) -> bool:
        """True once if the window was just dismissed from over the tray icon.

        Closing the popup with the tray icon deactivates it first (the mouse
        press hides it) and delivers the icon's click only afterwards (the
        release), so without this check that click reads as "open the calendar"
        and instantly reopens what the same press just closed. The verdict is
        the cursor-over-tray probe taken when the dismissal was RECORDED: by
        the time the icon's click arrives, the cursor position can no longer
        tell that click's own press from a separate tray click inside the age
        window. Both the timestamp and the verdict are cleared on read, so the
        next click opens normally.
        """
        at, self._outside_dismissed_at = self._outside_dismissed_at, None
        over_tray, self._outside_dismissed_over_tray = self._outside_dismissed_over_tray, False
        return at is not None and (time.monotonic() - at) <= max_age_s and over_tray

    def paintEvent(self, event):
        if self.rect().isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        painter.setClipPath(path)
        super().paintEvent(event)
