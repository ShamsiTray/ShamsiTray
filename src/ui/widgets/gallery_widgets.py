"""
Gallery Building Blocks
-----------------------

Shared pieces of the theme gallery: the filter the catalog narrows through
(all / light / dark / favorites), the segmented control that drives it, the
favorite-star artwork, and the mini-calendar card artwork the picker grid
paints per theme.

The card art is the calendar abstracted to its silhouette at the reference
mock-up's proportions: an abstract header (a chevron tick at each end and a
short rounded bar as the title - real words at this size read as noise), the
weekday dashes with Friday already holiday-colored, five equal weeks of day
dots - ONE dot size everywhere, a day's state riding a tinted rounded square
behind the dot (the four in-month Fridays as the only holiday cells, an event,
today, the selected day with a thin text ring, out-of-month greys, and the
trailing out-of-month Friday as the real calendar's muted Friday cell) - and,
after a divider line, the theme's own name in Inter semibold inside the card -
so a compact card still reads as "this theme's calendar" while showing every
gear the theme recolors. The big preview panel beside the grid carries the
pixel-true render of the same month; the card is its thumbnail silhouette.

Every surface stays painted from palette keys only, so nothing about a theme
changes between the card, the panel and the applied app.
"""

import math
from typing import Iterable, List, Optional, Tuple

from PyQt6.QtCore import (QEasingCurve, QPointF, QRectF, QSize, Qt,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                         QPen, QPixmap)
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

from config import APP_CONFIG
from utils.logger import setup_logging
from utils.ui_helpers import contrast_ratio, on_accent_text_color

logger = setup_logging(__name__)

# --- card artwork geometry ---------------------------------------------------------

# The mini-calendar card: square like the reference mock-up, painted at 2x so
# the dots and the small text stay crisp on scaled displays.
CARD_WIDTH, CARD_HEIGHT = 118, 118
CARD_RADIUS = 14.0
CARD_DPR = 2.0

# The reference proportions, stated at the 118px-wide card: every measurement
# below scales by CARD_WIDTH / REF_CARD_WIDTH, so the artwork keeps the
# reference's proportions whatever card size a future layout asks for.
REF_CARD_WIDTH = 118.0
CARD_SIDE_PADDING = 10.0          # grid, dashes and divider inset from the sides
HEADER_CENTER_Y = 8.0             # chevron ticks + title bar centre
WEEKDAY_DASH_Y = 21.0             # the weekday dashes' centre
GRID_TOP_Y = 30.0                 # the first week's top
CELL_PITCH_W, CELL_PITCH_H = 14.0, 11.0   # one grid cell
CELL_INSET = 1.0                  # the state square's inset from its grid cell
STATE_RADIUS = 4.0                # the state square's corner radius
STATE_FILL_OPACITY = 0.30         # the holiday tint behind the dot
EVENT_FILL_OPACITY = 0.32         # the event day's tint behind the dot
MUTED_HOLIDAY_DOT_OPACITY = 0.45  # the trailing out-of-month Friday's dot
MUTED_HOLIDAY_FILL_OPACITY = 0.09 # ...and the whisper of tint under it
DIVIDER_Y = 92.0                  # the divider under the grid
NAME_TOP_Y = 98.0                 # the theme name's band top
NAME_FONT_PX = 10.5               # Inter semibold, floored to whole pixels

# --- filters ----------------------------------------------------------------------

FILTER_ALL, FILTER_DARK, FILTER_LIGHT = "all", "dark", "light"
FILTER_FAVORITES = "favorites"
FILTER_ORDER = (FILTER_ALL, FILTER_LIGHT, FILTER_DARK, FILTER_FAVORITES)
# The favorites segment is a star glyph, not a word (see SegmentedFilter), so
# it carries no text label - only an accessible name.
_FILTER_LABELS = {FILTER_ALL: "همه", FILTER_LIGHT: "روشن", FILTER_DARK: "تاریک",
                  FILTER_FAVORITES: ""}
