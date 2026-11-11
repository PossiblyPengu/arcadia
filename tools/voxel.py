"""A small voxel modeller and isometric renderer, for drawing the pictures that have no photograph.

Build-time tooling (needs PySide6 for drawing). A Model is a set of coloured cells; render() projects it at
the classic 2:1 isometric angle, shades the top, front (+y) and side (+x) faces differently, and returns a
QImage. tools/make_extra_art.py then pixelates that the same way as the photographs.

Axes: x runs down and to the right on screen, y down and to the left (the front faces +y), z up.
"""

from __future__ import annotations


from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygon

TOP_LIGHT, FRONT_LIGHT, SIDE_LIGHT = 1.12, 0.86, 0.60


class Model:
    def __init__(self):
        self.v: dict[tuple[int, int, int], str] = {}
        self._index = None

    def _dirty(self):
        self._index = None
        return self

    def box(self, x, y, z, w, d, h, c):
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                for zz in range(z, z + h):
                    self.v[(xx, yy, zz)] = c
        return self._dirty()

    def cyl(self, cx, cy, z, r, h, c):
        """An upright disc centred on (cx, cy)."""
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for yy in range(int(cy - r) - 1, int(cy + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r:
                    for zz in range(z, z + h):
                        self.v[(xx, yy, zz)] = c
        return self._dirty()

    def cyl_y(self, cx, cz, r, y, d, c):
        """A disc facing the viewer, centred on (cx, cz)."""
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for zz in range(int(cz - r) - 1, int(cz + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (zz + 0.5 - cz) ** 2 <= r * r and zz >= 0:
                    for yy in range(y, y + d):
                        self.v[(xx, yy, zz)] = c
        return self._dirty()

    def shape_y(self, x, z, y, d, inside, c):
        """Extrude any shape: inside(u, v) takes 0..1 across and 0..1 up the box (x, z) and says if it's solid."""
        return self

    def carve(self, x, y, z, w, d, h):
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                for zz in range(z, z + h):
                    self.v.pop((xx, yy, zz), None)
        return self._dirty()

    def _lookup(self):
        if self._index is None:
            front, top, side = {}, {}, {}
            for x, y, z in self.v:
                if y > front.get((x, z), -10**9):
                    front[(x, z)] = y
                if z > top.get((x, y), -10**9):
                    top[(x, y)] = z
                if x > side.get((y, z), -10**9):
                    side[(y, z)] = x
            self._index = (front, top, side)
        return self._index

    def front(self, x, z, w, h, c):
        front = self._lookup()[0]
        for xx in range(x, x + w):
            for zz in range(z, z + h):
                y = front.get((xx, zz))
                if y is not None:
                    self.v[(xx, y, zz)] = c
        return self

    def top(self, x, y, w, d, c):
        top = self._lookup()[1]
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                z = top.get((xx, yy))
                if z is not None:
                    self.v[(xx, yy, z)] = c
        return self

    def side(self, y, z, w, h, c):
        side = self._lookup()[2]
        for yy in range(y, y + w):
            for zz in range(z, z + h):
                x = side.get((yy, zz))
                if x is not None:
                    self.v[(x, yy, zz)] = c
        return self

    def front_disc(self, cx, cz, r, c):
        front = self._lookup()[0]
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for zz in range(int(cz - r) - 1, int(cz + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (zz + 0.5 - cz) ** 2 <= r * r and (xx, zz) in front:
                    self.v[(xx, front[(xx, zz)], zz)] = c
        return self

    def top_disc(self, cx, cy, r, c):
        top = self._lookup()[1]
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for yy in range(int(cy - r) - 1, int(cy + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r and (xx, yy) in top:
                    self.v[(xx, yy, top[(xx, yy)])] = c
        return self

    def render(self) -> QImage:
        cells = self.v
        surface = [p for p in cells if (p[0] + 1, p[1], p[2]) not in cells or (p[0], p[1] + 1, p[2]) not in cells or (p[0], p[1], p[2] + 1) not in cells]
        surface.sort(key=lambda p: (p[0] + p[1] + p[2], p[2]))  # far to near

        def proj(x, y, z):
            return 2 * (x - y), (x + y) - 2 * z

        left = min(2 * (x - y - 1) for x, y, _z in surface) - 3
        right = max(2 * (x + 1 - y) for x, y, _z in surface) + 3
        up = min((x + y) - 2 * (z + 1) for x, y, z in surface) - 3
        down = max((x + y + 2) - 2 * z for x, y, z in surface) + 3
        image = QImage(right - left, down - up, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        shades = {}

        def shade(key, factor):
            if (key, factor) not in shades:
                base = QColor(key)
                shades[(key, factor)] = QColor(min(255, int(base.red() * factor)), min(255, int(base.green() * factor)), min(255, int(base.blue() * factor)))
            return shades[(key, factor)]

        def face(points, color):
            painter.setBrush(color)
            painter.drawPolygon(QPolygon([QPoint(proj(*p)[0] - left, proj(*p)[1] - up) for p in points]))

        for x, y, z in surface:
            key = cells[(x, y, z)]
            if (x, y, z + 1) not in cells:
                face(((x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)), shade(key, TOP_LIGHT))
            if (x, y + 1, z) not in cells:
                face(((x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)), shade(key, FRONT_LIGHT))
            if (x + 1, y, z) not in cells:
                face(((x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)), shade(key, SIDE_LIGHT))
        painter.end()
        return image
