"""Tests for the theme gallery feature: the palette-pack registry, the
on-accent text polarity rule, the mini-calendar card artwork, the gallery
window (the real calendar preview beside the theme picker), and the
controller-side wiring."""

import gc
import inspect

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStyle

from config import APP_CONFIG
from utils.ui_helpers import contrast_ratio, on_accent_text_color, QColor



@pytest.fixture(autouse=True)
def collect_garbage_between_tests():
    """Collect dead gallery windows at a safe point, not mid-paint.

    A closed gallery window from an earlier test can linger as a reference
    cycle; Python's cyclic GC may then run - triggered by an allocation inside
    the NEXT window's delegate paint - and delete that stale window's C++ side
    in the middle of the paint, which segfaults Qt ("Cannot destroy paint
    device that is being painted"). It reproduces on the untouched gallery
    code whenever test order shifts allocation timing. Collecting before and
    after every test keeps the collection at a point where nothing is painting.
    (The app is not exposed: the controller keeps the one gallery window
    referenced for as long as it exists.)"""
    gc.collect()
    yield
    gc.collect()


# The full palette shape every theme must carry (the stock dark theme and
# every gallery theme in themes.py; the gallery and every stylesheet builder
# index these).
REQUIRED_PALETTE_KEYS = {
    "TEXT_COLOR",
    "BACKGROUND_COLOR",
    "INPUT_BG_COLOR",
    "ACCENT_COLOR",
    "HOVER_BG",
    "SCROLLBAR_HANDLE_COLOR",
    "SCROLLBAR_GROOVE_COLOR",
    "HOLIDAY_COLOR",
    "GREY_COLOR",
    "WEEKDAY_NAMES_COLOR",
    "CALENDAR_BACKGROUND_COLOR",
    "CALENDAR_BORDER_COLOR",
    "CALENDAR_TODAY_BG_COLOR",
    "CALENDAR_TODAY_HOVER_BG_COLOR",
    "CALENDAR_SELECTED_BG_COLOR",
    "CALENDAR_SELECTED_HOVER_BG_COLOR",
    "MENU_BACKGROUND_COLOR",
    "MENU_BORDER_COLOR",
    "MENU_HOVER_COLOR",
    "GREGORIAN_DATE_HOVER_BG",
}


# --- registry --------------------------------------------------------------------


def test_pack_registry_loads_every_theme():
    """The single themes module registers 72 gallery palettes; with the stock
    dark theme the catalogue offers 73 selectable themes."""
    assert len(APP_CONFIG.EXTRA_THEMES) == 72
    assert len(APP_CONFIG.theme_catalog()) == 73
    assert "dracula" in APP_CONFIG._theme_map
    assert "nord_light" in APP_CONFIG._theme_map
    assert "kanagawa_wave" in APP_CONFIG._theme_map
    assert "oled_black" in APP_CONFIG._theme_map


def test_themes_module_is_the_single_palette_source():
    """Every palette - the stock dark theme included - lives in themes.py's
    registry, and the registry alone: no scattered pack modules exist for a
    theme to hide in."""
    import themes

    assert set(APP_CONFIG._theme_map) == set(themes.THEMES)
    assert APP_CONFIG.DARK_PALETTE is themes.DARK_PALETTE
    assert APP_CONFIG.DARK_PALETTE is themes.THEMES["dark"]
    for slug, palette in themes.THEMES.items():
        assert APP_CONFIG._theme_map[slug] is palette


def test_every_palette_carries_the_full_shape():
    palettes = [APP_CONFIG.DARK_PALETTE]
    palettes.extend(APP_CONFIG.EXTRA_THEMES.values())
    for index, palette in enumerate(palettes):
        missing = REQUIRED_PALETTE_KEYS - set(palette)
        assert not missing, f"palette #{index} misses {missing}"


def test_palette_hex_values_are_parseable():
    """Every color the stylesheet builders interpolate must be a valid hex
    literal - a stray rgba() or named color would raise mid-stylesheet."""
    for index, palette in enumerate([APP_CONFIG.DARK_PALETTE]
                                    + list(APP_CONFIG.EXTRA_THEMES.values())):
        for key in REQUIRED_PALETTE_KEYS - {"MENU_HOVER_COLOR", "HOVER_BG",
                                             "CALENDAR_TODAY_BG_COLOR",
                                             "CALENDAR_TODAY_HOVER_BG_COLOR",
                                             "CALENDAR_SELECTED_BG_COLOR",
                                             "CALENDAR_SELECTED_HOVER_BG_COLOR",
                                             "GREGORIAN_DATE_HOVER_BG"}:
            assert QColor(palette[key]).isValid(), f"palette #{index}: {key}"


def test_display_names_are_unique_and_pretty():
    catalog = APP_CONFIG.theme_catalog()
    names = [name for _key, name, _palette in catalog]
    assert len(names) == len(set(names))
    assert APP_CONFIG.theme_display_name("nord_light") == "Nord Light"
    assert APP_CONFIG.theme_display_name("oled_black") == "OLED Black"
    assert APP_CONFIG.theme_display_name("github_dark") == "GitHub Dark"


def test_theme_names_resolve_every_entry_verbatim():
    """THEME_NAMES carries the slugs word-splitting names wrong; every entry
    must hit a real theme and resolve to the exact exported name."""
    import themes

    for slug, expected in themes.THEME_NAMES.items():
        assert slug in APP_CONFIG._theme_map, slug
        assert APP_CONFIG.theme_display_name(slug) == expected
    assert themes.THEME_NAMES["rose_pine_moon"] == "Rosé Pine Moon"
    assert themes.THEME_NAMES["synthwave_84"] == "Synthwave '84"
    assert themes.THEME_NAMES["winter_is_coming"] == "Winter is Coming"
    assert themes.THEME_NAMES["fig_and_leaf"] == "Fig & Leaf"


def test_stock_dark_theme_is_named_default():
    """The theme the app ships wearing reads as «Default», not «Dark» - it is
    the baseline every gallery pick is a departure from."""
    catalog = APP_CONFIG.theme_catalog()
    assert catalog[0] == ("dark", "Default", APP_CONFIG.DARK_PALETTE)
    assert APP_CONFIG.theme_display_name("dark") == "Default"


def test_stock_light_theme_is_retired():
    """The original light palette left the selectable set: the packs carry
    better-designed light themes. The 'system' mode still resolves a light
    verdict onto a designated light theme, and a legacy "light" preference
    maps onto it (see the controller tests)."""
    assert "light" not in APP_CONFIG._theme_map
    assert all(key != "light" for key, _name, _palette in APP_CONFIG.theme_catalog())
    assert not hasattr(APP_CONFIG, "LIGHT_PALETTE")
    assert APP_CONFIG.SYSTEM_LIGHT_THEME in APP_CONFIG._theme_map
    assert not APP_CONFIG.palette_is_dark(
        APP_CONFIG._theme_map[APP_CONFIG.SYSTEM_LIGHT_THEME])


def test_theme_catalog_groups_extras_dark_then_light():
    """The stock dark theme leads, then the packs run as one dark block
    followed by one light block - no interleaving."""
    catalog = APP_CONFIG.theme_catalog()
    assert catalog[0][0] == "dark"
    polarities = [APP_CONFIG.palette_is_dark(palette) for _key, _name, palette in catalog[1:]]
    first_light = polarities.index(False) if False in polarities else len(polarities)
    assert polarities[:first_light] == [True] * first_light
    assert all(p is False for p in polarities[first_light:])


def test_gallery_order_is_the_file_order_not_alphabetical():
    """The picker browses in the themes module's popularity order: the
    recognizable themes line the top rows, the custom sets sit at the tail -
    the catalog never alphabetizes the file order away."""
    keys = [k for k, _n, _p in APP_CONFIG.theme_catalog()]
    assert keys[:5] == ["dark", "dracula", "catppuccin_mocha", "twitch",
                        "nord"]
    assert keys[46] == "catppuccin_latte"  # after stock + the 45 dark extras
    assert keys[-1] == "pastel_dreamland_adventure"


def test_palette_is_dark_polarity():
    assert APP_CONFIG.palette_is_dark(APP_CONFIG.DARK_PALETTE) is True
    # Gallery edge cases: near-black and near-white grounds.
    assert APP_CONFIG.palette_is_dark(APP_CONFIG.EXTRA_THEMES["oled_black"]) is True
    assert APP_CONFIG.palette_is_dark(APP_CONFIG.EXTRA_THEMES["high_contrast_light"]) is False


# --- on-accent text polarity -----------------------------------------------------


def test_on_accent_picks_white_for_deep_accents():
    assert on_accent_text_color("#1f6feb") == "#ffffff"  # GitHub Dark
    assert on_accent_text_color("#398439") == "#ffffff"  # stock dark


def test_on_accent_keeps_white_for_mid_tone_accents():
    """White stays while it clears the floor, even when the near-black
    candidate compares better: the mid-tone accents keep their
    brand-canonical white label instead of flipping to a muddy near-black
    (the misstep this retune exists to end). The 2.4-band accents carry
    white only because the floor is the tuned 2.4, not the WCAG 3.0 - that
    band is what the floor dial exists for."""
    assert on_accent_text_color("#5e81ac") == "#ffffff"  # Nord steel blue (4.0:1)
    assert on_accent_text_color("#268bd2") == "#ffffff"  # Solarized Dark blue (3.7:1)
    assert on_accent_text_color("#2e7de9") == "#ffffff"  # Tokyo Night Day blue (4.0:1)
    assert on_accent_text_color("#5f8787") == "#ffffff"  # PaperColor Dark teal (4.0:1)
    assert on_accent_text_color("#bd93f9") == "#ffffff"  # Dracula purple (2.4:1)
    assert on_accent_text_color("#7aa2f7") == "#ffffff"  # Tokyo Night Storm (2.5:1)


def test_on_accent_picks_near_black_for_light_accents():
    assert on_accent_text_color("#e6e6e6") == "#16161a"  # Graphite
    assert on_accent_text_color("#ffdd00") == "#16161a"  # High Contrast Dark
    assert on_accent_text_color("#5de4c7") == "#16161a"  # Poimandres mint
    assert on_accent_text_color("#cba6f7") == "#16161a"  # Catppuccin Mocha lilac (2.0:1)


def test_every_accent_carries_its_chosen_label_at_aa():
    """The point of the on-accent rule: the chosen label clears the tuned
    on-accent floor (2.4 - big bold captions; see ``_ON_ACCENT_MIN_RATIO``)
    on every accent, and the polarity is decided by that floor, not by a
    bare better-of-two: white while it clears the floor, near-black only for
    the accents white genuinely fails on, better-of-two as the last resort
    when neither does (no registry accent lands there today).
    """
    from utils.ui_helpers import _ON_ACCENT_MIN_RATIO

    palettes = [APP_CONFIG.DARK_PALETTE]
    palettes.extend(APP_CONFIG.EXTRA_THEMES.values())
    for index, palette in enumerate(palettes):
        accent = palette["ACCENT_COLOR"]
        label = on_accent_text_color(accent)
        white = contrast_ratio(QColor("#ffffff"), QColor(accent))
        dark = contrast_ratio(QColor("#16161a"), QColor(accent))
        if white >= _ON_ACCENT_MIN_RATIO:
            expected = "#ffffff"
        elif dark >= _ON_ACCENT_MIN_RATIO:
            expected = "#16161a"
        else:
            expected = "#ffffff" if white >= dark else "#16161a"
        assert label == expected, f"palette #{index}: unexpected label for {accent}"
        chosen = white if label == "#ffffff" else dark
        assert chosen >= _ON_ACCENT_MIN_RATIO, (
            f"palette #{index} ({accent}): {label} only {chosen:.2f}:1")


