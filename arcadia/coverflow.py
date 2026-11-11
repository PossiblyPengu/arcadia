"""Cover-flow carousel: the selected game sits large in the middle, its neighbours
tilt back and fade on either side, and the selection glides between them."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

COVER_W = 200
COVER_H = 280
VISIBLE_RADIUS = 4.5


class CoverFlow(QWidget):
    currentChanged = Signal(int)  # index, or -1 when empty
    activated = Signal(int)  # Enter, or clicking the centered cover

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(COVER_H + 90)
        self._items: list[tuple[str, str, QPixmap]] = []  # (key, title, cover)
        self._index = 0
        self._offset = 0.0
        self._accent = QColor("#3e89d6")
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    # ----- data -----

    def set_items(self, items: list[tuple[str, str, QPixmap]], select_key: str | None = None) -> None:
        self._anim.stop()
        self._items = list(items)
        index = 0
        if select_key is not None:
            for i, (key, _title, _cover) in enumerate(self._items):
                if key == select_key:
                    index = i
                    break
        self._index = index
        self._offset = float(index)
        self.update()
        self.currentChanged.emit(index if self._items else -1)

    def set_accent(self, color: QColor) -> None:
        self._accent = color
        self.update()

    def count(self) -> int:
        return len(self._items)

    def index(self) -> int:
        return self._index

    def current_key(self) -> str | None:
        return self._items[self._index][0] if self._items else None

    def set_index(self, index: int, animate: bool = True) -> None:
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, index))
        changed = index != self._index
        self._index = index
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._offset)
            self._anim.setEndValue(float(index))
            self._anim.start()
        else:
            self._offset = float(index)
            self.update()
        if changed:
            self.currentChanged.emit(index)

    def _on_anim(self, value) -> None:
        self._offset = float(value)
        self.update()

    # ----- input -----

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Left:
            self.set_index(self._index - 1)
        elif key == Qt.Key.Key_Right:
            self.set_index(self._index + 1)
        elif key == Qt.Key.Key_Home:
            self.set_index(0)
        elif key == Qt.Key.Key_End:
            self.set_index(len(self._items) - 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._items:
                self.activated.emit(self._index)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        self.set_index(self._index + (-1 if event.angleDelta().y() > 0 else 1))

    def mousePressEvent(self, event) -> None:
        if not self._items:
            return
        steps = round((event.position().x() - self.width() / 2) / self._spacing())
        if steps == 0:
            self.activated.emit(self._index)
        else:
            self.set_index(self._index + steps)

    # ----- drawing -----

    @staticmethod
    def _spacing() -> float:
        return COVER_W * 0.62

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if not self._items:
            painter.setPen(QColor(200, 200, 210))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No games here yet.\nCheck the ROM folder in Settings."
            )
            painter.end()
            return

        cx = self.width() / 2
        cy = (self.height() - 50) / 2
        spacing = self._spacing()
        visible = [i for i in range(len(self._items)) if abs(i - self._offset) <= VISIBLE_RADIUS]
        # Draw the farthest covers first so the centre one sits on top.
        for i in sorted(visible, key=lambda i: -abs(i - self._offset)):
            _key, _title, cover = self._items[i]
            d = i - self._offset
            dist = abs(d)
            scale = max(0.5, 1 - 0.16 * dist)
            w = cover.width() * scale
            h = cover.height() * scale
            rect = QRectF(cx + d * spacing - w / 2, cy - h / 2, w, h)

            painter.setOpacity(max(0.25, 1 - 0.18 * dist))
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(rect, cover, QRectF(cover.rect()))
            painter.restore()

            if dist < 0.5:
                painter.setOpacity(1.0)
                painter.setPen(QPen(self._accent, 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 12, 12)

        painter.setOpacity(1.0)
        title = self._items[self._index][1]
        font = painter.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(240, 240, 245))
        painter.drawText(
            QRectF(0, self.height() - 44, self.width(), 40), Qt.AlignmentFlag.AlignCenter, title
        )
        painter.end()
