"""
Theme Gallery Window (the calendar + side picker)
--------------------------------------------------

The theme gallery: the real calendar on the left of the window, the theme
picker on its right. The left panel is the actual popup itself -
``PersianCalendarWidget`` rendered through the shared
``CalendarShotRenderer`` at its own 305x395 size: nothing squished, nothing
redrawn to resemble it - so the preview is pixel-for-pixel the calendar the
tray opens (the user's live month, holidays and events included), re-rendered
in whichever theme is previewed. The commit button («اعمال») sits directly
under the preview, as wide as the calendar and dressed like the rest of the
chrome in the session's baseline theme - it stays put while previews come and
go, and re-dresses only when «اعمال» re-baselines the session onto the applied
theme. The filter bar rides the column above the calendar, as wide as it. The
picker runs the full height of the window beside them. There is no cancel
button: the caption bar's ✕ (or Esc) already closes the window and discards an
un-applied preview. (The preview carries no theme-name caption: the
highlighted card in the picker names the theme being previewed.)

Previews stay inside this window: clicking a card re-renders the panel in
the clicked theme and nothing else - the
application, the tray, every other window keep the theme they already have,
so «اعمال» is a real decision rather than a suggestion ratifying what already
happened.

Any theme can be starred: a small star badge on each card shows (and,
clicked, toggles) its state, and the star segment of the filter bar (همه /
روشن / تاریک / ★) narrows the picker to favorites.
Favorites are bookmarks, not part of the apply/cancel session - they persist
the moment a star is toggled and a close never discards them.

«اعمال» changes the theme for real - the controller persists and applies it -
and deliberately does NOT close the gallery: the session re-baselines onto the
applied theme (the stage re-dresses, the revert target and the dashed
outline move to it) so the user can keep browsing from there; a later close
reverts nothing, and closing without «اعمال» discards an un-applied preview.

The right panel is a compact grid of mini-calendar cards: one card per theme,
the calendar abstracted to its silhouette in that palette's colors - the
abstract header, the weekday dashes, five equal weeks of one-size day dots
over tinted state squares, and the theme's own name under a divider inside
the card. It scrolls deliberately: one card row per wheel notch, and a
re-shown window sits exactly where the user left it (see ``_PickerGrid``) -
never re-centered onto the previewed card.

The window's own chrome - painted background, caption bar, picker, and the
apply button - stays dressed in the session's baseline theme (see
``_chrome_palette``): only the calendar panel repaints into the previewed
theme, so its colors are judged against a constant stage instead of fighting
a surround that repainted itself into the very theme being previewed - and
the action never pretends a preview already happened.

The window reports three theme intents to the controller (preview / commit /
cancel - the last fired by closing) plus the favorites list whenever it
changes, and re-reads the active theme on every show - the controller reuses
a visible instance via ``_show_or_raise``.
"""
from contextlib import contextmanager
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QPainter, QPen, QPixmap)
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem,
                             QPushButton, QSizePolicy, QStyledItemDelegate,
                             QStyle, QVBoxLayout, QWidget)

from config import APP_CONFIG
from ui.widgets.gallery_widgets import (CARD_HEIGHT, CARD_RADIUS, CARD_WIDTH,
                                        FILTER_FAVORITES, SegmentedFilter, draw_star,
                                        filtered_catalog, frame_accent_color,
                                        theme_card_pixmap)
from ui.widgets.theme_shot import CalendarShotRenderer
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles
from utils.logger import setup_logging
from utils.ui_helpers import (accent_button_stylesheet,
                              rgba_string, scrollbar_stylesheet)
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

# The left column stacks the filter bar, the real popup at its own size
# (305x395) and the apply button; the right panel takes whatever width is
# left for four mini-calendar card columns.
PANEL_WIDTH = APP_CONFIG.CALENDAR_WIDTH
PANEL_HEIGHT = APP_CONFIG.CALENDAR_HEIGHT

# The apply button: as wide as the calendar, one gap beneath it. (Cancel is
# the caption bar's ✕; a second button for the same thing was redundant.)
ACTION_BUTTON_HEIGHT = 46
ACTION_BUTTON_RADIUS = 15
LEFT_COLUMN_GAP = 10
# The filter bar rides the column's top, as wide as the calendar under it.
LEFT_COLUMN_HEIGHT = (SegmentedFilter.HEIGHT + LEFT_COLUMN_GAP
                      + PANEL_HEIGHT + LEFT_COLUMN_GAP + ACTION_BUTTON_HEIGHT)