# --- shared gallery building blocks ----------------------------------------------


def test_filtered_catalog_narrows_by_polarity():
    from ui.widgets.gallery_widgets import FILTER_DARK, FILTER_LIGHT, filtered_catalog

    all_entries = filtered_catalog()
    assert len(all_entries) == 73
    assert len(filtered_catalog(mode=FILTER_LIGHT)) == 27
    assert len(filtered_catalog(mode=FILTER_DARK)) == 46
    assert "catppuccin_latte" not in [key for key, _n, _p in filtered_catalog(mode=FILTER_DARK)]


# --- real-window preview render (theme shots) --------------------------------------


def test_preview_render_is_the_real_calendar_window(qtbot):
    """The preview panel's render is the actual calendar window: the renderer
    builds a real (hidden) PersianCalendarWidget, restyles it per palette and
    hands the whole window over at its own size - never a painted
    look-alike."""
    from ui.widgets.theme_shot import PREVIEW_DPR, CalendarShotRenderer
    from ui.windows.calendar_window import PersianCalendarWidget

    renderer = CalendarShotRenderer()
    render = renderer.full_window_artwork("dark", APP_CONFIG.DARK_PALETTE)
    assert render.devicePixelRatio() == PREVIEW_DPR
    assert (render.width(), render.height()) == (
        APP_CONFIG.CALENDAR_WIDTH * PREVIEW_DPR,
        APP_CONFIG.CALENDAR_HEIGHT * PREVIEW_DPR)
    # The engine behind it is the real popup, kept hidden.
    assert isinstance(renderer._widget, PersianCalendarWidget)
    assert not renderer._widget.isVisible()


def test_rendering_never_shadows_the_config_palette(qtbot):
    """Regression: the render's palette swap once wrote ``APP_CONFIG``'s
    instance dict, shadowing the class attribute that ``set_theme`` updates -
    every ``APP_CONFIG.current_palette`` reader (the painted window
    backgrounds first among them) then froze on the palette of the very first
    render while ``get_current_palette()`` moved on."""
    from config import Config
    from ui.widgets.theme_shot import CalendarShotRenderer

    APP_CONFIG.set_theme("dark")
    renderer = CalendarShotRenderer()
    renderer.full_window_artwork("nord", APP_CONFIG.EXTRA_THEMES["nord"])
    assert "current_palette" not in vars(APP_CONFIG), (
        "the renderer must not leave an instance-level palette shadow"
    )
    APP_CONFIG.set_theme("tokyo_night_storm")
    assert APP_CONFIG.current_palette is Config.current_palette, (
        "instance reads must follow the class attribute set_theme writes"
    )
    APP_CONFIG.set_theme("dark")


def test_preview_render_keeps_the_popups_own_direction(qtbot):
    """Regression: the hidden popup is re-parented under the RTL gallery to
    tie its lifetime to the window, which made it inherit RTL and mirror
    every plain row - the forward chevron sat visually right, the gregorian
    date to the right of «امروز», the whole preview read reversed. The
    renderer must pin the popup back to the standalone window's LTR."""
    from PyQt6.QtWidgets import QWidget
    from ui.widgets.theme_shot import CalendarShotRenderer

    host = QWidget()
    host.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    qtbot.addWidget(host)
    renderer = CalendarShotRenderer(parent=host)
    renderer.full_window_artwork("dark", APP_CONFIG.DARK_PALETTE)
    widget = renderer._widget
    assert widget.layoutDirection() == Qt.LayoutDirection.LeftToRight
    # Behavioural, not just the flag: the forward chevron (❮) sits visually
    # left and the back chevron (❯) visually right - the standalone popup's
    # arrangement - and the gregorian date opens the bar from the left.
    assert widget.left_arrow_btn.x() < widget.right_arrow_btn.x()
    assert widget.gregorian_date_label.x() < widget.today_btn.x()


def test_preview_render_follows_the_palette_and_is_cached(qtbot):
    from ui.widgets.theme_shot import CalendarShotRenderer

    renderer = CalendarShotRenderer()
    dark = renderer.full_window_artwork("dark", APP_CONFIG.DARK_PALETTE)
    light = renderer.full_window_artwork(
        "catppuccin_latte", APP_CONFIG.EXTRA_THEMES["catppuccin_latte"])
    assert not dark.isNull() and not light.isNull()
    assert dark.toImage() != light.toImage(), "renders must differ per palette"
    # One pixmap per theme: later requests are the cached object.
    assert renderer.full_window_artwork("dark", APP_CONFIG.DARK_PALETTE) is dark
    assert "dracula" not in renderer._full_artwork


def test_rendering_a_preview_never_leaks_its_palette():
    """The palette swap behind a render is invisible to the live app: the
    active theme is exactly what it was before the render request."""
    from ui.widgets.theme_shot import CalendarShotRenderer

    APP_CONFIG.set_theme("dark")
    try:
        renderer = CalendarShotRenderer()
        renderer.full_window_artwork("dracula", APP_CONFIG.EXTRA_THEMES["dracula"])
        renderer.full_window_artwork("catppuccin_latte",
                                     APP_CONFIG.EXTRA_THEMES["catppuccin_latte"])
        assert APP_CONFIG.get_current_palette() is APP_CONFIG.DARK_PALETTE
    finally:
        APP_CONFIG.set_theme("dark")


def test_every_day_cell_renders_into_the_capture(qtbot):
    """Regression: a capture whose painter was scaled on top of the pixmap's
    device pixel ratio silently dropped day-cell text - the preview looked
    like an empty frame. The 2x render must carry ink in all 42 grid cells."""
    from PyQt6.QtGui import QColor, QImage
    from ui.widgets.theme_shot import CalendarShotRenderer

    renderer = CalendarShotRenderer()
    full = renderer._render_window(APP_CONFIG.EXTRA_THEMES["catppuccin_latte"])
    img = full.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    widget = renderer._widget
    blanks = 0
    for row in widget.day_labels:
        for cell in row:
            pos = cell.mapTo(widget, cell.rect().topLeft())
            ink = sum(1
                      for y in range(pos.y() * 2, (pos.y() + 35) * 2)
                      for x in range(pos.x() * 2, (pos.x() + 35) * 2)
                      if QColor(img.pixel(x, y)).lightness() < 230)
            if ink == 0:
                blanks += 1
    assert blanks == 0, f"{blanks} day cells painted no text into the capture"


def test_hidden_render_matches_a_shown_window(qtbot):
    """The never-shown render the preview relies on paints byte-identical
    pixels to the same window shown the normal way - the equivalence that
    makes the preview a true screenshot of the popup.

    The comparison is cursor-insulated: a shown window under the offscreen
    cursor legitimately carries a :hover day cell (the hidden one cannot),
    so the cursor is parked far away and the calendar's own stale-hover
    repair (normalize_day_hover) runs before either grab."""
    from PyQt6.QtGui import QCursor
    from PyQt6.QtWidgets import QApplication
    from ui.windows.calendar_window import PersianCalendarWidget

    palette = APP_CONFIG.EXTRA_THEMES["nord"]
    config_cls = type(APP_CONFIG)
    previous = config_cls.current_palette
    config_cls.current_palette = palette
    try:
        hidden = PersianCalendarWidget({}, {})
        hidden.ensurePolished()
        hidden.layout().activate()
        QCursor.setPos(20000, 20000)  # far from any window the suite leaves up
        shown = PersianCalendarWidget({}, {})
        shown.show()
        QApplication.instance().processEvents()
        QApplication.instance().processEvents()
        shown.normalize_day_hover()
        hidden.normalize_day_hover()
    finally:
        config_cls.current_palette = previous
    qtbot.addWidget(hidden)
    qtbot.addWidget(shown)
    assert hidden.grab().toImage() == shown.grab().toImage()


# --- the mini-calendar card artwork ------------------------------------------------


def test_card_art_is_the_calendar_silhouette():
    """The picker card is the calendar abstracted to its silhouette: the
    theme's own background surface carrying the abstract header, seven
    weekday dashes, five weeks of one-size day dots over tinted state
    squares, a divider and the theme's name inside the card - painted at 2x
    for scaled displays."""
    from ui.widgets.gallery_widgets import (CARD_HEIGHT, CARD_WIDTH,
                                            theme_card_pixmap)

    pixmap = theme_card_pixmap(APP_CONFIG.DARK_PALETTE, "Default")
    assert pixmap.devicePixelRatio() == 2.0
    assert (pixmap.width(), pixmap.height()) == (CARD_WIDTH * 2, CARD_HEIGHT * 2)
    image = pixmap.toImage()

    background = QColor(APP_CONFIG.DARK_PALETTE["BACKGROUND_COLOR"])
    # A quiet spot between the weekday dashes and the first week (logical
    # (100, 26) -> device (200, 52)) shows the theme's own surface.
    surface = image.pixelColor(200, 52)
    assert (abs(surface.red() - background.red())
            + abs(surface.green() - background.green())
            + abs(surface.blue() - background.blue())) < 30, "the theme's own surface"

    def close(actual: QColor, hex_color: str, slack: int = 40) -> bool:
        expected = QColor(hex_color)
        return (abs(actual.red() - expected.red())
                + abs(actual.green() - expected.green())
                + abs(actual.blue() - expected.blue())) <= slack

    # The reference geometry: 10px side padding, cell pitch 14x11, the first
    # week's top at y=30 (col 0 = Saturday, the rightmost column under RTL).
    def col_x(col: int) -> float:
        return CARD_WIDTH - 10 - 7 - col * 14

    def row_y(row: int) -> float:
        return 30 + 11 * row + 5.5

    # The Friday column (col 6, the leftmost under RTL) is a row of holiday
    # dots - the SAME small size as every other dot.
    assert close(image.pixelColor(int(col_x(6) * 2), int(row_y(0) * 2)),
                 APP_CONFIG.DARK_PALETTE["HOLIDAY_COLOR"]), "holiday dot"
    # Today (week 2, Sunday) is a text-colored dot over the today fill.
    assert close(image.pixelColor(int(col_x(1) * 2), int(row_y(1) * 2)),
                 APP_CONFIG.DARK_PALETTE["TEXT_COLOR"]), "today dot"
    # The event day (week 3, Tuesday) carries the event color (green here).
    assert close(image.pixelColor(int(col_x(3) * 2), int(row_y(2) * 2)),
                 APP_CONFIG.DARK_PALETTE["ACCENT_COLOR"]), "event dot"
    # An out-of-month cell (week 1, Saturday) stays quiet grey, no tint.
    assert close(image.pixelColor(int(col_x(0) * 2), int(row_y(0) * 2)),
                 APP_CONFIG.DARK_PALETTE["GREY_COLOR"]), "out-of-month dot"

    # ONE dot size everywhere: the holiday dot's ink run is no wider than a
    # normal day's (the retired big state circles must not come back).
    def ink_run(col: int, row: int) -> int:
        y = int(row_y(row) * 2)
        run = 0
        for x in range(int((col_x(col) - 8) * 2), int((col_x(col) + 8) * 2)):
            color = image.pixelColor(x, y)
            drift = (abs(color.red() - background.red())
                     + abs(color.green() - background.green())
                     + abs(color.blue() - background.blue()))
            if drift > 120:  # dot ink, not the quiet tint behind it
                run += 1
        return run

    holiday_run, normal_run = ink_run(6, 1), ink_run(0, 1)
    assert abs(holiday_run - normal_run) <= 2, (
        f"holiday ({holiday_run}px) and normal ({normal_run}px) dots differ in size"
    )

    # The state rides a TINTED ROUNDED SQUARE behind the dot: week 1's Friday
    # carries HOLIDAY_COLOR at 30% over the card surface, beside the dot.
    holiday = QColor(APP_CONFIG.DARK_PALETTE["HOLIDAY_COLOR"])
    tint = image.pixelColor(int((col_x(6) - 3.5) * 2), int(row_y(0) * 2))
    for actual, expected in (
            (tint.red(), holiday.red() * 0.3 + background.red() * 0.7),
            (tint.green(), holiday.green() * 0.3 + background.green() * 0.7),
            (tint.blue(), holiday.blue() * 0.3 + background.blue() * 0.7)):
        assert abs(actual - expected) <= 4, "the holiday tint behind the dot"

    # The selected day's cell: its own fill plus a thin text ring, and NO
    # accent ink anywhere outside the event day's cell (the retired outline
    # and underline must not come back).
    accent = QColor(APP_CONFIG.DARK_PALETTE["ACCENT_COLOR"])
    event_box = (int((col_x(3) - 7) * 2), int((col_x(3) + 7) * 2),
                 int((row_y(2) - 6) * 2), int((row_y(2) + 6) * 2))
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            color = image.pixelColor(x, y)
            if (abs(color.red() - accent.red())
                    + abs(color.green() - accent.green())
                    + abs(color.blue() - accent.blue())) <= 60:
                assert (event_box[0] <= x <= event_box[1]
                        and event_box[2] <= y <= event_box[3]), (
                    f"accent ink outside the event cell at ({x},{y})"
                )

    # The divider under the grid reads in the palette's calendar border color
    # (DIVIDER_Y = 89 -> device y = 178).
    assert close(image.pixelColor(CARD_WIDTH, 178),
                 APP_CONFIG.DARK_PALETTE["CALENDAR_BORDER_COLOR"]), "the divider line"


