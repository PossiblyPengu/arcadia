"""2.5D pixel-art renders of each console, built in code.

Each console is a small voxel model (blocks, discs, a few painted details). A tiny renderer projects it
isometrically (2:1), shades the three visible faces (top brightest, the front lit, the side in shadow),
adds a dark outline, and draws it at low resolution; it is then scaled up with hard edges so the pixels
stay crisp. These are stylised originals: the shape and colours of each console, not official artwork.

Axes: x runs down and to the right on screen, y down and to the left (the console's front faces +y), z up.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPolygon, qRgba

W, H = 128, 96  # the box a console is fitted into when shown (only the 4:3 shape matters)
OUTLINE = QColor("#0d0e13")
TOP_LIGHT, FRONT_LIGHT, SIDE_LIGHT = 1.12, 0.84, 0.58

PALETTE = {
    "w": "#f4f4ee", "g": "#c9c9c3", "G": "#8f8f8a", "d": "#55555b", "D": "#2a2a30", "k": "#121217",
    "e": "#ddd6bf", "E": "#aaa28a",
    "r": "#d6322c", "R": "#8e1d1a", "o": "#f28a1a", "O": "#a85a0c", "y": "#f2c200", "Y": "#a98700",
    "n": "#3fae5a", "N": "#22763a", "t": "#2bb3a3", "T": "#16766b", "c": "#35b6e8", "C": "#1c7aa3",
    "b": "#3e7bd6", "B": "#24478f", "p": "#7b4fd6", "P": "#4b2f93", "m": "#e84393", "M": "#99245f",
    "L": "#9bbc0f", "l": "#4d6a12", "s": "#1f2a44", "S": "#2e4a78", "W": "#8a5a2b",
}


class Model:
    """A voxel model. Build it with box/cyl/..., paint details with front/top/side, then render()."""

    def __init__(self):
        self.v: dict[tuple[int, int, int], str] = {}

    # ----- building -----

    def box(self, x: int, y: int, z: int, w: int, d: int, h: int, c: str) -> "Model":
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                for zz in range(z, z + h):
                    self.v[(xx, yy, zz)] = c
        return self

    def cyl(self, cx: float, cy: float, z: int, r: float, h: int, c: str) -> "Model":
        """An upright disc (axis along z), centred on cell cx, cy."""
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for yy in range(int(cy - r) - 1, int(cy + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r:
                    for zz in range(z, z + h):
                        self.v[(xx, yy, zz)] = c
        return self

    def cyl_y(self, cx: float, cz: float, r: float, y: int, d: int, c: str) -> "Model":
        """A disc standing on its edge and facing the viewer (axis along y)."""
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            for zz in range(int(cz - r) - 1, int(cz + r) + 2):
                if (xx + 0.5 - cx) ** 2 + (zz + 0.5 - cz) ** 2 <= r * r and zz >= 0:
                    for yy in range(y, y + d):
                        self.v[(xx, yy, zz)] = c
        return self

    def carve(self, x: int, y: int, z: int, w: int, d: int, h: int) -> "Model":
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                for zz in range(z, z + h):
                    self.v.pop((xx, yy, zz), None)
        return self

    def art(self, x: int, z_top: int, y: int, d: int, rows: list[str], legend: dict[str, str]) -> "Model":
        """Extrude a picture (rows of characters, '.' empty) into a slab facing the viewer."""
        for dz, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch != ".":
                    for yy in range(y, y + d):
                        self.v[(x + dx, yy, z_top - dz)] = legend.get(ch, ch)
        return self

    # ----- painting the outermost layer of one face -----

    def _top_z(self) -> int:
        return max(z for _x, _y, z in self.v)

    def front(self, x: int, row: int, w: int, h: int, c: str) -> "Model":
        """Paint the front face (rows counted from the top of the model)."""
        top = self._top_z()
        for xx in range(x, x + w):
            for zz in range(top - row - h + 1, top - row + 1):
                ys = [yy for (px, yy, pz) in self.v if px == xx and pz == zz]
                if ys:
                    self.v[(xx, max(ys), zz)] = c
        return self

    def top(self, x: int, y: int, w: int, d: int, c: str) -> "Model":
        """Paint the top face (y counted from the back)."""
        for xx in range(x, x + w):
            for yy in range(y, y + d):
                zs = [zz for (px, py, zz) in self.v if px == xx and py == yy]
                if zs:
                    self.v[(xx, yy, max(zs))] = c
        return self

    def side(self, y: int, row: int, w: int, h: int, c: str) -> "Model":
        """Paint the right-hand face (y counted from the back, rows from the top)."""
        top = self._top_z()
        for yy in range(y, y + w):
            for zz in range(top - row - h + 1, top - row + 1):
                xs = [xx for (xx, py, pz) in self.v if py == yy and pz == zz]
                if xs:
                    self.v[(max(xs), yy, zz)] = c
        return self

    # ----- drawing -----

    def render(self) -> QImage:
        cells = self.v
        surface = [p for p in cells if (p[0] + 1, p[1], p[2]) not in cells or (p[0], p[1] + 1, p[2]) not in cells or (p[0], p[1], p[2] + 1) not in cells]
        surface.sort(key=lambda p: (p[0] + p[1] + p[2], p[2]))  # far to near

        def proj(x: int, y: int, z: int) -> QPoint:
            return QPoint(2 * (x - y), (x + y) - 2 * z)

        left = min(2 * (x - y - 1) for x, y, _z in surface) - 2
        right = max(2 * (x + 1 - y) for x, y, _z in surface) + 2
        up = min((x + y) - 2 * (z + 1) for x, y, z in surface)
        down = max((x + y + 2) - 2 * z for x, y, z in surface)
        width, height = right - left, down - up
        ox = -left
        oy = -up

        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)

        def shade(key: str, factor: float) -> QColor:
            base = QColor(PALETTE[key])
            return QColor(min(255, int(base.red() * factor)), min(255, int(base.green() * factor)), min(255, int(base.blue() * factor)))

        def face(points: list[tuple[int, int, int]], color: QColor) -> None:
            painter.setBrush(color)
            painter.drawPolygon(QPolygon([proj(*p) + QPoint(ox, oy) for p in points]))

        for x, y, z in surface:
            key = cells[(x, y, z)]
            face([(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)], shade(key, TOP_LIGHT))
            face([(x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)], shade(key, FRONT_LIGHT))
            face([(x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)], shade(key, SIDE_LIGHT))
        painter.end()

        outline = qRgba(OUTLINE.red(), OUTLINE.green(), OUTLINE.blue(), 255)
        iw, ih = image.width(), image.height()
        edge = [
            (px, py)
            for py in range(ih)
            for px in range(iw)
            if image.pixelColor(px, py).alpha() == 0
            and any(0 <= px + dx < iw and 0 <= py + dy < ih and image.pixelColor(px + dx, py + dy).alpha() > 0 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        ]
        for px, py in edge:
            image.setPixel(px, py, outline)
        return image


# ----- the consoles -----
# Each builds a Model whose front (the +y face) faces the viewer.

def nes() -> Model:
    m = Model().box(0, 0, 0, 30, 16, 8, "g").box(0, 0, 8, 30, 16, 1, "w")
    m.top(4, 3, 22, 8, "d").top(5, 4, 20, 6, "D")
    m.front(4, 1, 22, 4, "D").front(4, 1, 22, 1, "d").front(4, 6, 12, 1, "r").front(21, 6, 2, 1, "r").front(24, 6, 2, 1, "r")
    return m


def snes() -> Model:
    m = Model().box(0, 0, 0, 30, 18, 8, "g").box(9, 3, 8, 12, 12, 2, "G").top(11, 5, 8, 3, "D")
    m.front(3, 3, 3, 2, "p").front(7, 3, 3, 2, "p").front(22, 3, 6, 2, "P").front(0, 6, 30, 2, "G")
    return m


def n64() -> Model:
    m = Model().box(3, 1, 0, 24, 16, 8, "d").box(0, 5, 0, 4, 10, 6, "d").box(26, 5, 0, 4, 10, 6, "d")
    m.box(9, 3, 8, 12, 9, 6, "G").front(10, 0, 10, 3, "r").top(10, 4, 10, 4, "d")
    for x, c in ((7, "b"), (12, "n"), (17, "y"), (22, "r")):
        m.front(x, 5, 3, 2, c)
    return m


def gc() -> Model:
    m = Model().box(0, 0, 0, 20, 20, 16, "p").top(0, 0, 20, 2, "P")
    m.box(6, 7, 16, 8, 5, 3, "P").carve(8, 8, 17, 4, 3, 2)
    m.cyl(10, 11, 16, 5, 1, "P").cyl(10, 11, 17, 3, 1, "g").cyl(10, 11, 18, 1.5, 1, "D")
    m.front(3, 10, 3, 3, "D").front(7, 10, 3, 3, "D").front(11, 10, 3, 3, "D").front(15, 10, 2, 3, "D")
    return m


def wii() -> Model:
    m = Model().box(0, 0, 0, 14, 4, 22, "w").front(2, 5, 10, 1, "D").front(2, 6, 10, 1, "G")
    return m.front(3, 15, 2, 1, "c").front(9, 15, 2, 1, "c").front(0, 11, 14, 1, "g")


def wiiu() -> Model:
    m = Model().box(0, 0, 0, 30, 18, 6, "w").top(2, 2, 26, 14, "g").front(4, 1, 22, 1, "D").front(4, 2, 22, 1, "G")
    return m.front(24, 4, 2, 1, "c")


def switch() -> Model:
    m = Model().box(4, 0, 0, 14, 3, 11, "D").box(0, 0, 0, 4, 3, 11, "c").box(18, 0, 0, 4, 3, 11, "r")
    m.front(5, 1, 12, 9, "S").front(6, 2, 10, 7, "s").front(1, 3, 2, 2, "D").front(19, 6, 2, 2, "D")
    m.front(1, 0, 2, 1, "C").front(19, 0, 2, 1, "R")
    return m


def _handheld_v(body: str, screen: str, btn: str, shade: str) -> Model:
    m = Model().box(0, 0, 0, 12, 3, 20, body)
    m.front(1, 1, 10, 9, "d").front(2, 2, 8, 7, screen)
    m.front(3, 12, 1, 3, "D").front(2, 13, 3, 1, "D")
    m.front(7, 13, 2, 2, btn).front(10, 12, 2, 2, btn)
    m.front(3, 17, 2, 1, "D").front(6, 17, 2, 1, "D")
    m.front(8, 17, 4, 1, shade).front(8, 18, 4, 1, shade)
    return m


def gb() -> Model:
    return _handheld_v("g", "L", "m", "G")


def gbc() -> Model:
    return _handheld_v("t", "L", "m", "T")


def wonderswan() -> Model:
    return _handheld_v("w", "L", "b", "g")


def _handheld_h(x: int, z: int, body: str, screen: str, btn: str, bezel: str = "D") -> Model:
    m = Model().box(0, 0, 0, x, 3, z, body)
    sw = x - 14
    m.front(7, 1, sw, z - 4, bezel).front(8, 2, sw - 2, z - 6, screen)
    mid = z // 2
    m.front(2, mid - 1, 4, 1, "D").front(3, mid - 2, 2, 3, "D")
    m.front(x - 5, mid - 2, 2, 2, btn).front(x - 8, mid, 2, 2, btn)
    return m


def gba() -> Model:
    m = _handheld_h(28, 13, "p", "L", "w")
    return m.front(0, 0, 4, 1, "P").front(24, 0, 4, 1, "P")


def gamegear() -> Model:
    return _handheld_h(28, 14, "D", "c", "r", "k")


def psp() -> Model:
    m = _handheld_h(30, 13, "D", "c", "m", "S")
    return m.front(26, 3, 2, 2, "n")


def lynx() -> Model:
    return _handheld_h(30, 14, "D", "L", "o", "k")


def ngp() -> Model:
    return _handheld_h(24, 14, "S", "c", "r", "k")


def _clamshell(x: int, body: str, shade: str, screen: str) -> Model:
    m = Model().box(0, 6, 0, x, 12, 2, body).box(0, 4, 2, x, 2, 14, body).box(0, 5, 0, x, 1, 2, shade)
    sw = x - 8
    m.front(4, 1, sw, 8, "D").front(5, 2, sw - 2, 6, screen)  # the upper screen
    m.top(4, 8, sw, 8, "D").top(5, 9, sw - 2, 6, "s")  # the lower screen
    m.top(1, 11, 2, 2, "D").top(x - 3, 10, 2, 2, "m")
    return m


def nds() -> Model:
    return _clamshell(22, "g", "G", "S")


def n3ds() -> Model:
    return _clamshell(28, "r", "R", "S")


def genesis() -> Model:
    m = Model().box(0, 0, 0, 30, 18, 7, "D").box(0, 0, 7, 30, 18, 1, "d")
    m.cyl(14, 9, 8, 6, 1, "d").cyl(14, 9, 9, 4, 1, "D").top(5, 14, 4, 2, "G")
    m.front(2, 2, 8, 1, "w").front(2, 4, 5, 1, "r").front(22, 3, 5, 2, "G")
    return m


def sms() -> Model:
    m = Model().box(0, 0, 0, 30, 16, 7, "D").top(0, 0, 30, 3, "r").top(5, 5, 20, 8, "d").top(6, 6, 18, 6, "k")
    return m.front(2, 4, 3, 1, "r")


def segacd() -> Model:
    m = Model().box(0, 4, 0, 36, 18, 5, "d").front(5, 1, 26, 2, "k").front(5, 1, 26, 1, "D")
    m.box(4, 6, 5, 28, 14, 7, "D").box(4, 6, 12, 28, 14, 1, "d").cyl(18, 13, 13, 5, 1, "d").top(10, 8, 4, 2, "k")
    return m.front(5, 3, 8, 1, "w")


def saturn() -> Model:
    m = Model().box(0, 0, 0, 30, 20, 6, "d").box(0, 0, 6, 30, 20, 1, "G")
    m.cyl(15, 10, 7, 7, 1, "D").cyl(15, 10, 8, 3, 1, "G").front(4, 2, 2, 1, "r").front(4, 4, 2, 1, "n").front(24, 3, 4, 1, "r")
    return m


def dreamcast() -> Model:
    m = Model().box(0, 0, 0, 22, 22, 8, "w").box(0, 0, 8, 22, 22, 1, "g")
    m.cyl(11, 11, 9, 8, 1, "g").cyl(11, 11, 10, 6.5, 1, "w").cyl(11, 11, 11, 3, 1, "o").cyl(11, 11, 12, 1.5, 1, "w")
    return m.front(2, 3, 18, 1, "g").front(2, 5, 18, 1, "g")


def psx() -> Model:
    m = Model().box(0, 0, 0, 26, 22, 7, "g").box(0, 0, 7, 26, 22, 1, "w")
    m.cyl(13, 10, 8, 8, 3, "G").cyl(13, 10, 11, 6, 1, "g").cyl(13, 10, 12, 2.5, 1, "G")
    m.front(3, 3, 3, 1, "d").front(20, 3, 3, 1, "d").front(11, 5, 4, 2, "d")
    return m


def ps2() -> Model:
    m = Model().box(0, 0, 0, 18, 8, 28, "D").front(2, 3, 14, 1, "b").front(2, 5, 14, 1, "d").front(4, 22, 10, 1, "d").front(7, 24, 4, 1, "b")
    return m.side(0, 2, 8, 24, "k")


def ps3() -> Model:
    m = Model().box(0, 0, 0, 30, 20, 8, "D").box(0, 0, 8, 30, 20, 1, "d")
    m.top(0, 0, 6, 20, "G").front(0, 0, 6, 9, "G").front(9, 5, 18, 1, "G").front(9, 6, 18, 2, "k")
    return m


def xbox() -> Model:
    m = Model().box(0, 0, 0, 26, 22, 9, "D").box(0, 0, 9, 26, 22, 1, "d")
    m.cyl(13, 11, 10, 7, 1, "N").cyl(13, 11, 11, 5.5, 1, "n").cyl(13, 11, 12, 3.5, 1, "N").cyl(13, 11, 13, 2, 1, "n")
    return m.front(3, 3, 2, 2, "n").front(21, 3, 2, 2, "G")


def pcengine() -> Model:
    m = Model().box(0, 0, 0, 16, 16, 6, "w").box(0, 0, 6, 16, 16, 1, "g").top(2, 2, 12, 5, "D").top(2, 9, 12, 1, "r").top(2, 11, 5, 1, "b")
    return m.front(3, 2, 10, 1, "D")


def neogeo() -> Model:
    m = Model().box(0, 0, 0, 30, 20, 8, "D").box(0, 0, 8, 30, 20, 1, "d")
    m.front(0, 4, 30, 1, "y").top(3, 3, 24, 8, "k")
    for x, c in ((4, "r"), (9, "b"), (14, "y"), (19, "n")):
        m.front(x, 6, 3, 2, c)
    return m


def arcade() -> Model:
    m = Model().box(0, 0, 0, 14, 12, 10, "B").box(0, 0, 10, 14, 8, 12, "B").box(0, 6, 10, 14, 6, 1, "d")
    m.front(1, 0, 12, 3, "y").front(1, 1, 12, 1, "o").front(2, 4, 10, 8, "D").front(3, 5, 8, 6, "N").front(4, 6, 6, 4, "n")
    m.box(4, 8, 11, 1, 1, 3, "G").box(3, 7, 14, 3, 3, 1, "r")
    m.top(8, 8, 2, 2, "y").top(11, 8, 2, 2, "c")
    return m


def atari2600() -> Model:
    m = Model().box(0, 0, 0, 28, 18, 8, "D").box(0, 0, 8, 28, 18, 1, "d")
    m.front(0, 3, 28, 6, "W").front(0, 3, 28, 1, "O").top(3, 3, 3, 2, "g").top(8, 3, 3, 2, "g").top(21, 3, 4, 2, "g")
    for y in (7, 9, 11, 13):
        m.top(3, y, 22, 1, "k")
    return m


def atari7800() -> Model:
    m = Model().box(0, 0, 0, 28, 18, 7, "D").box(0, 0, 7, 28, 18, 1, "d")
    for y in (3, 6, 9, 12):
        m.top(3, y, 22, 1, "k")
    return m.front(2, 3, 3, 1, "r").front(22, 3, 4, 1, "G")


def virtualboy() -> Model:
    m = Model().box(3, 2, 0, 20, 8, 2, "d").box(11, 4, 2, 4, 3, 6, "d").box(0, 0, 8, 26, 10, 10, "D").box(0, 0, 18, 26, 10, 1, "d")
    m.front(4, 3, 8, 5, "r").front(14, 3, 8, 5, "r").front(5, 4, 6, 3, "R").front(15, 4, 6, 3, "R").front(11, 3, 4, 3, "d")
    return m


def msx() -> Model:
    m = Model().box(0, 0, 0, 32, 16, 5, "d").box(0, 0, 5, 32, 16, 1, "G")
    for y in (4, 7, 10):
        for x in range(3, 25, 2):
            m.top(x, y, 1, 2, "g")
    return m.top(26, 4, 4, 9, "D").front(3, 2, 10, 1, "D")


def amiga() -> Model:
    m = Model().box(0, 0, 0, 32, 18, 6, "e").box(0, 0, 6, 32, 18, 1, "w").top(2, 4, 20, 11, "E").top(24, 4, 6, 11, "g")
    for y in (6, 9, 12):
        m.top(3, y, 18, 1, "d")
    return m.front(22, 3, 7, 1, "D").front(3, 3, 3, 1, "r").front(7, 3, 3, 1, "n")


def recent() -> Model:
    m = Model().cyl_y(12, 12, 11.5, 0, 3, "r").cyl_y(12, 12, 10, 0, 3, "w")
    m.front(12, 5, 1, 7, "D").front(12, 11, 5, 1, "D").front(11, 10, 3, 3, "r")
    return m


def favorites() -> Model:
    heart = [
        "..xxxx....xxxx..",
        ".xxxxxx..xxxxxx.",
        "xxxxxxxxxxxxxxxx",
        "xxxxxxxxxxxxxxxx",
        "xxxxxxxxxxxxxxxx",
        ".xxxxxxxxxxxxxx.",
        "..xxxxxxxxxxxx..",
        "...xxxxxxxxxx...",
        "....xxxxxxxx....",
        ".....xxxxxx.....",
        "......xxxx......",
        ".......xx.......",
    ]
    m = Model().art(0, 14, 0, 4, heart, {"x": "m"})
    return m.front(2, 1, 3, 2, "w").front(1, 3, 2, 1, "w")


def all_games() -> Model:
    m = Model()
    for x, y, body, label in ((0, 12, "d", "b"), (8, 6, "G", "r"), (16, 0, "g", "y")):
        m.box(x, y, 0, 10, 4, 13, body)
        for xx in range(x + 2, x + 8):
            for zz in range(6, 11):
                m.v[(xx, y + 3, zz)] = label
    return m


def cartridge() -> Model:
    """For consoles Arcadia has no model for (ones you add yourself)."""
    m = Model().box(0, 0, 0, 14, 4, 18, "G")
    for xx in range(2, 12):
        for zz in range(8, 16):
            m.v[(xx, 3, zz)] = "b"
    for xx in range(4, 10):
        for zz in range(10, 14):
            m.v[(xx, 3, zz)] = "c"
    for xx in range(2, 12):
        for zz in range(2, 5):
            m.v[(xx, 3, zz)] = "D"
    return m


SPRITES: dict[str, Callable[[], Model]] = {
    "nes": nes, "snes": snes, "n64": n64, "gc": gc, "wii": wii, "wiiu": wiiu, "switch": switch,
    "gb": gb, "gbc": gbc, "gba": gba, "nds": nds, "n3ds": n3ds,
    "genesis": genesis, "sms": sms, "gamegear": gamegear, "segacd": segacd, "saturn": saturn, "dreamcast": dreamcast,
    "psx": psx, "ps2": ps2, "ps3": ps3, "psp": psp, "xbox": xbox,
    "pcengine": pcengine, "neogeo": neogeo, "arcade": arcade,
    "atari2600": atari2600, "atari7800": atari7800, "lynx": lynx, "wonderswan": wonderswan, "ngp": ngp,
    "virtualboy": virtualboy, "msx": msx, "amiga": amiga,
    "__recent__": recent, "__favorites__": favorites, "__all__": all_games,
}


# Your own artwork: a picture named after the console (nes.png, snes.png, psx.webp ...) in this folder is
# shown instead of the built-in render. Transparent backgrounds are best; any empty border is trimmed.
ART_TYPES = (".png", ".webp", ".jpg", ".jpeg")
_art_dir: Path | None = None


def _signature(folder: Path | None) -> tuple:
    """Which of your pictures exist and when they last changed, so nothing is redrawn unless that changes."""
    if folder is None or not folder.is_dir():
        return ()
    try:
        return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in folder.iterdir() if p.suffix.lower() in ART_TYPES))
    except OSError:
        return ()


_art_sig: tuple = ()


def set_art_dir(folder: Path | None) -> None:
    """Where to look for your own console pictures (None = just use the built-in renders). Cheap to call
    again: the caches are only reset when the folder or the pictures in it have changed."""
    global _art_dir, _art_sig
    signature = _signature(folder)
    if folder == _art_dir and signature == _art_sig:
        return
    _art_dir, _art_sig = folder, signature
    for cached in (sprite_image, scaled, glow, _load_custom_cached, _load_bundled):
        cached.cache_clear()


def art_dir() -> Path | None:
    return _art_dir


def custom_file(view_id: str) -> Path | None:
    if _art_dir is None or "/" in view_id or "\\" in view_id or view_id.startswith("."):
        return None
    for ext in ART_TYPES:
        path = _art_dir / f"{view_id}{ext}"
        if path.is_file():
            return path
    return None


def _load_custom(path: Path) -> QImage | None:
    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    # trim empty (transparent) borders so every picture is fitted by what's actually drawn
    xs = [x for x in range(image.width()) if any(image.pixelColor(x, y).alpha() > 8 for y in range(0, image.height(), 2))]
    ys = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() > 8 for x in range(0, image.width(), 2))]
    if not xs or not ys:
        return None
    return image.copy(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def is_custom(view_id: str) -> bool:
    return custom_file(view_id) is not None and _load_custom_cached(view_id) is not None


@lru_cache(maxsize=None)
def _load_custom_cached(view_id: str) -> QImage | None:
    path = custom_file(view_id)
    return _load_custom(path) if path else None


# The pictures that ship with Arcadia: pixel art made from photographs of the real consoles (see
# tools/make_console_art.py and arcadia/assets/consoles/ATTRIBUTION.md). A console without one falls
# back to the drawn 3D render above.
ASSETS = Path(__file__).resolve().parent / "assets" / "consoles"


def bundled_file(view_id: str) -> Path | None:
    if "/" in view_id or "\\" in view_id or view_id.startswith("."):
        return None
    path = ASSETS / f"{view_id}.png"
    return path if path.is_file() else None


@lru_cache(maxsize=None)
def _load_bundled(view_id: str) -> QImage | None:
    path = bundled_file(view_id)
    if path is None:
        return None
    image = QImage(str(path))
    return None if image.isNull() else image.convertToFormat(QImage.Format.Format_ARGB32)


def is_bundled(view_id: str) -> bool:
    return not is_custom(view_id) and _load_bundled(view_id) is not None


@lru_cache(maxsize=None)
def sprite_image(view_id: str) -> QImage:
    custom = _load_custom_cached(view_id)
    if custom is not None:
        return custom
    bundled = _load_bundled(view_id)
    if bundled is not None:
        return bundled
    return SPRITES.get(view_id, cartridge)().render()


# ----- drawing: hard-edged scaling and the glow -----

@lru_cache(maxsize=512)
def scaled(view_id: str, width: int) -> QPixmap:
    """The console fitted into a width x (3/4 width) box, standing on its floor, with crisp pixels (no
    smoothing). Every console is fitted the same way, so a handheld fills the box as much as a big console."""
    box_w, box_h = width, round(width * H / W)
    src = sprite_image(view_id)
    fit = min(box_w * 0.96 / src.width(), box_h * 0.94 / src.height())
    tw, th = max(1, round(src.width() * fit)), max(1, round(src.height() * fit))
    if is_custom(view_id):  # your own pictures are scaled smoothly
        big = src.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    elif is_bundled(view_id):
        # pixel art: enlarge by whole pixels first so every pixel stays a clean square, then ease down to the exact size
        k = max(1, -(-tw // src.width()) + 1)
        blocky = src.scaled(QSize(src.width() * k, src.height() * k), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        big = blocky.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    else:
        big = src.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    out = QImage(box_w, box_h, QImage.Format.Format_ARGB32)
    out.fill(0)
    painter = QPainter(out)
    painter.drawImage((box_w - tw) // 2, box_h - th - round(box_h * 0.03), big)
    painter.end()
    return QPixmap.fromImage(out)


@lru_cache(maxsize=256)
def glow(view_id: str, width: int, color: str) -> QPixmap:
    """A soft halo in `color` the shape of the sprite, a little larger than it. (width is rounded so the
    cache stays small while the sprite animates in size.)"""
    pad = glow_padding(width)
    base = scaled(view_id, width)
    sil = QImage(base.width() + 2 * pad, base.height() + 2 * pad, QImage.Format.Format_ARGB32_Premultiplied)
    sil.fill(0)
    painter = QPainter(sil)
    painter.drawPixmap(pad, pad, base)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(sil.rect(), QColor(color))
    painter.end()
    # blur by shrinking and growing it again, smoothly; twice for a wider, softer spread
    small = sil.scaled(max(1, sil.width() // 6), max(1, sil.height() // 6), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    halo = small.scaled(sil.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(sil.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    painter = QPainter(out)
    painter.drawImage(0, 0, halo)
    painter.setOpacity(0.7)
    painter.drawImage(0, 0, halo)
    painter.end()
    return QPixmap.fromImage(out)


def glow_padding(width: int) -> int:
    return max(20, width // 3)
