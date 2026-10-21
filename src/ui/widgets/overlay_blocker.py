"""
Overlay Blocker
---------------

The dimming child a host window lays behind its overlay: a translucent rounded
sheet that click-blocks the surface behind it (while «افزودن رویداد» or a confirm
card is open, the host behind it must not react to clicks) and also signals the
modal state. The calendar popup and the event manager both host their overlays
over one of these - this is the review's "one OverlayHost" for that cloned pair.
"""
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QWidget


class OverlayBlocker(QWidget):
    """The scrim behind a host's overlay; sized to the host, never interactive."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        # rgba(0,0,0,75) + the 1px margin keep the sheet inside the host's own
        # rounded 26px window frame instead of covering its border.
        self.setStyleSheet("background-color: rgba(0, 0, 0, 75); border-radius: 26px; margin: 1px;")
        self.hide()

    def present(self):
        """Size to the host and show, just beneath the overlay card the host
        raises afterwards."""
        host = self.parentWidget()
        self.setGeometry(QRect(0, 0, host.width(), host.height()))
        self.show()
        self.raise_()
