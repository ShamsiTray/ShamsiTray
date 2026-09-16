"""Shared Qt mouse-event builders for widget tests.

Offscreen tests cannot move the real cursor, so interactions are simulated
by sending synthesized QMouseEvent objects straight into the handlers.
"""
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent


def mouse_event(event_type: QEvent.Type, widget, local=(5, 5), *,
                button=Qt.MouseButton.LeftButton, buttons=None, global_pos=None):
    """Build a QMouseEvent over ``widget`` at ``local`` coords."""
    if global_pos is None:
        global_pos = widget.mapToGlobal(QPoint(int(local[0]), int(local[1])))
    return QMouseEvent(
        event_type,
        QPointF(float(local[0]), float(local[1])),
        QPointF(global_pos),
        button,
        button if buttons is None else buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def press(widget, local=(5, 5), **kwargs):
    return mouse_event(QEvent.Type.MouseButtonPress, widget, local, **kwargs)


def release(widget, local=(5, 5), **kwargs):
    return mouse_event(QEvent.Type.MouseButtonRelease, widget, local, **kwargs)


def move(widget, local=(5, 5), **kwargs):
    return mouse_event(QEvent.Type.MouseMove, widget, local, **kwargs)