# The picker grid's rhythm (the "1b" reference spacing, stated at the 118px
# card): 14px between card columns, 18px between card rows, and about 14px of
# air above the first row (the art sits CARD_TOP_PAD into its cell, so the
# leftover below each card joins the next cell's pad into the 18px row gap).
# Every state outline rides CARD_OUTLINE_OFFSET outside the card's own edge,
# so these gaps are what keep two outlined cards from ever touching: the row
# gap leaves exactly 12px between neighbours, the column gap 8px.
CARD_COLUMN_GAP = 14
CARD_ROW_GAP = 18
CARD_TOP_PAD = 14
CARD_OUTLINE_OFFSET = 3.0
CARD_CELL_WIDTH = CARD_WIDTH + CARD_COLUMN_GAP
CARD_CELL_HEIGHT = CARD_HEIGHT + CARD_ROW_GAP

# Wide enough that the picker fits four card columns (cell + gaps, scrollbar
# in place) beside the calendar, and tall enough for the left column: 14 top
# margin + 30 caption bar + 10 spacing + 501 columns (filter 40 + 10 gap +
# calendar 395 + 10 gap + 46 apply button) + 16 bottom margin.
WINDOW_WIDTH, WINDOW_HEIGHT = 920, 571

_ROLE_KEY = Qt.ItemDataRole.UserRole
_ROLE_PALETTE = Qt.ItemDataRole.UserRole + 1

# The favorite badge: a small round chip straddling a card's top corner (the
# card's reading-start side is crowded by the header chevron, so the badge
# rides the corner itself and never covers the art). It shows on a favorited
# card always, and on the hovered or previewed card as an invitation.
BADGE_RADIUS = 8.5
BADGE_STAR_RADIUS = 5.4
BADGE_HIT_PAD = 3.0


def card_art_rect(cell: QRect) -> QRectF:
    """Where a card's artwork sits inside its grid cell (the delegate paints
    there and the grid hit-tests the favorite badge against the same rect)."""
    return QRectF(cell.x() + (cell.width() - CARD_WIDTH) / 2,
                  cell.y() + CARD_TOP_PAD, CARD_WIDTH, CARD_HEIGHT)


def favorite_badge_rect(art_rect: QRectF) -> QRectF:
    """The badge's bounding square: centered just inside the card's top-right
    corner so the chip hangs off the corner like a pin."""
    center = QPointF(art_rect.right() - 1.0, art_rect.top() + 1.0)
    return QRectF(center.x() - BADGE_RADIUS, center.y() - BADGE_RADIUS,
                  2 * BADGE_RADIUS, 2 * BADGE_RADIUS)


@contextmanager
def _dressed_as(palette: dict):
    """Briefly make ``APP_CONFIG`` serve ``palette`` to whoever styles itself
    from the live config (the title bar, the shared controls).

    The gallery keeps its chrome in the session's baseline theme while
    previews repaint the calendar panel, so the preview is always judged
    against a constant stage. The swap is the same class-level mechanism the
    card renderer uses - an instance write would shadow the attribute
    ``set_theme`` updates - and the ``finally`` restores the live palette even
    when styling raises."""
    config_cls = type(APP_CONFIG)
    previous = config_cls.current_palette
    config_cls.current_palette = palette
    try:
        yield
    finally:
        config_cls.current_palette = previous


# --- the calendar panel ------------------------------------------------------------