_FILTER_ACCESSIBLE_NAMES = {FILTER_ALL: "همه", FILTER_LIGHT: "روشن",
                            FILTER_DARK: "تاریک",
                            FILTER_FAVORITES: "علاقه‌مندی‌ها"}

# The favorite star's one color: a warm gold that reads on every palette, light
# or dark, so a favorite looks the same on every card and stage.
FAVORITE_COLOR = "#F5B301"


def filtered_catalog(mode: str = FILTER_ALL,
                     favorites: Iterable[str] = ()) -> List[Tuple[str, str, dict]]:
    """Catalog entries surviving the filter, in catalog order."""
    favorite_keys = set(favorites)
    entries = []
    for key, name, palette in APP_CONFIG.theme_catalog():
        if mode == FILTER_DARK and not APP_CONFIG.palette_is_dark(palette):
            continue
        if mode == FILTER_LIGHT and APP_CONFIG.palette_is_dark(palette):
            continue
        if mode == FILTER_FAVORITES and key not in favorite_keys:
            continue
        entries.append((key, name, palette))
    return entries


# --- artwork ----------------------------------------------------------------------


def frame_accent_color(card_palette: dict, stage_palette: dict,
                       min_ratio: float = 3.0) -> QColor:
    """The accent a card's state frame is painted in.

    The frame rides the artwork's edge, so it straddles the card's art and the
    gallery's own background - and an accent is not guaranteed to read against
    a background it was never designed for: the bright accents the dark themes
    carry (Graphite's near-white, Dracula's cyan, Monokai Pro's yellow) sit at
    about 1.1:1 on a light gallery and vanish outright, while the deep accents
    of the light themes (paper_mono's near-black) wash out on a dark one. The
    accent is therefore nudged lighter on a dark stage and darker on a light
    one - hue untouched - until it clears ``min_ratio`` (the WCAG non-text
    contrast floor) against the stage the frame must read on; accents that
    already read pass through unchanged."""
    color = QColor(card_palette["ACCENT_COLOR"])
    background = QColor(stage_palette["BACKGROUND_COLOR"])
    if not color.isValid():
        color = QColor("#808080")
    lighten = background.lightness() < 128
    for _ in range(16):
        if contrast_ratio(color, background) >= min_ratio:
            break
        stepped = color.lighter(125) if lighten else color.darker(125)
        if stepped == color:
            # Pure black/white cannot be nudged by a factor - jump to the
            # extreme; contrast against this stage is maximal there.
            stepped = QColor("#ffffff") if lighten else QColor("#000000")
        color = stepped
    return color


# The card's day pattern (the "1b" reference): one char per cell, col 0 =
# Saturday (the rightmost column under RTL), col 6 = Friday. '.' a normal
# day, 'o' an out-of-month cell, 'h' the trailing out-of-month Friday (the
# muted Friday), 'H' an in-month Friday, 'T' today, 'E' a day carrying an
# event, 'S' the selected day. A fixed decorative month - identical on every
# card, because the card shows the theme's colors while the live month lives
# on the preview panel: 30 days opening on a Sunday and closing on a Monday,
# so week 0 leads with one out-of-month Saturday and week 4 trails with three
# out-of-month days plus the muted Friday. The four in-month Fridays are the
# ONLY holiday-colored cells - the sample carries no ad-hoc red days.
_DAY_GRID = (
    "o.....H",
    ".T....H",
    "...E..H",
    "..S...H",
    "...oooh",
)