def test_card_name_wears_the_cards_own_text_color_never_the_accent():
    """The theme's name inside the card is text, not a state: it renders in
    the card's own text color and never swaps into an accent - not the
    theme's, not the gallery's."""
    from ui.widgets.gallery_widgets import theme_card_pixmap

    palette = APP_CONFIG.EXTRA_THEMES["catppuccin_latte"]
    image = theme_card_pixmap(palette, "Catppuccin Latte").toImage()
    text = QColor(palette["TEXT_COLOR"])
    accent = QColor(palette["ACCENT_COLOR"])
    background = QColor(palette["BACKGROUND_COLOR"])

    ink = 0
    for y in range(182, 230):  # the name band, device pixels
        for x in range(0, image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            if (abs(color.red() - background.red())
                    + abs(color.green() - background.green())
                    + abs(color.blue() - background.blue())) < 60:
                continue  # the card surface, not ink
            to_accent = (abs(color.red() - accent.red())
                         + abs(color.green() - accent.green())
                         + abs(color.blue() - accent.blue()))
            assert to_accent > 90, f"accent-colored text at ({x},{y}): {color.name()}"
            if (abs(color.red() - text.red())
                    + abs(color.green() - text.green())
                    + abs(color.blue() - text.blue())) < 90:
                ink += 1
    assert ink > 40, "the name must render in the theme's own text color"


def test_card_long_names_wrap_to_two_balanced_lines():
    """A name that does not fit the 98px band wraps at the word boundary
    whose wider line is smallest: ink renders in each band half and stays
    inside the band's width, while a short name still centers a single line
    in the taller band."""
    from PyQt6.QtGui import QFont, QFontMetrics

    from utils.asset_loader import load_fonts
    load_fonts()

    from ui.widgets.gallery_widgets import (CARD_SIDE_PADDING, CARD_WIDTH,
                                            NAME_BAND_HEIGHT, NAME_FONT_PX,
                                            NAME_TOP_Y, _balanced_name_split,
                                            theme_card_pixmap)

    palette = APP_CONFIG.DARK_PALETTE
    top, bottom = int(NAME_TOP_Y * 2), int((NAME_TOP_Y + NAME_BAND_HEIGHT) * 2)
    mid = (top + bottom) // 2
    band_left = int(CARD_SIDE_PADDING * 2)
    band_right = int((CARD_WIDTH - CARD_SIDE_PADDING) * 2)

    def ink_rows(image):
        """Name-ink rows, scanned inside the band's own x-window: the card's
        border curve dips a few logical px into these rows at the sides, and
        only the name lives between the padded edges."""
        background = QColor(palette["BACKGROUND_COLOR"])
        rows = []
        for y in range(top, bottom):
            xs = [x for x in range(band_left, band_right + 1)
                  if image.pixelColor(x, y).alpha() > 0
                  and (abs(image.pixelColor(x, y).red() - background.red())
                       + abs(image.pixelColor(x, y).green() - background.green())
                       + abs(image.pixelColor(x, y).blue() - background.blue())) >= 60]
            if xs:
                rows.append((y, min(xs), max(xs)))
        return rows

    image = theme_card_pixmap(palette, "Pastel Dreamland Adventure").toImage()
    rows = ink_rows(image)
    assert [r for r in rows if r[0] < mid], "a line renders above the band's middle"
    assert [r for r in rows if r[0] >= mid], "a line renders below the band's middle"

    font = QFont(APP_CONFIG.GREGORIAN_FONT_FAMILY)
    font.setPixelSize(int(NAME_FONT_PX))
    font.setWeight(QFont.Weight.DemiBold)
    metrics = QFontMetrics(font)
    assert _balanced_name_split("Pastel Dreamland Adventure", metrics, 98) == \
        ("Pastel Dreamland", "Adventure")
    assert _balanced_name_split("Tomorrow Night Blue", metrics, 98) == \
        ("Tomorrow", "Night Blue")
    assert _balanced_name_split("Supercalifragilistic", metrics, 98) is None, (
        "no fitting word boundary means the elide fallback, not a forced split")

    solo = theme_card_pixmap(palette, "Default").toImage()
    ys = [row[0] for row in ink_rows(solo)]
    assert ys, "the one-line name still renders"
    assert min(ys) >= top + 8 and max(ys) <= bottom - 8, (
        "the single line sits centered inside the taller band")


def test_card_header_is_abstract_not_text():
    """The header carries no real words: a rounded title bar in the theme's
    text color between the two chevron ticks, seven short dashes under it -
    Friday's already in the holiday color - and nothing else in the header
    band. The month the preview lives in stopped mattering to the card when
    the header went abstract."""
    from ui.widgets.gallery_widgets import theme_card_pixmap

    image = theme_card_pixmap(APP_CONFIG.DARK_PALETTE, "Default").toImage()
    background = QColor(APP_CONFIG.DARK_PALETTE["BACKGROUND_COLOR"])
    text = QColor(APP_CONFIG.DARK_PALETTE["TEXT_COLOR"])

    def close(actual: QColor, expected: QColor, slack: int = 60) -> bool:
        return (abs(actual.red() - expected.red())
                + abs(actual.green() - expected.green())
                + abs(actual.blue() - expected.blue())) <= slack

    # The title bar: a 34x5 rounded bar centred on the card's midline at the
    # header's centre (logical (59, 8) -> device (118, 16)) - and a short one:
    # just past its end the strip is already bare surface (device x=160).
    assert close(image.pixelColor(118, 16), text), "the abstract title bar"
    assert close(image.pixelColor(160, 16), background, 30), "the bar stays short"
    # The weekday dashes at y=21: Friday's dash (col 6, the leftmost) reads
    # holiday-red, a weekday dash reads the weekday color.
    assert close(image.pixelColor(34, 42),
                 QColor(APP_CONFIG.DARK_PALETTE["HOLIDAY_COLOR"])), "Friday's dash"
    assert close(image.pixelColor(202, 42),
                 QColor(APP_CONFIG.DARK_PALETTE["WEEKDAY_NAMES_COLOR"])), "a weekday dash"
    # Between the title bar and the dashes the strip stays the card's own
    # surface: no month name, no weekday letters.
    assert close(image.pixelColor(118, 24), background, 30), "no header text"


def test_card_light_theme_reads_dark_on_light():
    """A light theme's card mirrors: the theme's light surface with its dark
    dots, the Friday column still holiday-red."""
    from ui.widgets.gallery_widgets import CARD_WIDTH, theme_card_pixmap

    palette = APP_CONFIG.EXTRA_THEMES["catppuccin_latte"]
    image = theme_card_pixmap(palette, "Catppuccin Latte").toImage()
    background = QColor(palette["BACKGROUND_COLOR"])
    surface = image.pixelColor(200, 52)
    assert (abs(surface.red() - background.red())
            + abs(surface.green() - background.green())
            + abs(surface.blue() - background.blue())) < 30, "the light surface"
    friday_x = int((CARD_WIDTH - 10 - 7 - 6 * 14) * 2)
    holiday = QColor(palette["HOLIDAY_COLOR"])
    dot = image.pixelColor(friday_x, 71)
    assert (abs(dot.red() - holiday.red()) + abs(dot.green() - holiday.green())
            + abs(dot.blue() - holiday.blue())) < 90, "holiday dot on a light card"


def test_card_paints_the_1b_day_grid(qapp):
    """The card carries the fixed \"1b\" sample month, cell by cell: a 30-day
    month opening on a Sunday and closing on a Monday, whose four in-month
    Fridays are the ONLY holiday cells (no ad-hoc red days anywhere else),
    the trailing out-of-month Friday muted like the real calendar's, today,
    the event day and the selected day each riding their own tint behind the
    same-size dot."""
    from ui.widgets.gallery_widgets import theme_card_pixmap

    # col 0 = Saturday (the rightmost column under RTL), col 6 = Friday.
    expected_grid = (
        "o.....H",
        ".T....H",
        "...E..H",
        "..S...H",
        "...oooh",
    )
    palette = APP_CONFIG.DARK_PALETTE
    image = theme_card_pixmap(palette, "Default").toImage()
    background = QColor(palette["BACKGROUND_COLOR"])
    text = QColor(palette["TEXT_COLOR"])
    holiday = QColor(palette["HOLIDAY_COLOR"])
    grey = QColor(palette["GREY_COLOR"])
    accent = QColor(palette["ACCENT_COLOR"])
    today_fill = QColor(128, 128, 128, 76)   # rgba(..., 0.3)
    selected_fill = QColor(224, 224, 224, 51)  # rgba(..., 0.2)

    def col_x(col: int) -> int:
        return (118 - 10 - 7 - col * 14) * 2

    def row_y(row: int) -> int:
        return int((30 + 11 * row + 5.5) * 2)

    def composite(over: QColor, under: QColor) -> QColor:
        """Source-over of two QColors at their own alphas."""
        a = over.alphaF()
        return QColor(round(over.red() * a + under.red() * (1 - a)),
                      round(over.green() * a + under.green() * (1 - a)),
                      round(over.blue() * a + under.blue() * (1 - a)))

    def assert_pixel(x, y, expected, label, slack=6):
        actual = image.pixelColor(x, y)
        assert (abs(actual.red() - expected.red())
                + abs(actual.green() - expected.green())
                + abs(actual.blue() - expected.blue())) <= slack, (
            f"{label}: got {actual.name()}, want {expected.name()} at ({x},{y})")

    for row, pattern in enumerate(expected_grid):
        for col, state in enumerate(pattern):
            cx, cy = col_x(col), row_y(row)
            # A point solidly inside the state square yet clear of both the
            # dot and the square's rounded corners: 2x1.5 logical px off the
            # centre (the square spans +/-6x +/-4.5, the dot +/-1.5).
            if state == ".":
                assert_pixel(cx, cy, text, f"plain dot r{row}c{col}")
                assert_pixel(cx + 4, cy + 3, background,
                             f"plain cell carries no tint r{row}c{col}")
            elif state == "o":
                assert_pixel(cx, cy, grey, f"out-of-month dot r{row}c{col}")
                assert_pixel(cx + 4, cy + 3, background,
                             f"out-of-month cell carries no tint r{row}c{col}")
            elif state == "h":
                whisper = composite(
                    QColor(holiday.red(), holiday.green(), holiday.blue(), 23),
                    background)  # holiday at ~9%
                assert_pixel(cx + 4, cy + 3, whisper,
                             f"muted Friday tint r{row}c{col}")
                assert_pixel(cx, cy, composite(
                    QColor(holiday.red(), holiday.green(), holiday.blue(), 115),
                    whisper), f"muted Friday dot r{row}c{col}")  # ~45%
            elif state == "H":
                assert_pixel(cx + 4, cy + 3, composite(
                    QColor(holiday.red(), holiday.green(), holiday.blue(), 77),
                    background), f"holiday tint r{row}c{col}")  # 30%
                assert_pixel(cx, cy, holiday, f"holiday dot r{row}c{col}")
            elif state == "T":
                assert_pixel(cx + 4, cy + 3, composite(today_fill, background),
                             f"today tint r{row}c{col}")
                assert_pixel(cx, cy, text, f"today dot r{row}c{col}")
            elif state == "E":
                assert_pixel(cx + 4, cy + 3, composite(
                    QColor(accent.red(), accent.green(), accent.blue(), 82),
                    background), f"event tint r{row}c{col}")  # ~32%
                assert_pixel(cx, cy, accent, f"event dot r{row}c{col}")
            elif state == "S":
                assert_pixel(cx + 4, cy + 3,
                             composite(selected_fill, background),
                             f"selected tint r{row}c{col}")
                assert_pixel(cx, cy, text, f"selected dot r{row}c{col}")
                # The thin text ring rides the state square's edge: some pixel
                # in the band around the square's left edge reads text-ish.
                edge_x = cx - 12  # the square's left edge, device px
                def ring_distance(color: QColor) -> int:
                    return (abs(color.red() - text.red())
                            + abs(color.green() - text.green())
                            + abs(color.blue() - text.blue()))
                ring = min((image.pixelColor(x, cy)
                            for x in range(edge_x - 2, edge_x + 3)),
                           key=ring_distance)
                assert ring_distance(ring) <= 90, (
                    f"the selected cell's text ring, got {ring.name()}")


def test_selected_day_fill_stays_todays_quiet_sibling():
    """Every theme's selected-day fill rides the theme's own TEXT color at a
    whisper - the same neutral family the Default theme keeps today and
    selected in - never the accent: the two days must not read as unrelated
    colors, and the selected day must not become an accent block."""
    import re

    for key, _name, palette in APP_CONFIG.theme_catalog():
        selected = palette["CALENDAR_SELECTED_BG_COLOR"]
        hover = palette["CALENDAR_SELECTED_HOVER_BG_COLOR"]
        match = re.match(r"rgba\((\d+), (\d+), (\d+), ([\d.]+)\)", selected)
        assert match, f"{key}: selected fill must be an rgba tint, got {selected!r}"
        text = palette["TEXT_COLOR"].lstrip("#")
        rgb = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        assert tuple(int(g) for g in match.groups()[:3]) == rgb, (
            f"{key}: the selected fill must derive from the text color, "
            f"got {selected}")
        dark = APP_CONFIG.palette_is_dark(palette)
        opacity = float(match.group(4))
        assert opacity == (0.20 if dark else 0.14), f"{key}: {selected}"
        hover_match = re.match(r"rgba\((\d+), (\d+), (\d+), ([\d.]+)\)", hover)
        assert tuple(int(g) for g in hover_match.groups()[:3]) == rgb, (
            f"{key}: the selected hover fill must derive from the text color")
        assert abs(float(hover_match.group(4)) - (opacity + 0.10)) < 1e-6, (
            f"{key}: {hover}")


def test_gallery_grid_uses_the_reference_spacing(gallery):
    """The picker breathes on the \"1b\" spacing: 14px between card columns,
    18px between card rows, and about 14px of air above the first row - gaps
    wide enough that the 3px-offset state outlines never touch a neighbour."""
    from ui.widgets.gallery_widgets import CARD_HEIGHT, CARD_WIDTH
    from ui.windows.theme_gallery_window import (CARD_CELL_HEIGHT,
                                                 CARD_CELL_WIDTH, CARD_TOP_PAD)

    window, _calls = gallery
    first = window.grid.visualItemRect(window.grid.item(0))
    second = window.grid.visualItemRect(window.grid.item(1))
    fourth = window.grid.visualItemRect(window.grid.item(3))
    fifth = window.grid.visualItemRect(window.grid.item(4))
    # The cells pitch on the gap-inclusive size (RTL only mirrors which side
    # item 0 sits on, never the pitch itself)...
    assert abs(second.x() - first.x()) == CARD_CELL_WIDTH
    assert fifth.y() - first.y() == CARD_CELL_HEIGHT
    # ...so the card-to-card gaps are the pitch minus the art: 14 and 18.
    assert abs(second.x() - first.x()) - CARD_WIDTH == 14, "14px between columns"
    assert (fifth.y() - first.y()) - CARD_HEIGHT == 18, "18px between rows"
    assert fourth.y() == first.y(), "four cards abreast in the first row"
    # ~14px of air above the first row's art (the art sits CARD_TOP_PAD into
    # its cell, plus whatever top margin the view itself keeps).
    air = first.y() + CARD_TOP_PAD
    assert 12 <= air <= 22, f"about 14px above the first row, got {air}"


# --- the gallery window ------------------------------------------------------------


def _fresh_calls():
    return {"preview": [], "commit": [], "cancel": []}


@pytest.fixture
def gallery(qtbot):
    """A gallery window over stub callbacks, shown and registered with qtbot."""
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    calls = _fresh_calls()
    window = ThemeGalleryWindow(
        on_preview=calls["preview"].append,
        on_commit=lambda key: calls["commit"].append(key),
        on_cancel=lambda key: calls["cancel"].append(key),
        current_key_provider=lambda: "dark",
        holidays={},
        events={},
    )
    qtbot.addWidget(window)
    window.show()
    return window, calls


def _row_of(window, key):
    for row in range(window.grid.count()):
        if window.grid.item(row).data(Qt.ItemDataRole.UserRole) == key:
            return row
    raise AssertionError(f"{key} is not in the grid")


def test_gallery_lists_every_theme(gallery):
    window, _calls = gallery
    assert window.grid.count() == 73


def test_gallery_selection_previews_inside_the_panel(gallery):
    """A click previews inside the gallery and nowhere else: the panel dresses
    in the clicked theme while the application's own
    palette never moves - «اعمال», not browsing, is what changes the app."""
    window, calls = gallery
    live_before = APP_CONFIG.get_current_palette()
    window.grid.setCurrentRow(_row_of(window, "dracula"))
    assert calls["preview"] == ["dracula"]
    # The selection indicator follows the click; the baseline stays marked.
    assert window._delegate.preview_key == "dracula"
    assert window._delegate.original_key == "dark"
    # The panel rendered the clicked theme from the map - and the live
    # palette (the app, the tray, every other window) stayed exactly where
    # the session left it.
    assert window.calendar_panel._rendered_palette is (
        APP_CONFIG.EXTRA_THEMES["dracula"])
    assert APP_CONFIG.get_current_palette() is live_before


def test_gallery_hover_never_previews(gallery, qtbot):
    """Previews follow the click, never the cursor: a mouse move over a card
    must not preview it (the hover affordance is paint-only)."""
    window, calls = gallery
    rect = window.grid.visualItemRect(window.grid.item(_row_of(window, "nord")))
    qtbot.mouseMove(window.grid.viewport(), rect.center())
    assert calls["preview"] == [], "hovering must not change the previewed theme"
    assert window.grid.currentRow() == _row_of(window, "dark")


def test_gallery_clicked_card_carries_the_selection_frame(gallery):
    """A left click must visibly select the card: the solid accent frame hugs
    the clicked card's own corner curve - and nothing else rides the art (the
    retired check badge must not come back)."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem
    from ui.windows.theme_gallery_window import CARD_CELL_HEIGHT, CARD_CELL_WIDTH

    window, _calls = gallery
    window.grid.setCurrentRow(_row_of(window, "dracula"))
    accent = QColor(APP_CONFIG.EXTRA_THEMES["dracula"]["ACCENT_COLOR"])

    def paint_card(key):
        row = _row_of(window, key)
        image = QImage(CARD_CELL_WIDTH, CARD_CELL_HEIGHT, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, CARD_CELL_WIDTH, CARD_CELL_HEIGHT)
        option.state = QStyle.StateFlag.State_Enabled
        window._delegate.paint(painter, option, window.grid.model().index(row, 0))
        painter.end()
        return image

    clicked = paint_card("dracula")
    # The frame ring rides CARD_OUTLINE_OFFSET off the art's top edge (the art
    # sits CARD_TOP_PAD into its cell, so the outline's top edge is at
    # y = 14 - 3 = 11 at the cell's midline).
    ring = clicked.pixelColor(CARD_CELL_WIDTH // 2, 11)
    distance = (abs(ring.red() - accent.red()) + abs(ring.green() - accent.green())
                + abs(ring.blue() - accent.blue()))
    assert ring.alpha() > 0 and distance < 90, (
        f"the clicked card's frame must be its accent, got {ring.name()}"
    )
    # No badge: the art's top corner carries the card's own surface, not an
    # accent disc.
    corner = clicked.pixelColor(CARD_CELL_WIDTH - 18, 20)
    background = QColor(APP_CONFIG.EXTRA_THEMES["dracula"]["BACKGROUND_COLOR"])
    corner_distance = (abs(corner.red() - background.red())
                       + abs(corner.green() - background.green())
                       + abs(corner.blue() - background.blue()))
    assert corner_distance < 90, (
        f"no badge may ride a card's corner, got {corner.name()}"
    )
    # No frame on a plain card: nothing paints above the art's top edge.
    plain = paint_card("nord")
    assert plain.pixelColor(CARD_CELL_WIDTH // 2, 1).alpha() == 0, (
        "no frame on a plain card"
    )


def test_gallery_calendar_preview_sits_on_the_left(gallery):
    """The big calendar preview occupies the window's left side - the reading
    side - with the picker grid to its right."""
    window, _calls = gallery
    panel = window.calendar_panel.geometry()
    grid = window.grid.geometry()
    assert panel.left() <= window.width() * 0.45, "the preview starts at the left"
    assert panel.right() < grid.left(), "the picker sits to the preview's right"
    assert grid.right() > window.width() * 0.75, "the picker runs to the right edge"


def test_gallery_caption_bar_has_no_title_and_carries_the_filter(gallery):
    """The caption bar is the filter's stage, not a titled bar: no painted
    title text (the native window title covers the taskbar/Alt-Tab instead),
    and the segmented filter reads from the bar's other end - under RTL the
    buttons pin to the right edge, the filter to the left - as wide as the
    preview column it sits above, flush with its edge."""
    from ui.windows.theme_gallery_window import PANEL_WIDTH
    from ui.widgets.gallery_widgets import SegmentedFilter

    window, _calls = gallery
    assert window.title_bar._title_label is None
    # The taskbar keeps the window's name for a minimized gallery.
    assert window.windowTitle() == "گالری تم‌ها"
    control = window.filter_control
    assert control.parent() is window
    assert control.height() == SegmentedFilter.HEIGHT
    assert control.width() == PANEL_WIDTH, "as wide as the preview column"
    assert control.y() == 14, "the bar's row is exactly the filter's stage"
    assert control.x() < window.title_bar.minimize_button.x(), (
        "the filter reads from the bar's reading end")
    assert control.x() == window.left_column.x(), (
        "flush above the column it sits on")
    # No header row and no footer in the body: caption bar and columns -
    # nothing else.
    assert window.layout().count() == 2


def test_gallery_filter_is_out_of_the_preview_column(gallery):
    """The filter narrows the grid, not the preview: only the calendar and
    «اعمال» stack in the left column, every row as wide as the calendar."""
    from ui.windows.theme_gallery_window import PANEL_WIDTH

    window, _calls = gallery
    rows = [window.left_column.layout().itemAt(i).widget()
            for i in range(window.left_column.layout().count())]
    assert rows == [window.calendar_panel, window.apply_button]
    for row in rows:
        assert row.width() == PANEL_WIDTH, "as wide as the calendar"


def test_gallery_apply_button_sits_under_the_preview(gallery):
    """The calendar panel is a pure preview that owns no controls: «اعمال»
    lives in the left column directly beneath it, as wide as the calendar.
    The caption bar's ✕ is the way out, so there is no cancel button, and
    there is no footer strip any more."""
    from ui.windows.theme_gallery_window import (ACTION_BUTTON_HEIGHT,
                                                 LEFT_COLUMN_GAP, PANEL_WIDTH)

    window, _calls = gallery
    panel = window.calendar_panel
    for gone in ("apply_button", "cancel_button", "system_button"):
        assert not hasattr(panel, gone), f"the panel must not own {gone}"
    assert not hasattr(window, "system_button")
    assert not hasattr(window, "_commit_system")
    assert not hasattr(window, "cancel_button"), "the ✕ is the cancel"
    assert not hasattr(window, "footer"), "no footer strip"
    assert not hasattr(window, "_footer_divider")

    button = window.apply_button
    assert button.parent() is window.left_column
    assert button.width() == PANEL_WIDTH == panel.width()
    assert button.height() == ACTION_BUTTON_HEIGHT == 46
    assert button.x() == panel.x(), "flush with the calendar's edges"
    assert button.y() - (panel.y() + panel.height()) == LEFT_COLUMN_GAP


def test_gallery_panel_shows_the_real_calendar_at_its_own_size(gallery):
    """The preview IS the calendar: the panel renders the actual
    ``PersianCalendarWidget`` whole at its own 305x395 size (2x device
    pixels) - the popup's true design, not a squished look-alike."""
    from ui.windows.calendar_window import PersianCalendarWidget

    window, _calls = gallery
    panel = window.calendar_panel
    view = panel.shot_view
    assert (view.width(), view.height()) == (APP_CONFIG.CALENDAR_WIDTH,
                                             APP_CONFIG.CALENDAR_HEIGHT)
    render = view._render
    assert render.devicePixelRatio() == 2.0
    assert (render.width(), render.height()) == (APP_CONFIG.CALENDAR_WIDTH * 2,
                                                 APP_CONFIG.CALENDAR_HEIGHT * 2)
    engine = panel._renderer
    assert isinstance(engine._widget, PersianCalendarWidget)
    assert not engine._widget.isVisible(), "the render source stays hidden"


def test_gallery_panel_renders_the_users_live_month_and_holidays(qtbot):
    """The panel reads the live stores: today's month in the hidden popup's
    header, and a cached holiday on today painting red in the render source
    (the preview shows the live month, so the probe rides it)."""
    import jdatetime
    from ui.windows.theme_gallery_window import ThemeGalleryWindow
    from utils.date_utils import persian_month_name

    calls = _fresh_calls()
    today = jdatetime.date.today()
    holidays = {today.year: {(today.month, today.day): ["جشن تست"]}}
    window = ThemeGalleryWindow(
        on_preview=calls["preview"].append,
        on_commit=lambda key: calls["commit"].append(key),
        on_cancel=lambda key: calls["cancel"].append(key),
        current_key_provider=lambda: "dark",
        holidays=holidays,
        events={},
    )
    qtbot.addWidget(window)
    window.show()
    widget = window.calendar_panel._renderer._widget
    assert widget.month_label.text() == persian_month_name(today.month)
    assert widget.holidays_cache == holidays
    cells = [cell for row in widget.day_labels for cell in row
             if cell.jalali_date == today]
    assert len(cells) == 1
    assert APP_CONFIG.DARK_PALETTE["HOLIDAY_COLOR"].lower() in cells[0].styleSheet().lower()


def test_shot_renderer_aims_its_render_at_the_popup_browsed_month(qtbot):
    """The month provider aims the hidden grid at the LIVE popup's browsed
    month at render time: the user browsed a past month in the tray popup, so
    the preview shows that month instead of the hidden widget's own birth
    month (the no-provider default)."""
    import jdatetime

    from ui.widgets.theme_shot import CalendarShotRenderer
    from utils.date_utils import persian_month_name

    today = jdatetime.date.today()
    month = today.month - 3
    year = today.year
    while month < 1:
        month += 12
        year -= 1
    browsed = jdatetime.date(year, month, min(today.day, 28))

    renderer = CalendarShotRenderer(holidays={}, events={},
                                    month_provider=lambda: browsed)
    renderer.full_window_artwork(APP_CONFIG.Theme.DARK, APP_CONFIG.DARK_PALETTE)
    qtbot.addWidget(renderer._widget)
    widget = renderer._widget
    assert (widget.display_date.year, widget.display_date.month) == (
        browsed.year, browsed.month)
    assert widget.month_label.text() == persian_month_name(browsed.month)


def test_gallery_filter_narrows_the_grid(gallery):
    from ui.widgets.gallery_widgets import FILTER_DARK

    window, _calls = gallery
    window.filter_control.set_filter(FILTER_DARK)
    keys = [window.grid.item(r).data(Qt.ItemDataRole.UserRole) for r in range(window.grid.count())]
    assert len(keys) == 46
    assert "catppuccin_latte" not in keys


def test_filter_names_the_active_stop_for_screen_readers(gallery):
    """The accessible name carries the active stop, refreshed through
    _choose - clicks, set_filter and the arrow keys all land there, so a
    screen reader hears which filter a focus (or an arrow) rests on."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    from ui.widgets.gallery_widgets import (FILTER_ALL, FILTER_DARK,
                                            FILTER_FAVORITES, FILTER_LIGHT,
                                            _FILTER_ACCESSIBLE_NAMES)

    window, _calls = gallery
    control = window.filter_control
    for mode in (FILTER_LIGHT, FILTER_DARK, FILTER_FAVORITES, FILTER_ALL):
        control.set_filter(mode)
        assert control.accessibleName() == (
            f"فیلتر تم‌ها: {_FILTER_ACCESSIBLE_NAMES[mode]}")
    # The arrows move through the same _choose: the bar re-names whatever
    # stop the RTL-walked step landed on.
    QApplication.sendEvent(control, QKeyEvent(QEvent.Type.KeyPress,
                                              Qt.Key.Key_Left,
                                              Qt.KeyboardModifier.NoModifier))
    assert control.accessibleName() == (
        f"فیلتر تم‌ها: {_FILTER_ACCESSIBLE_NAMES[control.current_filter()]}")


def test_gallery_fits_four_card_columns(gallery):
    """The window is sized for the compact mini-calendar cards: four full
    card columns beside the calendar preview. The mirrored wrap only takes
    a cell into a row when it lands strictly inside the viewport, so the
    line carries its remainder at the far end - and the rail's strip and
    gutter stay reserved behind the cards."""
    from ui.windows.theme_gallery_window import (CARD_CELL_WIDTH,
                                                 RAIL_GUTTER_PX, RAIL_WIDTH)

    window, _calls = gallery
    grid = window.grid
    assert grid.gridSize().width() == CARD_CELL_WIDTH
    first = grid.visualItemRect(grid.item(0))
    line_end = grid.visualItemRect(grid.item(3))
    fifth = grid.visualItemRect(grid.item(4))
    assert line_end.y() == first.y(), "four cards abreast in the first row"
    assert fifth.y() > first.y(), "the fifth card wraps to the next row"
    # The row fills the card region exactly, flush at the reading start...
    card_span = grid.width() - (RAIL_WIDTH + RAIL_GUTTER_PX)
    assert (first.left() + first.width()) == card_span, (
        "the first card's cell runs flush to the gutter edge"
    )
    # ...and the line's remainder parks at the far end, away from the rail -
    # the 1px floor, because the window sits exactly on the four-card budget
    # (see the divider flanks in the window module: that remainder is what
    # levels the divider-side dead band with the rail's).
    assert line_end.left() == grid.viewport().width() - CARD_CELL_WIDTH * 4


def test_gallery_divider_flanks_level_the_dead_bands(gallery):
    """The calendar column keeps its 16px flank on the divider and the
    picker's side takes DIVIDER_GRID_GAP_PX; the window sits exactly on the
    four-card floor, where the divider-side dead band (the flank, the
    divider's 1px, the line's remainder, the art's cell inset) levels with
    the rail side's (gutter + inset) - the parity the budget was tuned for."""
    from PyQt6.QtCore import QPoint
    from ui.windows.theme_gallery_window import (CARD_CELL_WIDTH, CARD_WIDTH,
                                                 DIVIDER_GRID_GAP_PX,
                                                 DIVIDER_PANEL_GAP_PX,
                                                 RAIL_GUTTER_PX)

    window, _calls = gallery
    div = window._divider
    calendar_col = window.left_column
    grid_x = window.grid.mapTo(window, QPoint(0, 0)).x()
    # the flanks, in the window's visual space: the columns layout mirrors
    # them, and widget geometry is that truth
    assert (div.x() - (calendar_col.x() + calendar_col.width())
            ) == DIVIDER_PANEL_GAP_PX
    assert grid_x == div.x() + div.width() + DIVIDER_GRID_GAP_PX
    # the window meets the four-card budget exactly: 528 + the floor's 1px
    assert window.grid.viewport().width() == CARD_CELL_WIDTH * 4 + 1
    # both dead bands at the art rect, once the floor holds
    art_inset = (CARD_CELL_WIDTH - CARD_WIDTH) // 2
    remainder = window.grid.viewport().width() - CARD_CELL_WIDTH * 4
    divider_band = div.width() + DIVIDER_GRID_GAP_PX + remainder + art_inset
    rail_band = RAIL_GUTTER_PX + art_inset
    assert divider_band == rail_band == 15


def test_gallery_chrome_stays_in_the_session_theme_while_previewing(gallery):
    """A preview repaints the calendar panel - and nothing else in the world:
    the application's palette stays where the session left it, and the
    gallery's own stage stays in the session's baseline theme, so the
    preview's colors are judged against a constant surround."""
    window, _calls = gallery
    chrome = window._chrome_palette
    assert chrome is APP_CONFIG.DARK_PALETTE
    live_before = APP_CONFIG.get_current_palette()
    window._preview("rose_pine_dawn")
    assert window._painted_palette() is chrome
    assert window._delegate.chrome_palette is chrome
    # The application never wore the preview: the live palette is untouched.
    assert APP_CONFIG.get_current_palette() is live_before
    # The panel, though, did dress in the previewed theme.
    assert window.calendar_panel._rendered_palette is (
        APP_CONFIG.EXTRA_THEMES["rose_pine_dawn"])


def test_gallery_apply_commits_the_preview_and_stays_open(gallery):
    """«اعمال» is the decision, not the exit: the pick is committed through
    the callback, the gallery stays open for further browsing, and the
    session re-baselines onto the applied theme - so a later close reverts
    nothing instead of un-applying it."""
    window, calls = gallery
    window.grid.setCurrentRow(_row_of(window, "tokyo_night_storm"))
    window.apply_button.click()
    assert calls["commit"] == ["tokyo_night_storm"]
    assert not calls["cancel"]
    assert window.isVisible(), "apply must not close the gallery"
    # The session's baseline moved onto the applied pick: the stage, the
    # revert target and the dashed outline's card.
    assert window._original_key == "tokyo_night_storm"
    assert window._delegate.original_key == "tokyo_night_storm"
    assert window._chrome_palette is APP_CONFIG.EXTRA_THEMES["tokyo_night_storm"]
    # Browsing on: another preview, then a close - the committed theme holds.
    window._preview("nord")
    window.close()
    assert not calls["cancel"], "a close after apply reverts nothing"
    assert not window.isVisible()


def test_gallery_close_without_apply_reverts(gallery):
    window, calls = gallery
    window._preview("nord")
    window.close()
    assert calls["cancel"] == ["dark"]
    assert not calls["commit"]


def test_gallery_has_no_layout_machinery(gallery):
    """The A/B layout switch and its handoff are gone with the retired card
    grid: one gallery, no layout vocabulary anywhere on the window."""
    window, _calls = gallery
    assert not hasattr(window, "layout_switch")
    assert not hasattr(window, "_on_layout_chosen")
    assert not hasattr(window, "begin_handoff")
    assert not hasattr(window, "_handoff")
    from ui.widgets import gallery_widgets
    assert not hasattr(gallery_widgets, "GalleryLayoutSwitch")


def test_picker_scrolls_one_card_row_per_wheel_notch(gallery):
    """The picker's wheel step is one card row - the stock icon view pitches
    three rows per notch (its single step is the cell height, and a notch
    multiplies that by three), which reads as the grid leaping under the
    wheel. Sub-notch deltas from high-resolution touchpads accumulate instead
    of dropping."""
    from PyQt6.QtCore import QPointF, QPoint, Qt
    from PyQt6.QtGui import QWheelEvent

    window, _calls = gallery
    bar = window.grid.verticalScrollBar()
    bar.setValue(0)

    def notch():
        pos = QPointF(window.grid.viewport().width() / 2, 10)
        event = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(window.grid.viewport(), event)

    notch()
    first = bar.value()
    assert first == 136, f"one notch must move one card row, moved {first}"
    notch()
    assert bar.value() == 2 * 136
    # A half-notch touchpad pair still sums to one full row.
    bar.setValue(0)
    window.grid._wheel_remainder = 0
    pos = QPointF(window.grid.viewport().width() / 2, 10)
    for delta in (-60, -60):
        event = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(window.grid.viewport(), event)
    assert bar.value() == 136, "sub-notch deltas accumulate into whole rows"
    # Opposing sub-notch jitter cancels without a single step, and a lone
    # negative half-notch waits for its second half (floor-divmod stepped on
    # the first delta and parked a flipped remainder).
    bar.setValue(0)
    window.grid._wheel_remainder = 0
    for delta in (-40, 40):
        event = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(window.grid.viewport(), event)
    assert bar.value() == 0
    assert window.grid._wheel_remainder == 0
    window.grid._wheel_remainder = 0
    for delta in (-60, -60):
        event = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(window.grid.viewport(), event)
    assert bar.value() == 136, "a negative notch steps only when it is whole"


def test_programmatic_selection_does_not_scroll_the_picker(gallery):
    """Restoring the current item (a re-show, a filter change) must not scroll
    the view to it: making an item current scrolls it into view in the stock
    view, which is exactly how a re-shown gallery leapt to the previewed card
    instead of sitting where the user left it."""
    window, _calls = gallery
    grid = window.grid
    bar = grid.verticalScrollBar()
    bar.setValue(700)
    row = _row_of(window, "navy_red")  # deep in the dark tail (file order): offscreen at 700px, where the recognizable themes already are
    assert grid.visualItemRect(grid.item(row)).y() >= grid.viewport().height()
    with grid.hold_viewport():
        grid.setCurrentRow(row)
    assert bar.value() == 700, "the held selection must not move the viewport"
    # Keyboard navigation keeps its scroll-into-view: the walker is never
    # stranded outside the viewport.
    grid.setFocus()
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    QApplication.sendEvent(grid, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down,
                                           Qt.KeyboardModifier.NoModifier))
    assert bar.value() != 700


def test_reshown_gallery_keeps_the_browsed_row(qtbot):
    """A minimized (hidden and re-shown) gallery shows exactly where the user
    left off: the picker is not rebuilt on show - the catalog and filter
    cannot have changed while hidden - so both the items and the scroll
    position survive, and the selection is restored without scrolling.

    The provider is the controller's dynamic one (the in-flight preview
    answers "current"), so a restore keeps the previewed card current - it
    just never scrolls to it."""
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    state = {"current": "dark"}
    window = ThemeGalleryWindow(
        on_preview=lambda key: state.__setitem__("current", key),
        on_commit=lambda key: state.__setitem__("current", key),
        on_cancel=lambda key: state.__setitem__("current", key),
        current_key_provider=lambda: state["current"],
        holidays={},
        events={},
    )
    qtbot.addWidget(window)
    window.show()
    grid = window.grid
    bar = grid.verticalScrollBar()
    grid.setCurrentRow(_row_of(window, "nord"))
    bar.setValue(800)
    items_before = [grid.item(r) for r in range(grid.count())]
    window.hide()
    window.show()
    assert bar.value() == 800, "the re-shown picker keeps the browse position"
    assert [grid.item(r) for r in range(grid.count())] == items_before, (
        "the picker must not be rebuilt on show")
    # The session's state is still re-read: the previewed card stays current.
    assert grid.currentRow() == _row_of(window, "nord")
    # Park the window hidden: offscreen teardown flushes the deferred deletes
    # of a shown window whose paint regions are still pending, and that
    # flushes a corpse-paint the offscreen backend cannot always survive.
    window.hide()


def test_preview_panel_is_just_the_calendar(gallery):
    """The preview carries no name plate or caption: the panel is exactly the
    calendar render, level with the top of the picker."""
    window, _calls = gallery
    panel = window.calendar_panel
    assert not hasattr(panel, "theme_name_label")
    assert not hasattr(panel, "favorite_button")
    assert (panel.width(), panel.height()) == (305, 395)
    assert panel.shot_view.geometry().topLeft() == panel.rect().topLeft()
    top_left = window.left_column.mapTo(window, window.left_column.rect().topLeft())
    grid_top = window.grid.mapTo(window, window.grid.rect().topLeft())
    assert top_left.y() == grid_top.y(), "calendar and picker start level"
    # A preview re-dresses the render, never the stage.
    window._preview("catppuccin_latte")
    assert window.calendar_panel._rendered_palette is \
        APP_CONFIG.EXTRA_THEMES["catppuccin_latte"]
    assert window._chrome_palette is APP_CONFIG.DARK_PALETTE


def test_apply_button_stays_on_the_session_baseline(gallery):
    """«اعمال» is chrome, not preview: it keeps the session's baseline accent
    while themes are browsed - previews change nothing here - and re-dresses
    only when «اعمال» re-baselines the session. It keeps the shared
    accent-button recipe (its label follows on-accent polarity)."""
    from utils.ui_helpers import on_accent_text_color

    window, _calls = gallery
    dark = APP_CONFIG.DARK_PALETTE
    tokyo = APP_CONFIG.EXTRA_THEMES["tokyo_night_storm"]
    window._preview("tokyo_night_storm")
    apply_sheet = window.apply_button.styleSheet()
    assert dark["ACCENT_COLOR"] in apply_sheet
    assert on_accent_text_color(dark["ACCENT_COLOR"]) in apply_sheet
    assert "border-radius: 15px" in apply_sheet
    assert tokyo["ACCENT_COLOR"] not in apply_sheet

    # A commit re-baselines the chrome, and the button follows along with it.
    window._commit()
    assert tokyo["ACCENT_COLOR"] in window.apply_button.styleSheet()


def test_gallery_window_height_fits_the_left_column(gallery):
    """The window is sized to its parts (40px caption bar, then the 451px
    column of calendar + apply button): nothing clips, and the picker runs
    down to the same bottom edge as the left column."""
    from ui.windows.theme_gallery_window import (LEFT_COLUMN_HEIGHT,
                                                 WINDOW_HEIGHT)

    window, _calls = gallery
    assert LEFT_COLUMN_HEIGHT == 451
    assert WINDOW_HEIGHT == 531 and window.height() == 531
    column = window.left_column.geometry()
    assert column.height() == 451
    assert column.bottom() <= window.height() - 16, "fits the bottom margin"
    grid_bottom = window.grid.mapTo(window, window.grid.rect().bottomLeft()).y()
    assert abs(grid_bottom - column.bottom()) <= 1, "the picker reaches the bottom"
    view = window.calendar_panel.shot_view
    assert (view.height(), view.width()) == (395, 305)


def test_picker_scrollbar_rides_the_right_edge(gallery):
    """The picker grid mirrors RTL like the rest of the window, while its
    rail stays at the window's right edge: Qt mirrors an RTL scrollbar to
    the cards' left, so the grid carries a rail of its own (_PickerGrid).
    Placement is asserted in pixels on a probe groove - widget geometry is
    stale under the offscreen layout - and the stock bar must be out of
    the picture: the rail is the one scrollbar visible here."""
    from ui.windows.theme_gallery_window import CARD_TOP_PAD, RAIL_WIDTH
    from PyQt6.QtGui import QColor

    window, _calls = gallery
    grid = window.grid
    assert grid.isRightToLeft()
    stock = grid.verticalScrollBar()
    assert not stock.isVisibleTo(grid)
    rail = grid.rail
    assert rail.parent() is grid and rail.width() == RAIL_WIDTH
    assert rail.x() == grid.width() - RAIL_WIDTH

    original = grid.styleSheet()
    # A later same-selector rule wins the cascade, so this recolors the rail's
    # groove while the styled geometry (width, top/bottom margins) stays.
    grid.setStyleSheet(original + "\nQScrollBar:vertical { background: #ff0000; }")
    try:
        image = grid.grab().toImage()
    finally:
        grid.setStyleSheet(original)

    width, height = image.width(), image.height()
    red = QColor("#ff0000")

    def red_at(x: int) -> int:
        return sum(1 for y in range(CARD_TOP_PAD + 2, height - 6)
                   if image.pixelColor(x, y) == red)

    assert sum(red_at(x) for x in range(width - 14, width)) >= 50, (
        "the groove must paint at the window's right edge")
    assert all(red_at(x) == 0 for x in range(0, 4)), (
        "no groove may hug the left edge")


def test_picker_rail_hides_when_nothing_scrolls(favorites_gallery):
    """The rail shows only when the view actually scrolls: favorites that
    fit in one row render no rail - and the strip it needs stays reserved,
    so the cards never reflow around the rail's return."""
    from ui.widgets.gallery_widgets import FILTER_ALL, FILTER_FAVORITES

    window, _calls = favorites_gallery
    reserved = window.grid.viewport().width()
    window.filter_control.set_filter(FILTER_FAVORITES)
    assert window.grid.count() == 1
    assert window.grid.verticalScrollBar().maximum() == 0
    assert not window.grid.rail.isVisibleTo(window.grid)
    assert window.grid.viewport().width() == reserved, (
        "reserved, not released with the rail")
    window.filter_control.set_filter(FILTER_ALL)
    assert window.grid.rail.isVisibleTo(window.grid)


def test_reshown_gallery_keeps_a_pending_pick_it_can_list(gallery):
    """The reopen invariant: a pending pick the active filter excludes has no
    card to carry it, so the filter's first card is previewed instead and the
    intent is re-reported - the controller's memory must match the panel.
    An empty grid (favorites with no stars) leaves the selection absent."""
    window, calls = gallery
    # Try to make dracula pending, then narrow to light themes: the pending
    # pick (dark) is no longer listed.
    window.grid.setCurrentRow(_row_of(window, "dracula"))
    assert calls["preview"] == ["dracula"]
    window.filter_control.set_filter("light")
    assert not any(window.grid.item(row).data(Qt.ItemDataRole.UserRole)
                   == "dracula" for row in range(window.grid.count()))
    shown = window.grid.item(0).data(Qt.ItemDataRole.UserRole)
    assert window._preview_key == shown
    assert window.grid.currentItem() is window.grid.item(0)
    assert calls["preview"][-1] == shown, "the re-derived pick is re-reported"
    window.hide()
    window.show()
    assert window._preview_key == shown, "the reopen keeps the derivable pick"


# --- controller wiring ------------------------------------------------------------


def test_controller_previews_without_persisting(tray):
    """A preview is the gallery's own business: the pick is remembered as the
    session's in-flight preview, the application keeps the theme it has, and
    the stored preference never moves."""
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY
    tray.settings.setValue(key, "dark")
    # setValue only records: wear the pin before previewing, so the baseline
    # never rides the runner's own system verdict (a light-mode Windows
    # runner resolves system onto the light theme).
    tray._load_settings()
    tray._gallery_preview_theme("dracula")
    assert tray.current_theme == "dark", "the app never wore the preview"
    assert APP_CONFIG.get_current_palette() is not APP_CONFIG.EXTRA_THEMES["dracula"]
    assert tray._gallery_pending_theme == "dracula"
    assert tray.settings.value(key) == "dark", "preview must not write the preference"


def test_controller_commits_the_gallery_pick(tray):
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY
    tray.settings.setValue(key, "dark")
    tray._gallery_commit_theme("tokyo_night_storm")
    assert tray.settings.value(key) == "tokyo_night_storm"
    assert tray.current_theme == "tokyo_night_storm"
    # The pick validates through the same gate the old pins use.
    assert tray._theme_choice() == "tokyo_night_storm"


def test_controller_rejects_unknown_gallery_keys(tray):
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY
    tray.settings.setValue(key, "dark")
    tray._gallery_preview_theme("not-a-theme")
    tray._gallery_commit_theme("not-a-theme")
    assert tray.current_theme != "not-a-theme"
    assert tray.settings.value(key) == "dark"


def test_controller_restore_puts_back_the_opened_theme(tray):
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY
    tray.settings.setValue(key, "dark")
    tray._gallery_preview_theme("melange")
    tray._gallery_restore_theme("dark")
    assert tray.current_theme == APP_CONFIG.Theme.DARK
    assert tray.settings.value(key) == "dark", "restore is memory-only"
    assert tray._gallery_pending_theme is None, "restore drops the in-flight pick"


def test_controller_commit_rebaselines_the_session(tray):
    """A commit becomes the session's baseline, so a later cancel reverts to
    the applied theme instead of un-applying it - the rule the gallery's
    stay-open «اعمال» depends on."""
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY
    tray.settings.setValue(key, "dark")
    tray._gallery_original_theme = "dark"
    tray._gallery_pending_theme = "melange"
    tray._gallery_commit_theme("tokyo_night_storm")
    assert tray.settings.value(key) == "tokyo_night_storm"
    assert tray._gallery_original_theme == "tokyo_night_storm"
    assert tray._gallery_pending_theme is None
    # A cancel after that lands on the committed theme, not the opener.
    tray._gallery_restore_theme(tray._gallery_original_theme)
    assert tray.current_theme == "tokyo_night_storm"
    assert tray.settings.value(key) == "tokyo_night_storm", "the pick stays persisted"


def test_controller_builds_the_single_gallery_window(tray):
    """There is exactly one gallery design now: the controller builds the
    calendar + picker window, wired without any layout-switch intent."""
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    window = tray._build_gallery_window()
    assert isinstance(window, ThemeGalleryWindow)
    signature = inspect.signature(ThemeGalleryWindow.__init__)
    assert "on_layout_changed" not in signature.parameters
    assert not hasattr(tray, "_gallery_layout_changed")
    assert not hasattr(tray, "_gallery_handoff")
    window.close()


def test_controller_opens_the_gallery_from_the_tray_row(tray):
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    tray._open_theme_gallery()
    assert isinstance(tray.theme_gallery_window, ThemeGalleryWindow)
    assert tray.theme_gallery_window.isVisible()
    tray.theme_gallery_window.close()


def test_controller_maps_a_legacy_light_preference_onto_the_light_theme(tray):
    """A preference saved before the stock light theme was retired keeps its
    intent: it resolves onto the designated light theme instead of silently
    falling back to the dark default."""
    tray.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, "light")
    assert tray._theme_choice() == APP_CONFIG.SYSTEM_LIGHT_THEME
    # The boot path resolves the same way: the tray lands on the light theme.
    tray._load_settings()
    assert tray.current_theme == APP_CONFIG.SYSTEM_LIGHT_THEME
    assert APP_CONFIG.palette_is_dark(
        APP_CONFIG._theme_map[tray.current_theme]) is False