class _CalendarShotView(QWidget):
    """A passive surface that paints one of the renderer's DPR-aware renders
    whole, at a point, through the painter transform - the same drawing form
    the card artwork uses.

    A QLabel would not do: it rescales a 2x pixmap down to the label's own
    device pixel ratio on assignment, so a scaled Windows display would
    upsample a 1x copy and soften the preview. Drawing the pixmap this way
    keeps every device pixel of the render at any screen scale."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._render = QPixmap()
        self.setFixedSize(PANEL_WIDTH, PANEL_HEIGHT)

    def sizeHint(self) -> QSize:
        return QSize(PANEL_WIDTH, PANEL_HEIGHT)

    def set_render(self, pixmap: QPixmap):
        self._render = pixmap
        self.update()

    def paintEvent(self, event):
        if self._render.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(QPointF(0, 0), self._render)
        painter.end()


class RealCalendarPanel(QWidget):
    """The gallery's preview surface: the actual calendar popup, rendered
    whole at its own size by the shared ``CalendarShotRenderer``.

    Deliberately a render, not a live ``PersianCalendarWidget``: a preview is
    something you look at, not a second calendar to manage events from, and a
    static image of the real window carries every surface - header, weekday
    row, day states, the popup's own rounded chrome - without any editing
    surface ever being reachable. The render is regenerated whenever the
    previewed theme (or the session) changes, so what it shows is exactly
    what the tray's popup would show. The panel owns no controls: the
    apply button beneath it belongs to the window."""

    def __init__(self, holidays, events, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(PANEL_WIDTH)
        # The column is exactly the calendar - no dead space trailing the
        # render, no clipped art below it.
        self.setFixedHeight(PANEL_HEIGHT)
        # The engine behind the preview panel's render, asked for the
        # unscaled whole-window artwork of the previewed theme.
        self._renderer = CalendarShotRenderer(holidays=holidays, events=events,
                                              parent=self)
        self._rendered_palette: Optional[dict] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.shot_view = _CalendarShotView()
        root.addWidget(self.shot_view)

    # --- preview surface -----------------------------------------------------

    def present_palette(self, key: str, palette: dict):
        """(Re)render the calendar in ``palette`` and show it whole.

        The early return keeps repeated styling passes cheap: the render only
        rebuilds when the palette object actually moved (a preview or a
        revert); ``reset_session`` clears it so a new session re-reads the
        live stores even when the theme did not change."""
        if palette is self._rendered_palette:
            return
        self.shot_view.set_render(self._renderer.full_window_artwork(key, palette))
        self._rendered_palette = palette

    def reset_session(self):
        """A new gallery session: drop the cached render and re-read the live
        data (see ``CalendarShotRenderer.reset_session``)."""
        self._renderer.reset_session()
        self._rendered_palette = None


# --- the picker grid ----------------------------------------------------------------

class _PickerGrid(QListWidget):
    """The theme picker: a QListWidget tuned for deliberate, calm scrolling.

    The stock icon view ships two behaviours that read as "jumping" here.
    One is the wheel step: the per-pixel view sets its single step from the
    grid cell height, and a wheel notch multiplies that by three - three card
    rows, four-fifths of the viewport, gone in one flick. ``wheelEvent``
    therefore scrolls exactly one card row per notch (sub-notch deltas from
    high-resolution touchpads accumulate instead of dropping).

    The other is silent re-centering: making an item current - which every
    programmatic selection does - scrolls the view to that item, so a
    re-shown window would leap to the previewed card instead of sitting
    where the user left it browsing. ``hold_viewport()`` suppresses exactly
    that path for the window's programmatic selections; keyboard navigation
    and real clicks keep their scroll-into-view (a keyboard walker the view
    ignores would be stranded off-screen)."""

    favoriteToggleRequested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._viewport_held = False
        self._wheel_remainder = 0
        # Shown over the empty grid (the favorites filter with no stars yet).
        self.empty_label = QLabel(self.viewport())
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.empty_label.hide()

    def set_empty_message(self, message: Optional[str]):
        """Show ``message`` over the grid, or hide the label with ``None``."""
        if message:
            self.empty_label.setText(message)
            self._place_empty_label()
            self.empty_label.show()
        else:
            self.empty_label.hide()

    def _place_empty_label(self):
        rect = self.viewport().rect().adjusted(24, 0, -24, 0)
        self.empty_label.setGeometry(rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_empty_label()

    def _badge_key_at(self, pos: QPointF) -> Optional[str]:
        """The theme key whose favorite badge sits under ``pos``, if any."""
        index = self.indexAt(pos.toPoint())
        if not index.isValid():
            return None
        badge = favorite_badge_rect(card_art_rect(self.visualRect(index)))
        badge = badge.adjusted(-BADGE_HIT_PAD, -BADGE_HIT_PAD,
                               BADGE_HIT_PAD, BADGE_HIT_PAD)
        return index.data(_ROLE_KEY) if badge.contains(pos) else None

    def mousePressEvent(self, event):
        # A click on a card's star badge toggles its favorite and nothing
        # else: it must not select (and so preview) the card.
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._badge_key_at(event.position())
            if key is not None:
                self.favoriteToggleRequested.emit(key)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # The badge's second click of a quick pair is a toggle too, not a
        # double-click-to-apply on the card underneath it.
        key = self._badge_key_at(event.position())
        if key is not None:
            self.favoriteToggleRequested.emit(key)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    @contextmanager
    def hold_viewport(self):
        """Make the current item move without the view scrolling to it."""
        self._viewport_held = True
        try:
            yield
        finally:
            self._viewport_held = False

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if self._viewport_held:
            return
        super().scrollTo(index, hint)

    def wheelEvent(self, event):
        notches = event.angleDelta().y()
        if notches == 0:
            super().wheelEvent(event)
            return
        event.accept()
        # One notch = one card row, row-aligned: the grid steps instead of
        # leaping, and every notch lands on the same rhythm the cards pitch.
        self._wheel_remainder += notches
        steps, self._wheel_remainder = divmod(self._wheel_remainder, 120)
        if steps:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - steps * CARD_CELL_HEIGHT)


# --- the mini-calendar card delegate ------------------------------------------------

class ThemeCardDelegate(QStyledItemDelegate):
    """Paints one picker card: the mini-calendar artwork with the theme's
    name already inside it, the selected (clicked) state and the
    session-baseline marker.

    The artwork dresses in the card's own palette - that IS the preview -
    name included, so no text ever swaps into an accent color. The clicked
    card - the previewed theme - carries the selection: a solid accent frame
    riding CARD_OUTLINE_OFFSET off the card's edge, tracing its corner curve
    (the "1b" gaps are sized so two outlined cards never touch). While the
    preview differs from the session's baseline (the theme it opened on, or
    the last one «اعمال» put on), that baseline keeps a quiet dashed outline
    in the stage's border color - the revert target stays visible without
    ever reading as the selection. A hover on any other card is a thin
    translucent accent frame: affordance only, because a hover must never
    preview. Every frame's accent is contrast-checked against the stable
    stage (``frame_accent_color``) so it reads on light and dark stages
    alike."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.preview_key: Optional[str] = None
        self.original_key: Optional[str] = None
        # The stable palette the frames dress against; the window keeps it in
        # the session's baseline theme (see ThemeGalleryWindow.update_styles).
        self.chrome_palette: Optional[dict] = None
        # The gallery's favorite keys (the window shares its own set, so a
        # toggle shows on the next paint with no copying).
        self.favorites: set = set()
        self._cards: dict = {}  # theme key -> QPixmap

    def set_state(self, preview_key: Optional[str], original_key: Optional[str]):
        self.preview_key = preview_key
        self.original_key = original_key

    def _card(self, key: str, palette: dict) -> QPixmap:
        cached = self._cards.get(key)
        if cached is None:
            name = APP_CONFIG.theme_display_name(key)
            cached = theme_card_pixmap(palette, name)
            self._cards[key] = cached
        return cached

    def sizeHint(self, option, index):
        return QSize(CARD_CELL_WIDTH, CARD_CELL_HEIGHT)

    def paint(self, painter, option, index):
        key = index.data(_ROLE_KEY)
        palette = index.data(_ROLE_PALETTE)
        if key is None or palette is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_original = key == self.original_key
        is_preview = key == self.preview_key

        # The art sits CARD_TOP_PAD into its cell: the "1b" spacing's ~14px of
        # air above the first row, with the leftover below joining the next
        # cell's pad into the 18px row gap.
        art_rect = card_art_rect(option.rect)

        # The artwork first: the opaque card fills its whole rectangle, and
        # the state frames ride OFF its edge by CARD_OUTLINE_OFFSET - a frame
        # painted underneath would lose its inner half to the card's own
        # surface, and the offset keeps the outline clear of the art it marks.
        painter.drawPixmap(art_rect.topLeft().toPoint(), self._card(key, palette))
        # Every state frame traces this offset rectangle at the card's own
        # corner curve (radius grown by the same offset, so the outline stays
        # parallel to the card's rounded edge).
        outline = art_rect.adjusted(-CARD_OUTLINE_OFFSET, -CARD_OUTLINE_OFFSET,
                                    CARD_OUTLINE_OFFSET, CARD_OUTLINE_OFFSET)
        outline_radius = CARD_RADIUS + CARD_OUTLINE_OFFSET

        chrome = self.chrome_palette or APP_CONFIG.get_current_palette()
        # The frames ride the card's edge on the stable stage, so their accent
        # is contrast-checked against that stage (see frame_accent_color): a
        # bright accent on a light stage would read as no indicator at all.
        frame_color = frame_accent_color(palette, chrome)
        if is_preview:
            # The clicked card's selection: the card's own accent (contrast-safe
            # on the stage), solid and framed around the whole card.
            pen = QPen(frame_color)
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(outline, outline_radius, outline_radius)
        elif is_original:
            # The session's baseline: a quiet dashed outline in the stage's own
            # border color. It answers "what does closing go back to?" and can
            # never be mistaken for the selection's accent ring.
            pen = QPen(QColor(chrome["CALENDAR_BORDER_COLOR"]))
            pen.setWidthF(1.4)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 3])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(outline, outline_radius, outline_radius)
        elif hovered:
            # Hover is affordance, never a preview: a thin translucent frame in
            # the contrast-safe accent that vanishes when the cursor moves on.
            frame = QColor(frame_color)
            frame.setAlphaF(0.5)
            pen = QPen(frame)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(outline, outline_radius, outline_radius)

        # The favorite badge rides on top of the frames: always there on a
        # favorite, an invitation on the hovered or previewed card.
        is_favorite = key in self.favorites
        if is_favorite or hovered or is_preview:
            self._paint_badge(painter, art_rect, chrome, is_favorite)

        painter.restore()

    def _paint_badge(self, painter, art_rect: QRectF, chrome: dict,
                     is_favorite: bool):
        """The star chip on a card's corner, dressed in the stable stage so it
        reads the same on every card: the stage's surface and border behind a
        gold star (favorite) or a quiet outlined one (invitation)."""
        rect = favorite_badge_rect(art_rect)
        painter.setPen(QPen(QColor(chrome["CALENDAR_BORDER_COLOR"]), 1.0))
        painter.setBrush(QColor(chrome["CALENDAR_BACKGROUND_COLOR"]))
        painter.drawEllipse(rect)
        muted = QColor(chrome["TEXT_COLOR"])
        muted.setAlphaF(0.6)
        draw_star(painter, rect.center() + QPointF(0, 0.4), BADGE_STAR_RADIUS,
                  filled=is_favorite, outline=muted)


