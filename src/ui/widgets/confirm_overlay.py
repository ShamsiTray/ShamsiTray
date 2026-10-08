"""
In-Calendar Confirm Overlay
---------------------------

`ConfirmOverlay` is a `ConfirmCard` living *inside* the calendar popup rather
than in a top-level dialog. It looks identical to `ConfirmDialog` but belongs to
its host: the calendar parents it, dims the grid behind it with
``overlay_blocker``, and hides it again. So a confirmation is part of the popup
instead of a separate window floating over it - not draggable, not focusable, and
gone the moment the calendar closes.

Design notes:
- No drag, no window flags, no modality, no ``exec()``. The dialog's whole
  drag/center/screen-clamp machinery is meaningless for a child that cannot leave
  its parent, so none of it is mixed in.
- It is **persistent and reused**: the calendar builds it once and shows/hides
  it. Creating one per invocation would mean either a ``destroyed`` handler to
  clear the host's reference (the Go-To-Date path) or a risk of that reference
  outliving the C++ object.
- Two fixed shapes rather than one configurable card, because the calendar asks
  for different button counts: the distance notice is a single-button notice, the
  delete confirmation a two-button ask. Each instance keeps one button layout for
  life and only its text is updated between uses. Fixed *shape* is not fixed
  *content*: the delete card raises its description line per question and keeps
  the preview box for the event text alone.
- The host owns geometry, visibility and stacking; the overlay only reports what
  was chosen.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from ui.widgets.confirm_card import ConfirmCard


class ConfirmOverlay(ConfirmCard, QWidget):
    """A themed card drawn inside the calendar, not draggable, reused in place."""

    chosen = pyqtSignal(str)

    def __init__(self, parent, title: str, *, detail: str = "",
                 confirm_text: str = "تایید", cancel_text: str = "انصراف",
                 danger: bool = True, width: int = 265,
                 glyph: str = None, notice: bool = False):
        """Build a fixed-shape overlay card.

        ``notice=True`` yields the single-button shape (a «باشه» dismiss), which
        is what a read-only notice wants; otherwise the two-button
        confirm/cancel shape is built. ``width`` is a floor - the card widens
        itself if a button caption ever needs more room.
        """
        if notice:
            actions = [("باشه", "danger" if danger else "accent")]
        else:
            actions = [(confirm_text, "danger" if danger else "accent"),
                       (cancel_text, "ghost")]
        # No message at construction: the notice shape carries everything in its
        # detail box, and the ask raises its question per use via `set_message`.
        super().__init__(parent, title, "", detail=detail, danger=danger,
                         width=width, glyph=glyph, actions=actions)
        # Named accessors for both shapes. `ConfirmCard` only defines them for the
        # default two-button flow, but a host holding a fixed-shape overlay should
        # not have to remember which constructor flag produced it.
        self.confirm_button = self.buttons[0]
        self.cancel_button = self.buttons[1] if len(self.buttons) > 1 else None
        self.chosen.connect(self._on_chosen)

    def _finish_choice(self, kind: str) -> None:
        """Report the choice and get out of the way.

        The host clears the pending state and hides the overlay; doing it here
        would mean reaching into the calendar from a widget that only owns itself.
        """
        self.hide()
        self.chosen.emit(self.choice)

    def _on_chosen(self, text: str) -> None:
        """Hook for subclasses; the calendar connects to ``chosen`` directly."""

    def set_message(self, text: str) -> None:
        """Refill the description line for the next use.

        The label mechanics live in ``ConfirmCard`` (shared with the dialog's
        in-place notice update); the overlay adds only its per-use state reset
        and the size re-measure.
        """
        super().set_message(text)
        self.choice = None
        self.adjustSize()

    def set_detail(self, text: str) -> None:
        """Refill the box for the next use, keeping the card visible/hidden as is."""
        super().set_detail(text)
        self.choice = None
        self.adjustSize()

    def center_in(self, host) -> None:
        """Center the card over ``host``'s rectangle (both are in the same space:
        the overlay is a direct child of the host)."""
        self.adjustSize()
        host_size = host.size()
        self.move((host_size.width() - self.width()) // 2,
                  (host_size.height() - self.height()) // 2)