# --- tray menu ---------------------------------------------------------------------


def test_tray_menu_carries_the_gallery_row_and_no_theme_cycle():
    """The menu owns the «تم‌ها» row and nothing else thematic: the old
    system/light/dark cycle row is retired with its widget and controller
    cycle."""
    from ui.widgets import menu_widgets, tray_menu

    source = inspect.getsource(tray_menu.build_tray_menu)
    assert "add_theme_gallery_action(tray, menu)" in source
    assert "add_theme_toggle_action" not in source
    assert not hasattr(tray_menu, "add_theme_toggle_action")
    assert not hasattr(menu_widgets, "ThemeToggleActionWidget")


def test_controller_has_no_theme_cycle(tray):
    assert not hasattr(tray, "_cycle_theme_choice")
    assert not hasattr(APP_CONFIG, "THEME_CYCLE_CHOICES")


# --- segmented filter ----------------------------------------------------------------


def test_filter_is_one_connected_segmented_control(gallery):
    """The filter is a single widget (one connected bar), not a row of
    separate buttons: no child buttons, one accent highlight - and the
    forced caption stage is spent by the segments themselves, not pocketed."""
    from PyQt6.QtWidgets import QPushButton
    from ui.widgets.gallery_widgets import (FILTER_FAVORITES, FILTER_ORDER,
                                            SegmentedFilter)

    window, _calls = gallery
    control = window.filter_control
    assert isinstance(control, SegmentedFilter)
    assert control.findChildren(QPushButton) == []
    # The segments tile the track with no gaps between them, and exactly
    # fill it: both ends land on the track's INSET air, nothing left over -
    # the mirror end must not park a pocket of slack beside the star.
    rects = sorted((control._segment_rect(m) for m in FILTER_ORDER),
                   key=lambda r: r.left())
    for left, right in zip(rects, rects[1:]):
        assert abs(left.right() - right.left()) < 0.01
    assert abs(rects[0].left() - SegmentedFilter.INSET) < 0.01
    assert abs(rects[-1].right() - (control.width() - SegmentedFilter.INSET)) < 0.01
    # The shares are even: the star's pill grew past its bare glyph width
    # with the rest of the bar instead of the extra parking beside it.
    star = control._segment_rect(FILTER_FAVORITES)
    assert star.width() > SegmentedFilter.ICON_WIDTH


