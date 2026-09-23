"""
Go To Date Widget
---------------------

This module contains custom dialog-like widgets used in the application,
such as the 'Go To Date' panel for the calendar.
"""
import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QRegularExpression
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRegularExpressionValidator, QPen
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QHBoxLayout

from config import APP_CONFIG
from utils.date_utils import from_persian_digits, persian_month_name, to_persian_digits
from utils.ui_helpers import (DigitsFirstCombo, YearRangeValidationMixin,
                              accent_button_stylesheet, combo_stylesheet,
                              danger_button_stylesheet)

# The «NN - month» items mix digits with Persian text, which is bidi-ambiguous:
# their visual order depends on the base direction of whatever paints them.
# DigitsFirstCombo pins closed label and popup rows to the digits-first order
# («۰۶ - شهریور") on every platform.


def _year_range_hint(min_year: int, max_year: int) -> str:
    """The live range message: the red border says "wrong", this says what
    "right" is."""
    return f"سال باید بین {to_persian_digits(min_year)} تا {to_persian_digits(max_year)} باشد"


class GoToDateWindow(YearRangeValidationMixin, QWidget):
    """A small, non-movable window to jump to a specific month and year."""
    date_selected = pyqtSignal(int, int)
    # The app-wide supported Jalali range (config), kept as class aliases for
    # readability and backwards-compatible access from tests.
    MIN_YEAR = APP_CONFIG.SUPPORTED_MIN_YEAR
    MAX_YEAR = APP_CONFIG.SUPPORTED_MAX_YEAR

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("برو به تاریخ")
        self._initial_height = 200
        self.setFixedSize(200, self._initial_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._setup_ui()
        self.update_styles()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 15
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        pen = QPen(QColor(APP_CONFIG.current_palette['MENU_BORDER_COLOR']))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.title_label = QLabel("برو به تاریخ")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        self.month_combo = DigitsFirstCombo()
        self.month_combo.setMaxVisibleItems(5)
        month_names = [f"{to_persian_digits(str(i).zfill(2))} - {persian_month_name(i)}" for i in range(1, 13)]
        for name in month_names:
            self.month_combo.addItem(name)
            last_index = self.month_combo.count() - 1
            self.month_combo.setItemData(last_index, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)
        main_layout.addWidget(self.month_combo)

        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("سال (از ۱۲۰۰ تا ۱۶۰۰)")
        regex = QRegularExpression("^[0-9۰-۹]{0,4}$")
        validator = QRegularExpressionValidator(regex)
        self.year_input.setValidator(validator)
        self.year_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.year_input)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        main_layout.addWidget(self.error_label)
        # The mixin shows this same label (with the range text) for as long as
        # the typed year is out of range: the red border alone left the user
        # guessing which years WOULD be accepted.
        self.year_hint_label = self.error_label

        today = jdatetime.date.today()
        self.month_combo.setCurrentIndex(today.month - 1)
        self.year_input.setText(to_persian_digits(today.year))

        main_layout.addStretch(1)

        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("تایید")
        self.cancel_button = QPushButton("لغو")
        button_layout.addWidget(self.confirm_button)
        button_layout.addWidget(self.cancel_button)

        self.confirm_button.clicked.connect(self._on_confirm)
        self.cancel_button.clicked.connect(self.close)
        # Enter goes through the BUTTON, not straight to _on_confirm: a disabled
        # تایید button then swallows the key on an empty/invalid year exactly
        # like a click would. _on_confirm keeps its own guard for other callers.
        self.year_input.returnPressed.connect(self.confirm_button.click)
        self.year_input.textChanged.connect(self._clear_error)
        self.year_input.textChanged.connect(self._update_year_error_state)
        self.year_input.textChanged.connect(self._update_confirm_state)
        # The button state always derives from the CURRENT input (an empty year
        # is not submittable even before any edit event), so derive it once here
        # too and the card never opens with a stale button.
        self._update_confirm_state()

        main_layout.addLayout(button_layout)

    # --- YearRangeValidationMixin host hooks ---

    def _year_bounds(self):
        return self.MIN_YEAR, self.MAX_YEAR

    def _year_hint_text(self) -> str:
        return _year_range_hint(self.MIN_YEAR, self.MAX_YEAR)

    def _error_label_height(self) -> int:
        """The height the error/hint label actually needs at the card's inner width.

        A word-wrapped QLabel's sizeHint badly over-estimates (Qt's wrapped-text
        hint heuristic prefers a roughly square block), which used to grow this
        card far past the message and leave a band of dead space under it before
        the button row. ``heightForWidth`` answers the exact height the label
        gets once the layout assigns the inner width.
        """
        self.error_label.ensurePolished()
        margins = self.layout().contentsMargins()
        inner_width = 200 - margins.left() - margins.right()
        height = self.error_label.heightForWidth(inner_width)
        if height <= 0:  # no heightForWidth (defensive): fall back to the hint
            height = self.error_label.sizeHint().height()
        return height

    def _resize_for_error(self):
        """Fit the card exactly around the visible message.

        The label's measured height is pinned with setFixedHeight so the layout
        can never inflate it beyond the text, then the card takes the layout's
        own required height - never smaller than the base card.
        """
        self.error_label.setFixedHeight(self._error_label_height())
        needed = self.layout().sizeHint().height()
        self.setFixedSize(200, max(self._initial_height, needed))

    def _year_is_submittable(self) -> bool:
        """True when the current input can actually be confirmed.

        Distinct from ``_year_is_out_of_range`` (shared mixin): an EMPTY or
        non-numeric field is not "out of range" (the red-border hint must not
        claim otherwise), but it is definitely not submittable - so the تایید
        button's enabling comes from this predicate instead: empty / non-numeric
        / out of range all keep it greyed out.
        """
        text = self.year_input.text().strip()
        if not text:
            return False
        try:
            year = int(from_persian_digits(text))
        except (ValueError, TypeError):
            return False
        return self.MIN_YEAR <= year <= self.MAX_YEAR

    def _update_confirm_state(self, *_args):
        """Grey the تایید button in and out with the input's submittability.

        Driven by textChanged (plus one initial call), it covers every case the
        out-of-range flip cannot see: the empty and non-numeric states never
        change the mixin's error state, so without this the button would stay
        enabled after clearing the field. The shared accent style dims disabled
        buttons.
        """
        self.confirm_button.setEnabled(self._year_is_submittable())

    def _on_year_error_changed(self, errored: bool):
        """Grow/shrink the fixed-size card with the live range hint.

        Same sizing rule _show_error uses for confirm-time errors, applied
        whenever the live out-of-range state flips.
        """
        if errored:
            self._resize_for_error()
        else:
            self.setFixedSize(200, self._initial_height)

    def _year_style_kwargs(self, errored: bool) -> dict:
        kwargs = {"padding": "5px", "center_text": True}
        if not errored:
            kwargs["placeholder_color"] = APP_CONFIG.get_current_palette()['GREY_COLOR']
        return kwargs

    def _clear_error(self):
        """Clear confirm-time errors when the user types.

        The LIVE range hint is owned by the mixin's year-error state: while that
        state is set this must not hide the label - this handler runs before
        ``_update_year_error_state`` on textChanged, and hiding here would
        flicker the message away on every keystroke of an out-of-range year.
        """
        if getattr(self, "_year_error", False):
            return
        if self.error_label.isVisible():
            self.error_label.hide()
            self.setFixedSize(200, self._initial_height)

    def _show_error(self, message: str):
        """Show error and grow the window to fit it.

        The label is measured exactly (``heightForWidth`` at the card's inner
        width), so any wrap the fixed 200px width produces fits - and the card
        no longer grows past the message, which used to leave dead space between
        the hint and the button row.
        """
        self.error_label.setText(message)
        self.error_label.show()
        self._resize_for_error()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet("GoToDateWindow { background-color: transparent; }")

        self.title_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 18px; font-weight: bold; border: none; background: transparent;")

        self.error_label.setStyleSheet(f"color: red; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; border: none; background: transparent;")

        self.month_combo.setStyleSheet(combo_stylesheet(
            palette,
            padding="5px",
            center_text=True,
            dropdown_bg=palette['BACKGROUND_COLOR'],
            dropdown_border_key='MENU_BORDER_COLOR',
            scrollbar_width=8,
            zero_drop_down=False))
        self.month_combo.view().setStyleSheet(f"QListView {{ background-color: {palette['BACKGROUND_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}")

        self._apply_year_style()

        self.confirm_button.setStyleSheet(accent_button_stylesheet(palette))
        self.cancel_button.setStyleSheet(danger_button_stylesheet(palette))

    def _on_confirm(self):
        """Accept the displayed month/year (تایید click, or Enter via it).

        Enter is wired to ``confirm_button.click`` so a disabled button swallows
        the key; this guard is the second layer - ANY path into here (a direct
        call included) must prove the year submittable first, and
        ``_year_is_submittable`` stays the single source of truth. An
        un-submittable year is ignored silently, matching what a disabled button
        does.
        """
        if not self._year_is_submittable():
            return
        year = int(from_persian_digits(self.year_input.text().strip()))
        month = self.month_combo.currentIndex() + 1
        self.date_selected.emit(year, month)
        self.close()
