"""Tests for ui.widgets.overlay_blocker: the dim must actually paint."""
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

from ui.widgets.overlay_blocker import OverlayBlocker


def test_starts_hidden_under_its_host(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    blocker = OverlayBlocker(host)
    assert blocker.parentWidget() is host
    assert blocker.isHidden()


def test_present_darkens_the_covered_host(qtbot):
    """present() must not merely show the scrim: a named QWidget subclass
    paints stylesheet backgrounds only after the WA_StyledBackground opt-in
    (Qt grants them implicitly to exact QWidget instances, which the inline
    widget this class replaced was), and this exact regression once shipped a
    scrim that showed, blocked clicks and rendered nothing. Compare the same
    host grabbed with the scrim hidden against it grabbed with the scrim up."""
    host = QWidget()
    host.setStyleSheet("background-color: #ffffff;")
    host.resize(120, 90)
    blocker = OverlayBlocker(host)
    qtbot.addWidget(host)

    host.show()
    hidden = host.grab().toImage()
    blocker.present()
    shown = host.grab().toImage()

    assert blocker.isVisible()
    assert blocker.geometry() == host.rect()
    centre = QPoint(60, 45)  # inside the sheet, away from the rounded corners
    before = hidden.pixelColor(centre)
    after = shown.pixelColor(centre)
    assert before.lightness() >= 200, f"the white host did not render: {before.name()}"
    assert after.lightness() < before.lightness() - 30, \
        f"the scrim shows but paints nothing: {before.name()} vs {after.name()}"