def test_filter_segments_read_right_to_left(gallery):
    """Under the window's RTL, «همه» is the rightmost segment and the star
    the leftmost - the order the old chips read in."""
    from ui.widgets.gallery_widgets import FILTER_ALL, FILTER_FAVORITES

    window, _calls = gallery
    control = window.filter_control
    assert control.isRightToLeft()
    assert (control._segment_rect(FILTER_ALL).left()
            > control._segment_rect(FILTER_FAVORITES).left())


def test_filter_highlight_slides_to_the_chosen_segment(gallery, qtbot):
    from ui.widgets.gallery_widgets import FILTER_DARK

    window, _calls = gallery
    control = window.filter_control
    start = control.highlight_rect()
    control.set_filter(FILTER_DARK)
    target = control.target_highlight_rect()
    assert target != start
    qtbot.waitUntil(lambda: control.highlight_rect() == target, timeout=2000)
    assert control.current_filter() == FILTER_DARK


def test_filter_click_selects_the_segment_under_the_cursor(gallery):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from ui.widgets.gallery_widgets import FILTER_LIGHT

    window, _calls = gallery
    control = window.filter_control
    rect = control._segment_rect(FILTER_LIGHT)
    QTest.mouseClick(control, Qt.MouseButton.LeftButton,
                     pos=QPoint(int(rect.center().x()), int(rect.center().y())))
    assert control.current_filter() == FILTER_LIGHT
    assert 0 < window.grid.count() < 73


