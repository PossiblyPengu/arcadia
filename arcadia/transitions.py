"""The zoom between the two screens: a snapshot of the screen you're leaving grows (or shrinks) and fades
away over the new one, so opening a console feels like moving into it."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ZoomOverlay(QWidget):
    DURATION = 260

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._snapshot: QPixmap | None = None
        self._grow = True
        self._t = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._finished)
        self.hide()

    def running(self) -> bool:
        return self._snapshot is not None

    def start(self, snapshot: QPixmap, grow: bool) -> None:
        """grow=True: going into a console (the old screen swells and fades). False: coming back (it shrinks away)."""
        self._anim.stop()
        self._snapshot, self._grow, self._t = snapshot, grow, 0.0
        self.setGeometry(self.parentWidget().rect() if self.parentWidget() else self.rect())
        self.raise_()
        self.show()
        self._anim.start()

    def finish(self) -> None:
        self._anim.stop()
        self._finished()

    def _on_value(self, value) -> None:
        self._t = float(value)
        self.update()

    def _finished(self) -> None:
        self._snapshot = None
        self.hide()

    def paintEvent(self, _event) -> None:
        if self._snapshot is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = 1.0 + (0.22 if self._grow else -0.10) * self._t
        w, h = self.width() * scale, self.height() * scale
        target = QRectF(QPointF((self.width() - w) / 2, (self.height() - h) / 2), QPointF((self.width() + w) / 2, (self.height() + h) / 2))
        painter.setOpacity(max(0.0, 1.0 - self._t))
        painter.drawPixmap(target, self._snapshot, QRectF(self._snapshot.rect()))
        painter.end()
