"""The "choose a console" screen: a rotating carousel of pixel-art consoles.

The selected console sits large in the middle with its name beneath; the others curve away on both
sides, smaller and fainter, and the ring wraps around (after the last console comes the first).
Hover any console and it glows. Left/Right (or the D-pad, or the wheel) rotate it, Enter (or A, or
a click on the middle one) opens the console, and a click on another one rotates it to the middle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from arcadia import pixelart
from arcadia.eras import era_of

VISIBLE = 3.0  # how many places either side of the middle are drawn
IDLE_GLOW = 0.5  # the selected console glows a little by itself
HOVER_GLOW = 1.0


@dataclass(frozen=True)
class Entry:
    view_id: str
    name: str
    count: int
    accent: str


def circular_delta(a: float, b: float, n: int) -> float:
    """Signed shortest distance from a to b around a ring of n."""
    return (b - a + n / 2) % n - n / 2


class ConsoleCarousel(QWidget):
    currentChanged = Signal(int)  # the middle console changed (index, or -1 when there are none)
    activated = Signal(int)  # open this console (Enter, or a click on the middle one)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumHeight(300)
        self._entries: list[Entry] = []
        self._index = 0
        self._offset = 0.0
        self._hover: int | None = None
        self._glow: dict[int, float] = {}
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(340)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._step_glow)

    # ----- data -----

    def set_entries(self, entries: list[Entry], select_id: str | None = None) -> None:
        self._anim.stop()
        self._entries = list(entries)
        index = 0
        if select_id is not None:
            for i, e in enumerate(self._entries):
                if e.view_id == select_id:
                    index = i
                    break
        self._index = index
        self._offset = float(index)
        self._hover = None
        self._glow = {}
        self.update()

    def entries(self) -> list[Entry]:
        return list(self._entries)

    def ids(self) -> list[str]:
        return [e.view_id for e in self._entries]

    def count(self) -> int:
        return len(self._entries)

    def index(self) -> int:
        return self._index

    def current_id(self) -> str | None:
        return self._entries[self._index].view_id if self._entries else None

    def set_index(self, index: int, animate: bool = True) -> None:
        """Rotate to this console, the short way round the ring."""
        n = len(self._entries)
        if not n:
            return
        index %= n
        if index == self._index and self._offset == float(index):
            return
        start = self._offset
        delta = circular_delta(start, float(index), n)
        self._index = index
        self._anim.stop()
        if animate and self.isVisible():
            self._anim.setStartValue(start)
            self._anim.setEndValue(start + delta)
            self._anim.start()
        else:
            self._offset = float(index)
        self.currentChanged.emit(index)
        self.update()

    def set_current_id(self, view_id: str) -> None:
        for i, e in enumerate(self._entries):
            if e.view_id == view_id:
                self.set_index(i)
                return

    def rotate(self, step: int) -> None:
        self.set_index(self._index + step)

    def _on_anim(self, value) -> None:
        self._offset = float(value) % max(1, len(self._entries))
        self.update()

    # ----- layout: where each console sits -----

    def _middle_width(self) -> int:
        return int(max(160, min(400, self.width() * 0.30, self.height() * 0.78)))

    def _place(self, i: int) -> tuple[float, float, float, float] | None:
        """(centre x, centre y, width in pixels, opacity) for entry i, or None if it isn't shown."""
        n = len(self._entries)
        d = circular_delta(self._offset, float(i), n)
        a = abs(d)
        if a > VISIBLE:
            return None
        mid = self._middle_width()

        def span(lo: float, hi: float) -> float:  # how far a is through the stretch lo..hi, from 0 to 1
            return max(0.0, min(a, hi) - lo) / (hi - lo)

        scale = max(0.3, 1.0 - 0.38 * span(0, 1) - 0.14 * span(1, 2) - 0.08 * span(2, 3.4))
        reach = 0.86 * span(0, 1) + 0.50 * span(1, 2) + 0.36 * span(2, 3.4)  # in middle-widths, so neighbours never overlap
        x = self.width() / 2 + math.copysign(reach * mid, d)
        y = self.height() * 0.42 + min(a, 2.5) * mid * 0.03  # the sides sit a touch lower, like a ring seen from above
        opacity = max(0.0, min(1.0, 1.0 - 0.24 * a, (VISIBLE - a) * 1.2))
        return x, y, mid * scale, opacity

    def _rect(self, place: tuple[float, float, float, float]) -> QRectF:
        x, y, width, _ = place
        return QRectF(x - width / 2, y - width * pixelart.H / pixelart.W / 2, width, width * pixelart.H / pixelart.W)

    def _hit(self, pos: QPointF) -> int | None:
        best = None
        for i in range(len(self._entries)):
            place = self._place(i)
            if place is None or place[3] < 0.15:
                continue
            if self._rect(place).adjusted(-6, -6, 6, 6).contains(pos):
                dist = abs(circular_delta(self._offset, float(i), len(self._entries)))
                if best is None or dist < best[0]:
                    best = (dist, i)
        return best[1] if best else None

    # ----- painting -----

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._entries)
        if not n:
            painter.end()
            return
        order = sorted(range(n), key=lambda i: -abs(circular_delta(self._offset, float(i), n)))
        for i in order:
            place = self._place(i)
            if place is None or place[3] <= 0.01:
                continue
            self._paint_one(painter, i, place)
        self._paint_title(painter)
        painter.end()

    def _paint_one(self, painter: QPainter, i: int, place) -> None:
        entry = self._entries[i]
        x, y, width, opacity = place
        rect = self._rect(place)
        intensity = self._glow.get(i, 0.0)
        accent = QColor(entry.accent).lighter(135)
        painter.save()
        # a hovered console comes fully forward: solid, so its glow doesn't show through it
        opacity = opacity + (1.0 - opacity) * min(1.0, intensity)
        painter.setOpacity(opacity)

        # a soft pool of light on the floor under it
        shadow = QRadialGradient(QPointF(x, rect.bottom() + width * 0.04), width * 0.55)
        shadow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), int(70 + 90 * intensity)))
        shadow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        painter.setBrush(shadow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.save()
        painter.translate(x, rect.bottom() + width * 0.04)
        painter.scale(1.0, 0.16)
        painter.translate(-x, -(rect.bottom() + width * 0.04))
        painter.drawEllipse(QPointF(x, rect.bottom() + width * 0.04), width * 0.55, width * 0.55)
        painter.restore()

        pixel_width = max(32, int(round(width / 8.0)) * 8)  # whole-ish pixel size keeps the edges crisp, and the cache small
        if intensity > 0.01:
            halo = pixelart.glow(entry.view_id, pixel_width, accent.name())
            pad = pixelart.glow_padding(pixel_width)
            scale = width / pixel_width
            painter.save()
            target = QRectF(rect.left() - pad * scale, rect.top() - pad * scale, halo.width() * scale, halo.height() * scale)
            for strength in (1.0, 0.8):  # twice: a bright core and a wide soft edge
                painter.setOpacity(opacity * min(1.0, intensity * strength * 1.3))
                painter.drawPixmap(target, halo, QRectF(halo.rect()))
            painter.restore()
        sprite = pixelart.scaled(entry.view_id, pixel_width)
        painter.drawPixmap(rect, sprite, QRectF(sprite.rect()))
        if i == self._hover and i != self._index:
            self._paint_label(painter, entry.name, QPointF(x, rect.bottom() + width * 0.16), 14, 0.9)
        painter.restore()

    def _paint_title(self, painter: QPainter) -> None:
        entry = self._entries[self._index]
        mid = self._middle_width()
        top = self.height() * 0.42 + mid * pixelart.H / pixelart.W / 2 + mid * 0.16
        self._paint_label(painter, entry.name.upper(), QPointF(self.width() / 2, top), 30, 1.0, spacing=3.0, bold=True)
        sub = "Empty" if not entry.count else f"{entry.count} game{'s' if entry.count != 1 else ''}"
        era = era_of(entry.view_id)
        if era:
            sub = f"{era.upper()}   ·   {sub}"
        self._paint_label(painter, sub, QPointF(self.width() / 2, top + 36), 15, 0.6)
        if self.count() > 1:
            self._paint_dots(painter, QPointF(self.width() / 2, top + 66))

    def _paint_label(self, painter: QPainter, text: str, centre: QPointF, pixels: int, alpha: float, spacing: float = 0.0, bold: bool = False) -> None:
        font = QFont(self.font())
        font.setPixelSize(pixels)
        font.setWeight(QFont.Weight.ExtraBold if bold else QFont.Weight.Medium)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(236, 238, 244, int(255 * alpha)))
        box = QRectF(centre.x() - self.width() / 2, centre.y() - pixels, self.width(), pixels * 2)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(self.width() * 0.9)))
        painter.restore()

    def _paint_dots(self, painter: QPainter, centre: QPointF) -> None:
        """A row of dots under the name showing where you are in the ring (collapses to a bar when there are many)."""
        n = self.count()
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        if n <= 14:
            gap = 14
            start = centre.x() - (n - 1) * gap / 2
            for i in range(n):
                active = i == self._index
                painter.setBrush(QColor(255, 255, 255, 230 if active else 60))
                r = 4.0 if active else 2.5
                painter.drawEllipse(QPointF(start + i * gap, centre.y()), r, r)
        else:
            width = 220.0
            painter.setBrush(QColor(255, 255, 255, 50))
            painter.drawRoundedRect(QRectF(centre.x() - width / 2, centre.y() - 2, width, 4), 2, 2)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QPointF(centre.x() - width / 2 + width * (self._index / (n - 1)), centre.y()), 6, 6)
        painter.restore()

    # ----- glow animation -----

    def _targets(self) -> dict[int, float]:
        targets = {i: 0.0 for i in range(len(self._entries))}
        if self._entries:
            targets[self._index] = IDLE_GLOW
        if self._hover is not None:
            targets[self._hover] = HOVER_GLOW
        return targets

    def _step_glow(self) -> None:
        moving = False
        for i, target in self._targets().items():
            now = self._glow.get(i, 0.0)
            if abs(now - target) < 0.02:
                new = target
            else:
                new = now + (target - now) * 0.22  # ease toward the target
                moving = True
            if new > 0:
                self._glow[i] = new
            else:
                self._glow.pop(i, None)
        self.update()
        if not moving:
            self._tick.stop()

    def _glow_changed(self) -> None:
        if not self._tick.isActive():
            self._tick.start()

    # ----- input -----

    def mouseMoveEvent(self, event) -> None:
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit is not None else Qt.CursorShape.ArrowCursor)
            self._glow_changed()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self._glow_changed()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus()
        hit = self._hit(event.position())
        if hit is None:
            return
        if hit == self._index:
            self.activated.emit(hit)
        else:
            self.set_index(hit)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self.rotate(-1 if delta > 0 else 1)
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._offset = float(self._index)  # no spin on first show
        self._glow_changed()
        self._warm = [e.view_id for e in self._entries]
        QTimer.singleShot(0, self._warm_next)

    def _warm_next(self) -> None:
        """Draw the 3D renders ahead of time, one per tick, so spinning the ring never waits on one."""
        while getattr(self, "_warm", None):
            view_id = self._warm.pop(0)
            pixelart.sprite_image(view_id)  # cached after the first time
            QTimer.singleShot(8, self._warm_next)
            return

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.rotate(-1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.rotate(1)
        elif key == Qt.Key.Key_Home:
            self.set_index(0)
        elif key == Qt.Key.Key_End:
            self.set_index(self.count() - 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._entries:
                self.activated.emit(self._index)
        elif event.text().isalpha() and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self.jump_to_letter(event.text())
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def jump_to_letter(self, letter: str) -> bool:
        """Rotate to the next console whose name starts with this letter (wrapping)."""
        letter = letter.lower()
        n = len(self._entries)
        for step in range(1, n + 1):
            i = (self._index + step) % n
            if self._entries[i].name.lower().startswith(letter):
                self.set_index(i)
                return True
        return False