def _qcolor(palette: dict, key: str) -> QColor:
    """A palette entry as a QColor, in whatever notation the pack carried.

    Packs state most keys as hex, but the calendar's day-state fills ride
    ``rgba(r, g, b, a)`` strings (alpha as a 0-1 float or 0-255 int) and at
    least one key is a raw ``(r, g, b, a)`` tuple - and QColor's string parser
    rejects the rgba() form outright (it resolves to invalid black), so the
    three notations are folded together here."""
    value = palette[key]
    if isinstance(value, (tuple, list)):
        channels = [float(channel) for channel in value[:4]]
        color = QColor(int(channels[0]), int(channels[1]), int(channels[2]))
        alpha = channels[3] if len(channels) > 3 else 255.0
        color.setAlphaF(max(0.0, min(1.0, alpha / 255.0 if alpha > 1.0 else alpha)))
        return color
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith(("rgba(", "rgb(")):
            inner = text[text.index("(") + 1:text.rindex(")")]
            parts = [float(part) for part in inner.split(",")]
            color = QColor(int(parts[0]), int(parts[1]), int(parts[2]))
            if len(parts) > 3:
                alpha = parts[3]
                color.setAlphaF(max(0.0, min(1.0,
                                             alpha / 255.0 if alpha > 1.0 else alpha)))
            return color
        color = QColor(text)
        if color.isValid():
            return color
    return QColor("#808080")


def _tinted(color: QColor, opacity: float) -> QColor:
    """``color`` as a translucent fill at ``opacity`` (any alpha the palette
    already carried is kept, so a tint never reads stronger than its base)."""
    out = QColor(color)
    out.setAlphaF(out.alphaF() * opacity)
    return out


def _column_center(col: int, width: float, scale: float) -> float:
    """Center x of day-grid column ``col``: col 0 is Saturday - the rightmost
    column under RTL - and col 6 is Friday, mirroring the real calendar."""
    return width - (CARD_SIDE_PADDING + CELL_PITCH_W / 2) * scale - col * CELL_PITCH_W * scale