# --- the window --------------------------------------------------------------------

class ThemeGalleryWindow(BaseFramelessWindow):
    """The theme gallery: the real calendar preview beside the theme picker."""

    TASKBAR_ICON = True  # a minimized gallery must stay reachable

    def __init__(self,
                 on_preview: Callable[[str], None],
                 on_commit: Callable[[str], None],
                 on_cancel: Callable[[str], None],
                 current_key_provider: Callable[[], str],
                 session_original_provider: Optional[Callable[[], str]] = None,
                 holidays: Callable[[], dict] | dict | None = None,
                 events: Callable[[], dict] | dict | None = None,
                 favorites_provider: Optional[Callable[[], Iterable[str]]] = None,
                 on_favorites_changed: Optional[Callable[[list], None]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("گالری تم‌ها")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._on_preview = on_preview
        self._on_commit = on_commit
        self._on_cancel = on_cancel
        self._current_key_provider = current_key_provider
        self._session_original_provider = (session_original_provider
                                           or current_key_provider)
        self._favorites_provider = favorites_provider
        self._on_favorites_changed = on_favorites_changed
        # The favorite keys, shared with the card delegate. Read from the
        # provider at construction and on every show; written back through
        # ``on_favorites_changed`` on every toggle.
        self._favorites: set = set()
        self._load_favorites()

        self._original_key: str = APP_CONFIG.Theme.DARK
        self._preview_key: str = self._original_key
        self._committed = False
        self._rebuilding = False
        # The stable theme the window's own chrome dresses in: the palette the
        # session started on, resolved on every show. None until then - the
        # constructor's styling pass falls back to the live palette, which at
        # build time is the same theme anyway.
        self._chrome_palette: Optional[dict] = None

        self._setup_ui(holidays, events)
        self.update_styles()
        apply_windows_styles(self)

    # --- UI ------------------------------------------------------------------

    def _setup_ui(self, holidays, events):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 16)
        main_layout.setSpacing(10)

        # The caption bar carries the title and the window buttons; the filter
        # rides above the preview column instead (see the left column).
        self.title_bar = WindowTitleBar(self.close, self.showMinimized,
                                        title="گالری تم‌ها")
        main_layout.addLayout(self.title_bar)

        columns = QHBoxLayout()
        columns.setSpacing(16)

        # The picker rides the window's right side (added first under RTL);
        # the calendar preview takes the left - the reading side, where the
        # eye lands first and the big artwork reads before the grid does.
        picker = QVBoxLayout()
        picker.setSpacing(8)
        self.grid = _PickerGrid()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setGridSize(QSize(CARD_CELL_WIDTH, CARD_CELL_HEIGHT))
        self.grid.setResizeMode(QListWidget.ResizeMode.Fixed)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(False)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Mouse tracking only feeds the delegate's hover affordance: previews
        # follow the click (currentItemChanged), never the cursor. The cell
        # already carries the "1b" gaps (14px columns / 18px rows), so the
        # view adds no spacing of its own.
        self.grid.setMouseTracking(True)
        self.grid.setSpacing(0)
        # RTL would mirror the vertical scrollbar to the column's left edge,
        # away from the cards it scrolls; the LTR pin keeps it at the window's
        # right edge, where every Windows list puts it.
        self.grid.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.grid.currentItemChanged.connect(self._on_current_changed)
        self.grid.itemDoubleClicked.connect(lambda _item: self._commit())
        self.grid.favoriteToggleRequested.connect(self._toggle_favorite)
        self._delegate = ThemeCardDelegate(self.grid)
        self._delegate.favorites = self._favorites
        self.grid.setItemDelegate(self._delegate)
        picker.addWidget(self.grid, 1)
        columns.addLayout(picker, 1)

        divider = QWidget()
        divider.setFixedWidth(1)
        divider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._divider = divider
        columns.addWidget(divider)

        # The left column: the filter bar, then the real calendar render with
        # the apply button under it - every row as wide as the calendar. The
        # panel is pure preview and owns no controls; the button dresses in
        # the session's baseline palette - the same stable theme as the chrome
        # around it - so it never moves with the browsing: previews change
        # nothing here, and it re-dresses only when «اعمال» re-baselines the
        # session onto the applied theme (or the window re-opens onto a new
        # one). Closing (the caption bar's ✕, Esc) is the way out without
        # applying.
        self.filter_control = SegmentedFilter()
        self.filter_control.setFixedWidth(PANEL_WIDTH)
        self.filter_control.filterChanged.connect(lambda _mode: self._refresh())
        self.calendar_panel = RealCalendarPanel(holidays, events)
        self.apply_button = QPushButton("اعمال")
        self.apply_button.setFixedSize(PANEL_WIDTH, ACTION_BUTTON_HEIGHT)
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.clicked.connect(self._commit)
        self.left_column = QWidget()
        self.left_column.setFixedSize(PANEL_WIDTH, LEFT_COLUMN_HEIGHT)
        left = QVBoxLayout(self.left_column)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(LEFT_COLUMN_GAP)
        left.addWidget(self.filter_control)
        left.addWidget(self.calendar_panel)
        left.addWidget(self.apply_button)
        columns.addWidget(self.left_column, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addLayout(columns, 1)

        # Populate once, at construction: the catalog and the filter cannot
        # change while the window is hidden, so a re-show must never rebuild
        # (a rebuild is a scroll reset - see showEvent).
        self._refresh()

    # --- population ----------------------------------------------------------

    def _refresh(self, *_args):
        self._rebuilding = True
        self.grid.clear()
        mode = self.filter_control.current_filter()
        for key, name, palette in filtered_catalog(mode, self._favorites):
            item = QListWidgetItem(name)
            item.setData(_ROLE_KEY, key)
            item.setData(_ROLE_PALETTE, palette)
            self.grid.addItem(item)
        self._select_key(self._preview_key)
        self._rebuilding = False
        self._ensure_preview_listed()
        # The favorites filter with no stars yet says how to add one.
        self.grid.set_empty_message(
            "هنوز تمی را به علاقه‌مندی‌ها اضافه نکرده‌اید.\n"
            "روی ستاره‌ی هر تم بزنید."
            if mode == FILTER_FAVORITES and self.grid.count() == 0 else None)

    def _ensure_preview_listed(self):
        """Keep the previewed theme under the active filter.

        A pick the filter excludes (a light theme pending under «تاریک») has
        no card to carry its selection, so the filter's first card is
        previewed instead and the intent is re-reported - the controller's
        pending pick must match what is on the preview panel. An empty grid
        (favorites with no stars yet) leaves the selection absent."""
        if self.grid.count() == 0:
            return
        listed = [self.grid.item(row).data(_ROLE_KEY)
                  for row in range(self.grid.count())]
        if self._preview_key in listed:
            return
        self._preview(listed[0])
        self._select_key(listed[0])

    # --- favorites -----------------------------------------------------------

    def _load_favorites(self):
        """Re-read the stored favorites into the shared set (in place, so the
        delegate's reference stays valid)."""
        known = {key for key, _name, _palette in APP_CONFIG.theme_catalog()}
        stored = self._favorites_provider() if self._favorites_provider else ()
        self._favorites.clear()
        self._favorites.update(key for key in stored if key in known)

    def favorite_keys(self) -> list:
        """The favorites, in gallery (catalog) order."""
        return [key for key, _name, _palette in APP_CONFIG.theme_catalog()
                if key in self._favorites]

    def is_favorite(self, key: str) -> bool:
        return key in self._favorites

    def _toggle_favorite(self, key: Optional[str]):
        """Star or unstar ``key`` and persist it at once.

        Under the favorites filter the card stays put until the filter next
        changes: rebuilding the grid on every unstar would snap the scroll
        position and make a mis-click impossible to take back."""
        if not key:
            return
        if key in self._favorites:
            self._favorites.discard(key)
        else:
            self._favorites.add(key)
        if self._on_favorites_changed is not None:
            self._on_favorites_changed(self.favorite_keys())
        self.grid.viewport().update()

    def _select_key(self, key: str):
        # Held: restoring the selection (filter change, re-show) must not
        # scroll the picker off the row the user was browsing.
        with self.grid.hold_viewport():
            for row in range(self.grid.count()):
                if self.grid.item(row).data(_ROLE_KEY) == key:
                    self.grid.setCurrentRow(row)
                    return
            self.grid.setCurrentRow(-1)

    # --- preview plumbing ----------------------------------------------------

    def _preview(self, key: str):
        """Preview ``key`` inside this window - and only inside it.

        Only the list's selection reaches this method - the click (or a
        keyboard move): hovering a card must never change the theme under
        the user's cursor. The panel is re-rendered straight from the theme
        map, so the clicked theme shows on the calendar while the application
        (this window's stage included) keeps the theme it already has: apply,
        not browsing, is what changes the app. The intent is still reported
        through ``on_preview`` - the controller remembers it as the session's
        in-flight pick without applying anything."""
        if not key or key == self._preview_key:
            return
        self._preview_key = key
        self._delegate.set_state(self._preview_key, self._original_key)
        self.grid.viewport().update()
        palette = APP_CONFIG._theme_map.get(key)
        if palette is not None:
            self.calendar_panel.present_palette(key, palette)
        # The apply button is deliberately NOT re-dressed here: it rides the
        # session's baseline (see update_styles), so it reads as the
        # theme the app actually wears until «اعمال» says otherwise.
        self._on_preview(key)

    def _on_current_changed(self, current: QListWidgetItem, _previous):
        if self._rebuilding or current is None:
            return
        self._preview(current.data(_ROLE_KEY))

    # --- actions -------------------------------------------------------------

    def _commit(self):
        """Apply the previewed theme for real - and keep the gallery open.

        «اعمال» is the decision, not the exit: the controller persists and
        applies the pick (the whole application changes now), and this window
        stays up for further browsing. The session re-baselines onto the
        applied theme - the stage re-dresses in it, the revert target and the
        dashed outline move to it - so a later close reverts nothing and a
        close only ever discards an un-applied preview."""
        if not self._preview_key:
            return
        self._committed = True
        # Re-baseline before the controller's apply sweep reaches this
        # window's update_styles, so the stage lands in the applied theme
        # directly instead of being styled twice in one frame.
        self._original_key = self._preview_key
        self._chrome_palette = (APP_CONFIG._theme_map.get(self._preview_key)
                                or APP_CONFIG.get_current_palette())
        self._delegate.set_state(self._preview_key, self._original_key)
        self._on_commit(self._preview_key)
        self.update_styles()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()  # closeEvent performs the revert
            return
        super().keyPressEvent(event)

    # --- window lifecycle ----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._committed = False
        self._load_favorites()
        self._original_key = self._session_original_provider()
        self._preview_key = self._current_key_provider()
        # The chrome theme of the session: everything but the preview surfaces
        # stays in this palette while previews come and go, so the preview is
        # always judged against the stage the gallery opened on.
        self._chrome_palette = (APP_CONFIG._theme_map.get(self._original_key)
                                or APP_CONFIG.get_current_palette())
        self._delegate.chrome_palette = self._chrome_palette
        self._delegate.set_state(self._preview_key, self._original_key)
        # A new session must re-read the user's live calendar data (events or
        # holidays added meanwhile, a month rollover) and drop stale renders -
        # the same contract the panel's render cache carries. The cards need
        # no such reset: their artwork is the month-free silhouette, so a
        # cached card can never go stale on a rollover. The picker is not
        # rebuilt either: the catalog and the filter cannot have changed
        # while the window was hidden, and a rebuild would reset the scroll -
        # the grid keeps its items and its position, and the selection is
        # restored without scrolling (see _PickerGrid.hold_viewport).
        self.calendar_panel.reset_session()
        self._select_key(self._preview_key)
        # A pending pick survives hiding (minimize) only under the active
        # filter; one the filter excludes is re-derived onto its first card.
        self._ensure_preview_listed()
        # Re-resolve the chrome after the session's original may have moved
        # (a commit since the last show): styling here rather than trusting
        # the constructor's pass keeps the stage honest on reuse.
        self.update_styles()

    def closeEvent(self, event):
        if not self._committed:
            self._on_cancel(self._original_key)
        super().closeEvent(event)

    # --- styling -------------------------------------------------------------

    def _painted_palette(self) -> dict:
        """The window's painted background and border follow the stable chrome
        palette, not the previewed theme (see ``BaseFramelessWindow.paintEvent``)."""
        return self._chrome_palette or APP_CONFIG.current_palette

    def _style_apply_button(self, palette: dict):
        """Dress «اعمال» in ``palette`` - the session's baseline theme, the
        same one the chrome around it wears (``update_styles`` passes the
        chrome palette; a commit re-baselines it). It carries the app's
        shared accent-button recipe: label polarity, hover and press."""
        self.apply_button.setStyleSheet(
            accent_button_stylesheet(palette, padding="0px 24px",
                                     font_size=16, radius=ACTION_BUTTON_RADIUS))

    def update_styles(self):
        """Style the chrome in the session's baseline theme, dress the
        preview surfaces in the previewed one.

        The stage (painted background, caption bar, picker and apply button)
        dresses in the theme the session is
        currently anchored on - the theme it opened on, or the last one
        «اعمال» put on - and never follows a preview. The preview surface -
        the calendar panel - renders the previewed theme's own palette from the map: exactly what the real popup would look like
        in it, never the application's live one (which a preview deliberately
        does not touch). The button riding the stage is the point: it
        keeps the theme the app actually wears until a commit changes it."""
        chrome = self._chrome_palette or APP_CONFIG.get_current_palette()
        with _dressed_as(chrome):
            self.title_bar.update_styles()
            self._divider.setStyleSheet(
                f"background-color: {chrome['CALENDAR_BORDER_COLOR']}; border: none;")
            self.filter_control.update_styles()
            self.grid.setStyleSheet(
                "QListWidget { background: transparent; border: none; outline: none; }"
                + scrollbar_stylesheet(chrome, width=10, bottom_margin=4,
                                         top_margin=CARD_TOP_PAD))
        self.grid.empty_label.setStyleSheet(
            f"QLabel {{ background: transparent; color: {rgba_string(chrome['TEXT_COLOR'], 0.65)};"
            f" font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; }}")
        preview_palette = (APP_CONFIG._theme_map.get(self._preview_key)
                           or APP_CONFIG.get_current_palette())
        self.calendar_panel.present_palette(self._preview_key, preview_palette)
        self._style_apply_button(chrome)
        # The frames ride the stable stage too.
        self._delegate.chrome_palette = chrome
        self.grid.viewport().update()
