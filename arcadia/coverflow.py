"""Cover-flow carousel: the selected game sits large in the middle with a glowing
ring and a reflection, its neighbours shrink and fade to either side, and the
selection glides between them.

Covers are loaded lazily. Each item carries a loader function, and only the covers
near the selection are kept in memory, so large libraries stay fast.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

COVER_W = 280
COVER_H = 392
VISIBLE_RADIUS = 4.5
CACHE_KEEP = 12  # covers kept on each side of the selection
CACHE_LIMIT = 48
REFLECTION = 0.40  # reflection height as a fraction of the cover

Item = tuple[str, str, Callable[[], QPixmap]]  # (key, title, cover loader)


def _sort_key(title: str) -> str:
    return title.lstrip("★ ").lower()


class CoverFlow(QWidget):
    currentChanged = Signal(int)  # index, or -1 when empty
    activated = Signal(int)  # Enter, or clicking the centered cover

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(340)
        self._items: list[Item] = []
        self._covers: dict[str, QPixmap] = {}
        self._reflections: dict[str, QPixmap] = {}
        self._index = 0
        self._offset = 0.0
        self._accent = QColor("#3e89d6")
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    # ----- data -----

    def set_items(self, items: list[Item], select_key: str | None = None) -> None:
        self._anim.stop()
        self._items = list(items)
        self._covers.clear()
        self._reflections.clear()
        index = 0
        if select_key is not None:
            for i, (key, _title, _loader) in enumerate(self._items):
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

    def current_title(self) -> str:
        return self._items[self._index][1] if self._items else ""

    def titles(self) -> list[str]:
        return [title for _key, title, _loader in self._items]

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

    def jump_to_letter(self, letter: str) -> bool:
        """Select the next title starting with letter (wraps around). Returns True if found."""
        letter = letter.lower()
        n = len(self._items)
        for step in range(1, n + 1):
            i = (self._index + step) % n
            if _sort_key(self._items[i][1]).startswith(letter):
                self.set_index(i)
                return True
        return False

    def _on_anim(self, value) -> None:
        self._offset = float(value)
        self.update()

    # ----- lazy covers -----

    def _cover(self, i: int) -> QPixmap:
        key, _title, loader = self._items[i]
        pix = self._covers.get(key)
        if pix is None:
            pix = loader()
            self._covers[key] = pix
            self._trim()
        return pix

    def _trim(self) -> None:
        if len(self._covers) <= CACHE_LIMIT:
            return
        lo = max(0, self._index - CACHE_KEEP)
        hi = min(len(self._items), self._index + CACHE_KEEP + 1)
        keep = {self._items[j][0] for j in range(lo, hi)}
        for key in list(self._covers):
            if key not in keep:
                del self._covers[key]
                self._reflections.pop(key, None)

    def _reflection(self, key: str, cover: QPixmap) -> QPixmap:
        cached = self._reflections.get(key)
        if cached is not None:
            return cached
        h = max(1, int(cover.height() * REFLECTION))
        flipped = cover.transformed(QTransform().scale(1, -1))
        refl = QPixmap(cover.width(), h)
        refl.fill(Qt.GlobalColor.transparent)
        painter = QPainter(refl)
        painter.drawPixmap(0, 0, flipped, 0, 0, cover.width(), h)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fade = QLinearGradient(0, 0, 0, h)
        fade.setColorAt(0.0, QColor(0, 0, 0, 95))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(refl.rect(), fade)
        painter.end()
        self._reflections[key] = refl
        return refl

    # ----- input -----

    def keyPressEvent(self, event) -> None:
        key = event.key()
        text = event.text()
        if key == Qt.Key.Key_Left:
            self.set_index(self._index - 1)
        elif key == Qt.Key.Key_Right:
            self.set_index(self._index + 1)
        elif key == Qt.Key.Key_PageUp:
            self.set_index(self._index - 6)
        elif key == Qt.Key.Key_PageDown:
            self.set_index(self._index + 6)
        elif key == Qt.Key.Key_Home:
            self.set_index(0)
        elif key == Qt.Key.Key_End:
            self.set_index(len(self._items) - 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._items:
                self.activated.emit(self._index)
        elif text and text.isalnum() and not event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            self.jump_to_letter(text)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() or event.angleDelta().x()
        self.set_index(self._index + (-1 if delta > 0 else 1))

    def mousePressEvent(self, event) -> None:
        if not self._items:
            return
        steps = round((event.position().x() - self.width() / 2) / self._spacing())
        if steps == 0:
            self.activated.emit(self._index)
        else:
            self.set_index(self._index + steps)

    # ----- drawing -----

    def _scale(self) -> float:
        return max(0.45, min(1.25, (self.height() - 110) / COVER_H))

    def _spacing(self) -> float:
        return COVER_W * self._scale() * 0.58

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if not self._items:
            painter.setPen(QColor(200, 202, 212))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nothing here yet.")
            painter.end()
            return

        cx = self.width() / 2
        cy = self.height() * 0.46
        base = self._scale()
        spacing = self._spacing()
        visible = [i for i in range(len(self._items)) if abs(i - self._offset) <= VISIBLE_RADIUS]
        # Draw the farthest covers first so the centre one sits on top.
        for i in sorted(visible, key=lambda i: -abs(i - self._offset)):
            key = self._items[i][0]
            cover = self._cover(i)
            d = i - self._offset
            dist = abs(d)
            scale = base * max(0.55, 1 - 0.16 * dist)
            w = cover.width() * scale
            h = cover.height() * scale
            rect = QRectF(cx + d * spacing - w / 2, cy - h / 2, w, h)
            fade = max(0.25, 1 - 0.18 * dist)

            # Reflection under the cover.
            refl = self._reflection(key, cover)
            refl_rect = QRectF(rect.left(), rect.bottom() + 4, w, refl.height() * scale)
            painter.setOpacity(fade)
            painter.drawPixmap(refl_rect, refl, QRectF(refl.rect()))

            painter.setOpacity(fade)
            path = QPainterPath()
            path.addRoundedRect(rect, 12, 12)
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(rect, cover, QRectF(cover.rect()))
            painter.restore()

            if dist < 0.5:
                painter.setOpacity(1.0)
                painter.setPen(QPen(self._accent, 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), 14, 14)
        painter.end()