def _draw_dot(painter: QPainter, x: float, y: float, radius: float,
              color: QColor) -> None:
    """One day dot: the same small circle for every day and every state."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(x, y), radius, radius)


def theme_card_pixmap(palette: dict, theme_name: str) -> QPixmap:
    """The picker card art: the calendar abstracted to its silhouette in
    ``palette``'s colors, at the "1b" reference's proportions.

    Top to bottom: an abstract header - a chevron tick at each end and a short
    rounded bar as the title, no text - then seven weekday dashes with Friday
    already holiday-colored, five equal weeks of day dots (one dot size
    everywhere: a day's state rides a tinted rounded square BEHIND the dot -
    the in-month Fridays in holiday red, the trailing out-of-month Friday as
    the muted Friday, the event day in the event color, today's fill, the
    selected day's fill plus a thin text ring - never a different dot shape),
    out-of-month days as plain grey dots, and, after a divider line, the
    theme's own name centered inside the card in Inter semibold. Every
    element is an ordinary palette key, so the card is a faithful miniature of
    what the theme does to the app."""
    width, height = CARD_WIDTH, CARD_HEIGHT
    scale = width / REF_CARD_WIDTH
    pixmap = QPixmap(int(width * CARD_DPR), int(height * CARD_DPR))
    pixmap.setDevicePixelRatio(CARD_DPR)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    text = _qcolor(palette, "TEXT_COLOR")
    accent = _qcolor(palette, "ACCENT_COLOR")
    holiday = _qcolor(palette, "HOLIDAY_COLOR")
    weekday = _qcolor(palette, "WEEKDAY_NAMES_COLOR")
    grey = _qcolor(palette, "GREY_COLOR")
    border = _qcolor(palette, "CALENDAR_BORDER_COLOR")

    # The card body: the theme's own surface with its own subtle border, the
    # same pairing the calendar popup wears.
    card = QRectF(0.5, 0.5, width - 1, height - 1)
    card_path = QPainterPath()
    card_path.addRoundedRect(card, CARD_RADIUS * scale, CARD_RADIUS * scale)
    painter.fillPath(card_path, _qcolor(palette, "BACKGROUND_COLOR"))
    body_pen = QPen(border)
    body_pen.setWidthF(1.0)
    painter.setPen(body_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(card_path)

    # --- header: chevron ticks around a rounded title bar, no text --------
    tick = QColor(weekday)
    tick.setAlphaF(0.7)
    tick_pen = QPen(tick)
    tick_pen.setWidthF(1.3)
    tick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    tick_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(tick_pen)
    painter.drawLine(QPointF(15 * scale, (HEADER_CENTER_Y - 2) * scale),
                     QPointF(11 * scale, HEADER_CENTER_Y * scale))
    painter.drawLine(QPointF(11 * scale, HEADER_CENTER_Y * scale),
                     QPointF(15 * scale, (HEADER_CENTER_Y + 2) * scale))
    painter.drawLine(QPointF(width - 15 * scale, (HEADER_CENTER_Y - 2) * scale),
                     QPointF(width - 11 * scale, HEADER_CENTER_Y * scale))
    painter.drawLine(QPointF(width - 11 * scale, HEADER_CENTER_Y * scale),
                     QPointF(width - 15 * scale, (HEADER_CENTER_Y + 2) * scale))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(text)
    painter.drawRoundedRect(QRectF(width / 2 - 17 * scale,
                                   (HEADER_CENTER_Y - 2.5) * scale,
                                   34 * scale, 5 * scale),
                            2.5 * scale, 2.5 * scale)

    # --- weekday row: one short dash per column, Friday in the holiday color
    painter.setPen(Qt.PenStyle.NoPen)
    for col in range(7):
        center_x = _column_center(col, width, scale)
        painter.setBrush(holiday if col == 6 else weekday)
        painter.drawRoundedRect(QRectF(center_x - 4 * scale,
                                       (WEEKDAY_DASH_Y - 1) * scale,
                                       8 * scale, 2 * scale),
                                1 * scale, 1 * scale)

    # --- the five weeks: one dot size, states as tinted squares behind -----
    dot_radius = max(2.0, 0.025 * width) / 2.0
    today_fill = _qcolor(palette, "CALENDAR_TODAY_BG_COLOR")
    selected_fill = _qcolor(palette, "CALENDAR_SELECTED_BG_COLOR")
    for row, pattern in enumerate(_DAY_GRID):
        center_y = (GRID_TOP_Y + CELL_PITCH_H * (row + 0.5)) * scale
        for col, state in enumerate(pattern):
            center_x = _column_center(col, width, scale)
            state_rect = QRectF(center_x - (CELL_PITCH_W / 2 - CELL_INSET) * scale,
                                center_y - (CELL_PITCH_H / 2 - CELL_INSET) * scale,
                                (CELL_PITCH_W - 2 * CELL_INSET) * scale,
                                (CELL_PITCH_H - 2 * CELL_INSET) * scale)
            if state == "o":
                # Out-of-month, not a Friday: the same small dot, quiet grey,
                # no tint.
                _draw_dot(painter, center_x, center_y, dot_radius, grey)
                continue
            if state == "h":
                # The trailing out-of-month Friday: the real calendar's muted
                # Friday cell - a dimmer holiday dot over a whisper of the
                # same hue, so the column still reads as Fridays at a glance.
                fill, dot = (_tinted(holiday, MUTED_HOLIDAY_FILL_OPACITY),
                            _tinted(holiday, MUTED_HOLIDAY_DOT_OPACITY))
            elif state == "H":
                # The in-month Fridays - the only holiday-colored cells.
                fill, dot = _tinted(holiday, STATE_FILL_OPACITY), holiday
            elif state == "E":
                # The event day wears the event color - the same gear the real
                # calendar colors its event days with (green on Default).
                fill, dot = _tinted(accent, EVENT_FILL_OPACITY), accent
            elif state == "T":
                fill, dot = today_fill, text
            elif state == "S":
                fill, dot = selected_fill, text
            else:
                fill, dot = None, text
            if fill is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                painter.drawRoundedRect(state_rect, STATE_RADIUS * scale,
                                        STATE_RADIUS * scale)
            if state == "S":
                # The selected day: its cell's own fill plus a thin text ring,
                # never a different dot shape or a marker under it.
                ring = QPen(text)
                ring.setWidthF(1.0)
                painter.setPen(ring)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(state_rect, STATE_RADIUS * scale,
                                        STATE_RADIUS * scale)
            _draw_dot(painter, center_x, center_y, dot_radius, dot)

    # --- divider, then the theme's own name inside the card -----------------
    divider_pen = QPen(border)
    divider_pen.setWidthF(1.0)
    painter.setPen(divider_pen)
    painter.drawLine(QPointF(CARD_SIDE_PADDING * scale, DIVIDER_Y * scale),
                     QPointF(width - CARD_SIDE_PADDING * scale, DIVIDER_Y * scale))

    name_font = QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY)
    name_font.setPixelSize(max(1, int(NAME_FONT_PX * scale)))
    name_font.setWeight(QFont.Weight.DemiBold)
    metrics = QFontMetrics(name_font)
    available = width - 2 * CARD_SIDE_PADDING * scale
    elided = metrics.elidedText(theme_name, Qt.TextElideMode.ElideRight,
                                int(available))
    painter.setFont(name_font)
    painter.setPen(text)
    painter.drawText(QRectF(CARD_SIDE_PADDING * scale, NAME_TOP_Y * scale,
                            available, 12 * scale),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                     elided)
    painter.end()
    return pixmap


# --- favorites: the star ---------------------------------------------------------


def star_path(center_x: float, center_y: float, outer_radius: float,
              inner_ratio: float = 0.46) -> QPainterPath:
    """A five-point star centered on a point, one tip straight up."""
    path = QPainterPath()
    for step in range(10):
        radius = outer_radius if step % 2 == 0 else outer_radius * inner_ratio
        angle = -math.pi / 2 + step * math.pi / 5
        point = QPointF(center_x + radius * math.cos(angle),
                        center_y + radius * math.sin(angle))
        if step == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def draw_star(painter: QPainter, center: QPointF, outer_radius: float, *,
              filled: bool, outline: QColor) -> None:
    """One favorite star: solid gold when favorited, an outline otherwise."""
    path = star_path(center.x(), center.y(), outer_radius)
    pen = QPen(QColor(FAVORITE_COLOR) if filled else outline)
    pen.setWidthF(max(1.0, outer_radius * 0.17))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor(FAVORITE_COLOR) if filled else Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


class FavoriteStarButton(QPushButton):
    """A round favorite-toggle button: gold and solid while checked, an
    outline otherwise. (The gallery currently favorites through the card
    badges, so the window places none; it is kept ready for a star beside the
    apply button or on a name caption.)

    It is painted, not a font glyph, so it needs no icon font and renders the
    same everywhere. ``set_checked`` moves the state without emitting
    ``clicked`` - only the user's click should write a preference."""

    SIZE = 34

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("افزودن به علاقه‌مندی‌ها")
        self._off_color = QColor("#808080")
        self._hover_color = QColor(128, 128, 128, 40)

    def set_checked(self, checked: bool) -> None:
        self.setChecked(checked)
        self.update()

    def set_colors(self, off_color: QColor, hover_color: QColor) -> None:
        self._off_color = QColor(off_color)
        self._hover_color = QColor(hover_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._hover_color)
            painter.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        draw_star(painter, QPointF(self.width() / 2, self.height() / 2 + 0.5),
                  self.width() * 0.30, filled=self.isChecked(),
                  outline=self._off_color)
        painter.end()


# --- controls ---------------------------------------------------------------------


def _mix(base: QColor, other: QColor, amount: float) -> QColor:
    """``base`` blended toward ``other`` by ``amount`` (0 = base, 1 = other)."""
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(base.red() + (other.red() - base.red()) * amount),
        round(base.green() + (other.green() - base.green()) * amount),
        round(base.blue() + (other.blue() - base.blue()) * amount))


