"""
Theme Shots: real-window previews
---------------------------------

Renders the *actual* calendar window - the very ``PersianCalendarWidget`` the
tray opens - in any registered palette, at the window's own size. The gallery
preview panel is therefore a true screenshot-scale preview of the theme: the
same month the user is living in, their holidays, their events, the real
header/weekday/grid surfaces, nothing painted to resemble them.

The renderer keeps one hidden calendar widget and restyles it per theme
(palette swap + ``update_styles``), which measures ~10 ms a theme versus
~25 ms for building a fresh window per request. Renders happen on demand -
the gallery asks for exactly the theme being previewed.

Correctness notes:
- The hidden widget is never ``show()``-ed; ``QWidget.render`` on a polished,
  layout-activated widget paints byte-identical pixels to a shown grab (the
  equivalence is pinned by the test suite).
- The palette swap touches only ``APP_CONFIG.current_palette`` in memory -
  no settings write, no controller signal - and is restored in a ``finally``
  so the live theme survives an exception mid-render.
- The hidden widget is re-parented to the gallery window, so its lifetime and
  the artwork cache's follow the window the controller already keeps alive.
"""

from typing import Callable, Dict, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from config import APP_CONFIG
from utils.logger import setup_logging

logger = setup_logging(__name__)

# The render is painted at 2x so the preview stays crisp on scaled displays.
PREVIEW_DPR = 2.0


def _as_provider(value) -> Callable[[], dict]:
    """Accept a live-callable, a plain dict, or nothing; return a callable.

    A dict is wrapped so later mutations of the same dict object are still
    seen; a callable (what the controller passes) is used as-is so even a
    rebound attribute stays live."""
    if value is None:
        return lambda: {}
    if callable(value):
        return value
    return lambda: value


class CalendarShotRenderer:
    """The real-calendar preview engine behind the gallery.

    One instance per gallery window: it owns the hidden calendar widget and
    the per-theme render cache, and answers ``full_window_artwork(key,
    palette)`` - the preview panel's whole-window render - rendering on
    demand for a theme's first request."""

    def __init__(
        self,
        holidays: Callable[[], dict] | dict | None = None,
        events: Callable[[], dict] | None = None,
        parent: Optional[QWidget] = None,
    ):
        self._holidays_provider = _as_provider(holidays)
        self._events_provider = _as_provider(events)
        self._widget: Optional[QWidget] = None
        # The unscaled whole-window renders (the gallery's live preview
        # panel): one cache per requested theme.
        self._full_artwork: Dict[str, QPixmap] = {}
        self._parent = parent

    # --- session -----------------------------------------------------------

    def reset_session(self) -> None:
        """A new gallery session: drop every cached artwork and re-read the
        live data.

        The calendar previews the user's actual window, so stale art is worse
        than no art: events or holidays added while the gallery was closed
        must show up when it reopens, and a month rollover must move the
        previewed month along. Re-rendering is cheap and correctness stays
        unconditional."""
        self._full_artwork.clear()
        if self._widget is not None:
            self._widget.set_holidays(self._holidays_provider())
            self._widget.set_user_events(self._events_provider())

    # --- rendering ----------------------------------------------------------

    def _ensure_widget(self) -> QWidget:
        if self._widget is None:
            from ui.windows.calendar_window import PersianCalendarWidget

            widget = PersianCalendarWidget(self._holidays_provider(), self._events_provider())
            if self._parent is not None:
                widget.setParent(self._parent)
                # Pin the hidden state: setParent() on a parent that is not
                # shown yet leaves the child without the explicit-hide flag,
                # and the parent's later show() would propagate a show to it -
                # a full-size calendar painting over the gallery's own chrome
                # (the split panel builds its render during construction,
                # before the window is ever shown). An explicit hide() makes
                # the never-shown contract unconditional for both layouts.
                widget.hide()
            # The popup is a standalone LTR window: its RTL runs (weekday row,
            # day-grid origin) are set on the layouts themselves, while its
            # plain rows - month arrows, gregorian bar - rely on the LTR they
            # get as a top-level window. Re-parenting under the RTL gallery
            # inherits RTL and mirrors exactly those plain rows (the forward
            # chevron swaps to the visual right, the gregorian date to the
            # right of «امروز»), so the direction is pinned back to the
            # standalone window's before the layout activates. Setting it on
            # the widget propagates to every child that never chose one of
            # its own, which is all of the popup's children.
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            widget.ensurePolished()
            widget.layout().activate()
            self._widget = widget
        return self._widget

    def full_window_artwork(self, key: str, palette: dict) -> QPixmap:
        """The whole calendar window rendered in this palette at its own size,
        unscaled - the gallery's live preview panel, which shows the popup
        exactly as the user would get it. Carries the 2x device pixel ratio,
        so the panel displays it at the window's true logical size."""
        cached = self._full_artwork.get(key)
        if cached is not None:
            return cached
        rendered = self._render_window(palette)
        self._full_artwork[key] = rendered
        return rendered

    def _render_window(self, palette: dict) -> QPixmap:
        """The hidden calendar window painted in ``palette`` at 2x.

        The pixmap carries the 2x device pixel ratio and the widget renders
        into it in logical coordinates - exactly how Qt rasterizes a window on
        a high-DPI screen - so stylesheets and fonts rasterize natively at the
        target scale. (Scaling the painter on top of that would double the
        mapping and silently drop child widgets' text.)

        The palette swap happens on the Config *class*: ``APP_CONFIG`` is an
        instance and ``current_palette`` lives on the class, so an instance
        write would shadow it with a value ``set_theme`` can never update
        again - every ``APP_CONFIG.current_palette`` reader (the windows'
        painted backgrounds first among them) would stick to the palette of
        the first render while ``get_current_palette()`` moved on."""
        widget = self._ensure_widget()
        config_cls = type(APP_CONFIG)
        previous = config_cls.current_palette
        config_cls.current_palette = palette
        try:
            # update_styles re-runs the whole stylesheet sweep, including
            # fill_calendar_grid, so every day cell re-dresses in this palette.
            widget.update_styles()
            dpr = PREVIEW_DPR
            full = QPixmap(int(widget.width() * dpr), int(widget.height() * dpr))
            full.setDevicePixelRatio(dpr)
            full.fill(Qt.GlobalColor.transparent)
            painter = QPainter(full)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            widget.render(painter, QPoint(0, 0))
            painter.end()
        finally:
            config_cls.current_palette = previous
        return full