def test_filter_arrow_keys_step_with_the_reading_direction(gallery):
    from PyQt6.QtTest import QTest
    from ui.widgets.gallery_widgets import FILTER_ALL, FILTER_LIGHT

    window, _calls = gallery
    control = window.filter_control
    assert control.current_filter() == FILTER_ALL
    # RTL: the next segment lies to the LEFT.
    QTest.keyClick(control, Qt.Key.Key_Left)
    assert control.current_filter() == FILTER_LIGHT
    QTest.keyClick(control, Qt.Key.Key_Right)
    assert control.current_filter() == FILTER_ALL


# --- favorites ------------------------------------------------------------------------


@pytest.fixture
def favorites_gallery(qtbot):
    """A gallery wired to an in-memory favorites store."""
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    store = {"favorites": ["nord"], "writes": []}

    def save(keys):
        store["favorites"] = list(keys)
        store["writes"].append(list(keys))

    window = ThemeGalleryWindow(
        on_preview=lambda key: None,
        on_commit=lambda key: None,
        on_cancel=lambda key: None,
        current_key_provider=lambda: "dark",
        holidays={},
        events={},
        favorites_provider=lambda: store["favorites"],
        on_favorites_changed=save,
    )
    qtbot.addWidget(window)
    window.show()
    return window, store


