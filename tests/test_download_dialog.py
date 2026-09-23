"""Tests for ui.widgets.download_dialog: the themed installer-download card."""
from PyQt6.QtCore import Qt

from config import APP_CONFIG
from tests.qt_mousing import release
from ui.widgets.download_dialog import DownloadUpdateDialog, _mb_str

_MB = 1024 * 1024


def test_mb_str_persian_digits_one_decimal():
    assert _mb_str(0) == "۰.۰"
    assert _mb_str(_MB) == "۱.۰"
    assert _mb_str(int(1.5 * _MB)) == "۱.۵"
    assert _mb_str(int(12.34 * _MB)) == "۱۲.۳"


def test_dialog_initial_state_is_busy(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    assert dialog.width() == 340  # fixed card width
    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert dialog.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert (dialog.progress.minimum(), dialog.progress.maximum()) == (0, 0)  # busy
    assert "1.4.0" in dialog.message_label.text()
    assert dialog.progress.isTextVisible() is False


def test_set_progress_switches_to_determinate(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.set_progress(50 * _MB, 100 * _MB)
    assert (dialog.progress.minimum(), dialog.progress.maximum()) == (0, 100)
    assert dialog.progress.value() == 50
    # Persian percent + MB counters.
    assert "۵۰٪" in dialog.status_label.text()
    assert "۵۰.۰" in dialog.status_label.text() and "۱۰۰.۰" in dialog.status_label.text()


def test_set_progress_clamps_over_100(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.set_progress(150, 100)
    assert dialog.progress.value() == 100


def test_set_progress_unknown_total_returns_to_busy(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.set_progress(10, 100)          # determinate first
    dialog.set_progress(3 * _MB, -1)      # total became unknown
    assert dialog.progress.maximum() == 0  # back to the busy indicator
    assert "۳.۰" in dialog.status_label.text()


def test_cancel_button_emits_canceled_once(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    canceled, rejected = [], []
    dialog.canceled.connect(lambda: canceled.append(1))
    dialog.rejected.connect(lambda: rejected.append(1))
    dialog.cancel_button.click()
    assert canceled == [1]
    assert rejected == [1]


def test_dismiss_does_not_emit_canceled(qtbot):
    """UPD-4: the controller's post-success/failure close must not re-fire
    `canceled` - Qt's closeEvent -> reject() chain used to emit it every
    time, misreporting successful downloads as user cancellations."""
    dialog = DownloadUpdateDialog("1.0.0")
    fired = []
    dialog.canceled.connect(lambda: fired.append(1))
    dialog.show()
    dialog.dismiss()
    assert fired == []
    assert not dialog.isVisible()


def test_reject_path_emits_canceled(qtbot):
    """Esc / programmatic dismiss must abort the download too."""
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(1))
    dialog.reject()
    assert canceled == [1]


def test_update_styles_and_paint(qtbot):
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.resize(340, 180)
    palette = APP_CONFIG.get_current_palette()
    dialog.update_styles()
    assert palette["ACCENT_COLOR"] in dialog.status_label.styleSheet()
    assert palette["ACCENT_COLOR"] in dialog.progress.styleSheet()
    assert dialog.cancel_button.styleSheet()
    pixmap = dialog.grab()  # exercises paintEvent's rounded card
    assert not pixmap.isNull()


def test_message_label_uses_readable_text_color(qtbot):
    """The download card's one explanatory sentence must read as normal text,
    not the de-emphasised grey reserved for secondary/minor metadata."""
    palette = APP_CONFIG.get_current_palette()
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    assert palette["TEXT_COLOR"] in dialog.message_label.styleSheet()
    assert palette["GREY_COLOR"] not in dialog.message_label.styleSheet()


def test_message_label_height_fits_its_wrapped_text(qtbot):
    """Spacing regression: a one-line message must sit compactly under the
    title — the word-wrapped label's inflated sizeHint used to leave a band
    of dead air around it (title 25px + message 21px need rendered as
    28px + 29px inside a taller card)."""
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.adjustSize()
    dialog.show()
    margins = dialog.layout().contentsMargins()
    inner_width = dialog.width() - margins.left() - margins.right()
    needed = dialog.message_label.heightForWidth(inner_width)
    assert needed > 0
    assert dialog.message_label.height() == needed


def test_drag_from_blank_surface_moves_dialog(qtbot):
    """Dragging the blank card tracks the cursor 1:1 (unclamped)."""
    from PyQt6.QtCore import QPoint, QPointF, QEvent
    from PyQt6.QtGui import QMouseEvent
    dialog = DownloadUpdateDialog("1.4.0")
    qtbot.addWidget(dialog)
    dialog.resize(340, 180)
    dialog.show()
    dialog.move(100, 100)
    start = QPoint(dialog.x(), dialog.y())
    press_global = dialog.mapToGlobal(dialog.rect().center())
    press_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(170, 90),
                              QPointF(press_global),
                              Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                              Qt.KeyboardModifier.NoModifier)
    dialog.handle_drag_press(press_event)
    move_global = press_global + QPoint(25, 15)
    move_event = QMouseEvent(QEvent.Type.MouseMove, QPointF(170, 90),
                             QPointF(move_global),
                             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier)
    dialog.handle_drag_move(move_event)
    dialog.handle_drag_release(release(dialog))
    # 1:1 cursor tracking; a ±1px tolerance absorbs offscreen frame rounding.
    assert abs((dialog.x() - start.x()) - 25) <= 1
    assert abs((dialog.y() - start.y()) - 15) <= 1
