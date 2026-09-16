"""Tests for ui.widgets.window_chrome: the shared caption row and the
no-op Windows style tweak on non-Windows platforms."""
from PyQt6.QtWidgets import QWidget

from config import APP_CONFIG
from ui.widgets.window_chrome import WindowTitleBar, apply_windows_styles


def test_title_bar_without_title_hides_minimize(qtbot):
    closed = []
    bar = WindowTitleBar(lambda: closed.append(1))
    host = QWidget()
    qtbot.addWidget(host)
    host.setLayout(bar)
    assert bar._title_label is None
    assert not bar.minimize_button.isVisible()  # hidden, not wired
    bar.exit_button.click()
    assert closed == [1]


def test_title_bar_with_title_and_minimize(qtbot):
    closed, minimized = [], []
    bar = WindowTitleBar(lambda: closed.append(1), on_minimize=lambda: minimized.append(1),
                         title="Window Title")
    host = QWidget()
    qtbot.addWidget(host)
    host.setLayout(bar)
    assert bar._title_label is not None
    assert bar._title_label.objectName() == "WindowTitleLabel"
    assert bar._title_label.text() == "Window Title"
    bar.exit_button.click()
    bar.minimize_button.click()
    assert closed == [1] and minimized == [1]


def test_title_bar_update_styles_sizes_and_fonts(qtbot):
    bar = WindowTitleBar(lambda: None, title="t")
    host = QWidget()
    qtbot.addWidget(host)
    host.setLayout(bar)
    bar.update_styles()
    assert bar.exit_button.size().width() == 30
    assert bar.exit_button.size().height() == 30
    assert bar.exit_button.styleSheet()  # styled from the shared builders
    assert bar.minimize_button.styleSheet()
    assert APP_CONFIG.FONT_FAMILY in bar._title_label.styleSheet()


def test_apply_windows_styles_is_noop_off_windows(qtbot):
    """On non-Windows (and without pywin32) the tweak must do nothing."""
    import sys

    if sys.platform == "win32":
        return  # nothing to prove on a real Windows box
    window = QWidget()
    qtbot.addWidget(window)
    apply_windows_styles(window)  # must not raise
