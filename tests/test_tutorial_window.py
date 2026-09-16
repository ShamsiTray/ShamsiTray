"""Tests for ui.windows.tutorial_window: the first-run welcome guide."""
from PyQt6.QtGui import QMovie

from config import APP_CONFIG
from ui.windows.tutorial_window import TutorialWindow


def test_tutorial_window_layout(qtbot):
    window = TutorialWindow()
    qtbot.addWidget(window)
    assert window.width() == 500 and window.height() == 365
    assert window.windowTitle() == "Welcome Guide"
    assert "نوار وظیفه" in window.message_label.text()  # taskbar pinning hint
    assert window.message_label.wordWrap()
    assert window.close_button.text() == "بستن آموزش"


def test_tutorial_loads_real_gif(qtbot):
    """With the bundled welcome.gif present, the movie starts running."""
    window = TutorialWindow()
    qtbot.addWidget(window)
    assert window.movie is not None
    assert window.movie.isValid()
    assert window.movie.state() == QMovie.MovieState.Running
    window._close_tutorial()  # stop the movie before the widget is torn down


def test_tutorial_gif_missing_falls_back_to_text(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "TUTORIAL_GIF_PATH", tmp_path / "gone.gif")
    window = TutorialWindow()
    qtbot.addWidget(window)
    assert "GIF file not found." in window.gif_label.text()
    assert not hasattr(window, "movie")


def test_close_button_stops_movie_and_closes(qtbot):
    window = TutorialWindow()
    qtbot.addWidget(window)
    window.show()
    window.close_button.click()
    assert window.movie is None        # movie released
    assert not window.isVisible()      # window closed


def test_update_styles_applies_theme(qtbot):
    window = TutorialWindow()
    qtbot.addWidget(window)
    palette = APP_CONFIG.get_current_palette()
    window.update_styles()
    assert palette["TEXT_COLOR"] in window.message_label.styleSheet()
    assert palette["ACCENT_COLOR"] in window.close_button.styleSheet()
    assert window.close_button.height() == 50