def test_favorites_load_from_the_provider_and_drop_unknown_keys(qtbot):
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    window = ThemeGalleryWindow(
        on_preview=lambda key: None, on_commit=lambda key: None,
        on_cancel=lambda key: None, current_key_provider=lambda: "dark",
        holidays={}, events={},
        favorites_provider=lambda: ["dracula", "no-such-theme"])
    qtbot.addWidget(window)
    assert window.favorite_keys() == ["dracula"]


def test_toggling_a_favorite_twice_round_trips(favorites_gallery):
    window, store = favorites_gallery
    window._toggle_favorite("dracula")
    assert window.is_favorite("dracula")
    assert store["favorites"] == ["dracula", "nord"]  # catalog order
    window._toggle_favorite("dracula")
    assert not window.is_favorite("dracula")
    assert "dracula" not in store["favorites"]
    assert len(store["writes"]) == 2, "every toggle persists at once"


def test_favorites_persist_in_catalog_order(favorites_gallery):
    window, store = favorites_gallery
    window._toggle_favorite("dracula")
    catalog_order = [k for k, _n, _p in APP_CONFIG.theme_catalog()]
    assert store["favorites"] == sorted(store["favorites"], key=catalog_order.index)


def test_favorites_filter_lists_only_starred_themes(favorites_gallery):
    from ui.widgets.gallery_widgets import FILTER_FAVORITES

    window, _store = favorites_gallery
    window._toggle_favorite("dracula")
    window.filter_control.set_filter(FILTER_FAVORITES)
    keys = {window.grid.item(r).data(Qt.ItemDataRole.UserRole)
            for r in range(window.grid.count())}
    assert keys == {"nord", "dracula"}
    assert window.grid.empty_label.isHidden()