class SegmentedFilter(QWidget):
    """The همه / روشن / تاریک / ★ filter: ONE connected bar with a highlight
    that slides between the segments.

    The gallery filters through these stops, so the widget owns the mode and
    emits it as a string. It is painted by hand rather than assembled from
    buttons - a single rounded track, one accent highlight that glides to the
    chosen segment (the label colors cross-fade with the highlight's overlap,
    so a label never flashes the wrong polarity mid-slide), a faint hover fill
    on the segment under the cursor, and an accent ring while the bar holds
    keyboard focus (left/right arrows step the selection, mirrored under RTL).
    Segment order follows the layout direction, like the buttons it replaces:
    the first stop («همه») sits at the reading start."""

    filterChanged = pyqtSignal(str)

    HEIGHT = 40
    INSET = 4               # air between the track and the highlight
    TEXT_PADDING = 22       # either side of a text label
    ICON_WIDTH = 44         # the star segment: the 16px glyph + 14px air a side
    TRACK_RADIUS = 14.0
    FONT_PX = 14
    STAR_RADIUS = 8.0
    HOVER_INSET = 3         # gap between a hover fill and the highlight
    SLIDE_MS = 190

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mode = FILTER_ALL
        self._hovered: Optional[str] = None
        self._palette: Optional[dict] = None
        self._font = QFont(APP_CONFIG.FONT_FAMILY)
        self._font.setPixelSize(self.FONT_PX)
        self._font.setBold(True)
        self._widths = self._measure_segments()
        self.setFixedHeight(self.HEIGHT)
        self.setFixedWidth(int(sum(self._widths.values())) + 2 * self.INSET)
        self._highlight = self._segment_rect(self._mode)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(self.SLIDE_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_slide)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("فیلتر تم‌ها")
        self.update_styles()

    # --- geometry --------------------------------------------------------------

    def _measure_segments(self) -> dict:
        metrics = QFontMetrics(self._font)
        widths = {}
        for mode in FILTER_ORDER:
            label = _FILTER_LABELS[mode]
            widths[mode] = (float(metrics.horizontalAdvance(label)
                                  + 2 * self.TEXT_PADDING)
                            if label else float(self.ICON_WIDTH))
        return widths

    def sizeHint(self) -> QSize:
        return QSize(self.width(), self.HEIGHT)

    def _segment_rect(self, mode: str) -> QRectF:
        """Segment ``mode``'s rectangle inside the track, mirrored under RTL."""
        offset = float(self.INSET)
        for candidate in FILTER_ORDER:
            if candidate == mode:
                break
            offset += self._widths[candidate]
        width = self._widths[mode]
        x = (self.width() - offset - width) if self.isRightToLeft() else offset
        return QRectF(x, self.INSET, width, self.HEIGHT - 2 * self.INSET)

    def highlight_rect(self) -> QRectF:
        """Where the highlight is right now (mid-slide included)."""
        return QRectF(self._highlight)

    def target_highlight_rect(self) -> QRectF:
        """Where the highlight is heading: the chosen segment's rectangle."""
        return self._segment_rect(self._mode)

    def settle(self) -> None:
        """Finish any slide in flight and park the highlight on the choice."""
        self._animation.stop()
        self._highlight = self._segment_rect(self._mode)
        self.update()

    def segment_at(self, x: float) -> Optional[str]:
        for mode in FILTER_ORDER:
            rect = self._segment_rect(mode)
            if rect.left() <= x < rect.right():
                return mode
        return None

    # --- state -----------------------------------------------------------------

    def current_filter(self) -> str:
        return self._mode

    def set_filter(self, mode: str) -> None:
        """Programmatic filter change (tests, future restore): slides the
        highlight and emits exactly like a click would."""
        if mode in _FILTER_LABELS:
            self._choose(mode)

    def _choose(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        target = self._segment_rect(mode)
        if self.isVisible():
            self._animation.stop()
            self._animation.setStartValue(QRectF(self._highlight))
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._highlight = target
        self.update()
        self.filterChanged.emit(mode)

    def _on_slide(self, value) -> None:
        self._highlight = QRectF(value)
        self.update()

    # --- input -----------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mode = self.segment_at(event.position().x())
            if mode is not None:
                self._choose(mode)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        hovered = self.segment_at(event.position().x())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered is not None:
            self._hovered = None
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        if self.isRightToLeft():
            step = -step  # the arrow points the way the bar reads
        index = FILTER_ORDER.index(self._mode) + step
        if 0 <= index < len(FILTER_ORDER):
            self._choose(FILTER_ORDER[index])
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._animation.state() != QVariantAnimation.State.Running:
            self._highlight = self._segment_rect(self._mode)

    def showEvent(self, event):
        super().showEvent(event)
        self.settle()

    def hideEvent(self, event):
        # Never leave a slide running against a hidden (or closing) widget.
        self.settle()
        super().hideEvent(event)

    # --- painting --------------------------------------------------------------

    def update_styles(self) -> None:
        self._palette = dict(APP_CONFIG.get_current_palette())
        self.update()

    def paintEvent(self, event):
        palette = self._palette or APP_CONFIG.get_current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        text = QColor(palette["TEXT_COLOR"])
        accent = QColor(palette["ACCENT_COLOR"])
        on_accent = QColor(on_accent_text_color(palette["ACCENT_COLOR"]))
        border = QColor(palette["CALENDAR_BORDER_COLOR"])
        quiet_text = _mix(text, QColor(palette["BACKGROUND_COLOR"]), 0.15)

        # The track: one rounded bar behind every segment.
        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(accent if self.hasFocus() else border, 1.0))
        painter.setBrush(QColor(palette["INPUT_BG_COLOR"]))
        painter.drawRoundedRect(track, self.TRACK_RADIUS, self.TRACK_RADIUS)

        inner_radius = self.TRACK_RADIUS - self.INSET

        # A hover fill on an idle segment under the cursor. It is inset a
        # further HOVER_INSET so it never touches the highlight beside it (two
        # flush blobs read as one shape: the hover looked "inside" the
        # selection), and it fades out as the highlight slides over it.
        # HOVER_BG is an rgba(...) string QColor cannot parse (it would
        # resolve to opaque black); _qcolor folds the notations.
        if self._hovered is not None and self._hovered != self._mode:
            hovered_rect = self._segment_rect(self._hovered)
            overlap = hovered_rect.intersected(self._highlight)
            covered = (overlap.width() / hovered_rect.width()
                       if overlap.isValid() and hovered_rect.width() else 0.0)
            tint = _qcolor(palette, "HOVER_BG")
            tint.setAlphaF(tint.alphaF() * (1.0 - covered))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            hover_radius = max(2.0, inner_radius - self.HOVER_INSET)
            painter.drawRoundedRect(
                hovered_rect.adjusted(self.HOVER_INSET, self.HOVER_INSET,
                                      -self.HOVER_INSET, -self.HOVER_INSET),
                hover_radius, hover_radius)

        # The sliding highlight.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(self._highlight, inner_radius, inner_radius)

        # Labels: each blends toward the on-accent color by how much of its
        # segment the highlight covers right now.
        painter.setFont(self._font)
        for mode in FILTER_ORDER:
            rect = self._segment_rect(mode)
            overlap = rect.intersected(self._highlight)
            covered = (overlap.width() / rect.width()
                       if overlap.isValid() and rect.width() else 0.0)
            color = _mix(quiet_text, on_accent, covered)
            label = _FILTER_LABELS[mode]
            if label:
                painter.setPen(color)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            else:
                # Drawn in the label color, never gold: gold on the accent
                # highlight would fight it. Solid while the highlight is on it.
                path = star_path(rect.center().x(), rect.center().y(), self.STAR_RADIUS)
                star_pen = QPen(color)
                star_pen.setWidthF(1.2)
                star_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(star_pen)
                painter.setBrush(color if covered > 0.5 else Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
        painter.end()