def test_favorites_filter_explains_itself_when_empty(qtbot):
    from ui.widgets.gallery_widgets import FILTER_FAVORITES
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    window = ThemeGalleryWindow(
        on_preview=lambda key: None, on_commit=lambda key: None,
        on_cancel=lambda key: None, current_key_provider=lambda: "dark",
        holidays={}, events={})
    qtbot.addWidget(window)
    window.show()
    window.filter_control.set_filter(FILTER_FAVORITES)
    assert window.grid.count() == 0
    assert not window.grid.empty_label.isHidden()
    window.filter_control.set_filter("all")
    assert window.grid.empty_label.isHidden()


def test_unstarring_under_the_favorites_filter_keeps_the_card_until_refilter(
        favorites_gallery):
    """Unstarring must not rebuild the grid under the user's cursor (the scroll
    would snap and a mis-click could not be taken back)."""
    from ui.widgets.gallery_widgets import FILTER_FAVORITES

    window, _store = favorites_gallery
    window.filter_control.set_filter(FILTER_FAVORITES)
    assert window.grid.count() == 1
    window._toggle_favorite("nord")
    assert window.grid.count() == 1, "the card stays until the filter changes"
    window.filter_control.set_filter("all")
    window.filter_control.set_filter(FILTER_FAVORITES)
    assert window.grid.count() == 0


def test_card_badge_click_toggles_favorite_without_previewing(favorites_gallery):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from ui.windows.theme_gallery_window import (card_art_rect,
                                                 favorite_badge_rect)

    window, store = favorites_gallery
    window.grid.verticalScrollBar().setValue(0)
    row = _row_of(window, "dracula")
    cell = window.grid.visualRect(window.grid.indexFromItem(window.grid.item(row)))
    center = favorite_badge_rect(card_art_rect(cell)).center()
    before = window._preview_key
    QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(int(center.x()), int(center.y())))
    assert window.is_favorite("dracula")
    assert "dracula" in store["favorites"]
    assert window._preview_key == before, "starring a card never previews it"


def test_space_toggles_the_current_card_without_previewing(favorites_gallery):
    """The star badge's keyboard twin: Space on the grid toggles the current
    card's favorite over the same signal the badge clicks ride - a favorite
    toggle never previews the card, and the star is takeable-back."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    def press_space():
        QApplication.sendEvent(window.grid, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Space,
            Qt.KeyboardModifier.NoModifier))

    window, store = favorites_gallery
    window.grid.setCurrentRow(_row_of(window, "dracula"))
    before = window._preview_key
    press_space()
    assert window.is_favorite("dracula")
    assert "dracula" in store["favorites"]
    assert window._preview_key == before, (
        "starring from the keyboard never previews")
    press_space()
    assert not window.is_favorite("dracula")


def test_picker_arrows_walk_with_the_reading_direction(gallery):
    """The stock grid walk keeps the model direction, which the RTL mirror
    flips against the reading order: Left lands on the card visually LEFT of
    the current one (the model's next card) and Right on the previous one,
    with the bounds clamping instead of wrapping."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    def press(key):
        QApplication.sendEvent(grid, QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    window, _calls = gallery
    grid = window.grid
    # The first row reads right to left: model order flows leftward.
    rect0 = grid.visualItemRect(grid.item(0))
    rect1 = grid.visualItemRect(grid.item(1))
    rect2 = grid.visualItemRect(grid.item(2))
    assert rect0.x() > rect1.x() > rect2.x()
    grid.setCurrentRow(1)
    press(Qt.Key.Key_Left)
    assert grid.currentRow() == 2
    assert grid.visualItemRect(grid.item(2)).x() < rect1.x()
    press(Qt.Key.Key_Right)
    assert grid.currentRow() == 1
    # Bounds clamp; the walk never leaves the grid or wraps a card row.
    grid.setCurrentRow(0)
    press(Qt.Key.Key_Right)
    assert grid.currentRow() == 0
    grid.setCurrentRow(grid.count() - 1)
    press(Qt.Key.Key_Left)
    assert grid.currentRow() == grid.count() - 1


def test_enter_applies_the_card_the_walk_parked_on(gallery):
    """Enter is the keyboard's «اعمال»: the walk previews what it parks on,
    so Enter commits exactly the card under the selection - the keyboard twin
    of the double-click, and never a second commit through itemActivated."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    window, calls = gallery
    grid = window.grid
    key = grid.item(2).data(Qt.ItemDataRole.UserRole)
    grid.setCurrentRow(2)
    assert calls["preview"] == [key], "the walk previews, the commit waits"
    assert calls["commit"] == []
    QApplication.sendEvent(grid, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert calls["commit"] == [key]


def test_card_body_click_still_previews(favorites_gallery):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from ui.windows.theme_gallery_window import card_art_rect

    window, _store = favorites_gallery
    window.grid.verticalScrollBar().setValue(0)
    row = _row_of(window, "dracula")
    cell = window.grid.visualRect(window.grid.indexFromItem(window.grid.item(row)))
    center = card_art_rect(cell).center()
    QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(int(center.x()), int(center.y())))
    assert window._preview_key == "dracula"
    assert not window.is_favorite("dracula")


def test_favorites_survive_close_without_apply(favorites_gallery):
    """Favorites are bookmarks: closing (a cancel) never discards them."""
    window, store = favorites_gallery
    window._toggle_favorite("dracula")
    window.close()
    assert "dracula" in store["favorites"]


def test_controller_persists_and_validates_favorites(tray):
    key = APP_CONFIG.FAVORITE_THEMES_SETTING_KEY
    assert tray._favorite_themes() == []
    tray._gallery_save_favorites(["dracula", "bogus", "dracula", "nord"])
    assert tray.settings.value(key) == ["dracula", "nord"]
    assert tray._favorite_themes() == ["dracula", "nord"]
    # A hand-edited or corrupt value degrades to "no favorites", never raises.
    tray.settings.setValue(key, "dracula")
    assert tray._favorite_themes() == []
    tray.settings.setValue(key, ["dracula", 7, None, "ghost"])
    assert tray._favorite_themes() == ["dracula"]


def test_controller_wires_favorites_into_the_gallery(tray):
    tray._gallery_save_favorites(["nord"])
    window = tray._build_gallery_window()
    assert window.favorite_keys() == ["nord"]
    window._toggle_favorite("dracula")
    assert tray._favorite_themes() == ["dracula", "nord"]
    window.close()


def test_reshown_gallery_selects_the_restored_theme(qtbot):
    """On show the picker highlights the theme the session restores - not
    whatever the constructor defaulted to - and the preview renders it."""
    from ui.windows.theme_gallery_window import ThemeGalleryWindow

    state = {"current": "dark"}
    window = ThemeGalleryWindow(
        on_preview=lambda key: None, on_commit=lambda key: None,
        on_cancel=lambda key: None,
        current_key_provider=lambda: state["current"],
        holidays={}, events={}, favorites_provider=lambda: ["dracula"])
    qtbot.addWidget(window)
    state["current"] = "dracula"
    window.show()
    assert window._preview_key == "dracula"
    assert window.grid.currentItem().data(Qt.ItemDataRole.UserRole) == "dracula"
    assert window.is_favorite("dracula")
    assert window.calendar_panel._rendered_palette is \
        APP_CONFIG.EXTRA_THEMES["dracula"]


def test_filter_hover_never_touches_the_highlight(gallery):
    """The hovered segment's fill is inset so it leaves a gap to the selected
    highlight next to it, and it fades as the highlight slides over it."""
    from ui.widgets.gallery_widgets import FILTER_LIGHT, FILTER_ALL

    window, _calls = gallery
    control = window.filter_control
    control.settle()
    selected = control.highlight_rect()
    neighbour = control._segment_rect(FILTER_LIGHT)
    assert control.current_filter() == FILTER_ALL
    inset = neighbour.adjusted(control.HOVER_INSET_X, control.HOVER_INSET_Y,
                               -control.HOVER_INSET_X, -control.HOVER_INSET_Y)
    # Horizontal gap between the hover fill and the highlight.
    gap = (selected.left() - inset.right()) if selected.left() >= inset.right() \
        else (inset.left() - selected.right())
    assert gap >= control.HOVER_INSET_X


def test_gallery_scrollbar_thumb_opens_level_with_the_first_card(gallery):
    """The cards start CARD_TOP_PAD under the viewport's top, so the rail's
    top inset must match: at scroll-top the thumb opens level with the first
    card instead of poking above the cards."""
    from PyQt6.QtWidgets import QStyle, QStyleOptionSlider
    from ui.windows.theme_gallery_window import CARD_TOP_PAD, card_art_rect

    window, _calls = gallery
    bar = window.grid.rail
    assert f"margin: {CARD_TOP_PAD}px 0px 4px 0px" in window.grid.styleSheet()
    bar.setValue(0)
    opt = QStyleOptionSlider()  # initStyleOption is protected: fill it by hand
    opt.initFrom(bar)
    opt.orientation = Qt.Orientation.Vertical
    opt.minimum, opt.maximum = bar.minimum(), bar.maximum()
    opt.pageStep, opt.sliderPosition = bar.pageStep(), bar.value()
    opt.sliderValue = bar.value()
    opt.subControls = QStyle.SubControl.SC_All
    slider = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt,
                                        QStyle.SubControl.SC_ScrollBarSlider, bar)
    first = window.grid.visualRect(window.grid.indexFromItem(window.grid.item(0)))
    first_card_top = card_art_rect(first).top()
    assert abs(slider.top() - first_card_top) <= 1, (slider.top(), first_card_top)


def test_other_scrollbars_keep_their_flush_top():
    """The new top inset defaults to 0: the holiday viewer and event manager
    rails still open flush with their first row."""
    from utils.ui_helpers import scrollbar_stylesheet

    sheet = scrollbar_stylesheet(APP_CONFIG.DARK_PALETTE, bottom_margin=6)
    assert "margin: 0px 0px 6px 0px" in sheet
