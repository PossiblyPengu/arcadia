"""A small isometric drawing tool, and the "era" step that turns a drawing into period-correct pixel art.

Build-time tooling (needs PySide6, Pillow and numpy). A Scene collects 3D shapes sized in real centimetres
(boxes, rounded boxes, discs, tilted boxes), projects them at the classic 2:1 isometric angle with each face
lit differently, and paints them smoothly at high resolution. `pixelate(image, era)` then reduces that to the
look of a console generation: how many pixels wide, how many colours, how hard the outline is.

Axes: x runs down and to the right on screen (a console's width), y down and to the left (its depth; the
front faces +y), z up. A body is the tuple (x, y, z, width, depth, height) returned by Scene.box().
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPolygonF

OUT = Path(__file__).resolve().parent.parent / "arcadia" / "assets" / "consoles"
SCALE = 16  # pixels per centimetre in the high-resolution drawing
Z_SCALE = 0.95  # how tall a centimetre of height looks next to a centimetre of width
LIGHT = (0.42, 0.91)  # where the light comes from (x, y), for curved sides
TOP, FRONT, SIDE = 1.10, 0.86, 0.66


def shade(color: str, factor: float) -> QColor:
    base = QColor(color)
    r, g, b = base.red(), base.green(), base.blue()
    if 0.299 * r + 0.587 * g + 0.114 * b < 46:  # black plastic reads as dark grey, so its edges still show on a dark screen
        r, g, b = r + 22, g + 22, b + 26
    return QColor(*(max(0, min(255, int(c * factor))) for c in (r, g, b)))


def project(x: float, y: float, z: float) -> tuple[float, float]:
    return (x - y) * 0.894 * SCALE, (x + y) * 0.447 * SCALE - z * Z_SCALE * SCALE


def circle(cx: float, cy: float, r: float, n: int = 40) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rrect(x: float, y: float, w: float, d: float, r: float, n: int = 7) -> list[tuple[float, float]]:
    """A rounded rectangle outline (counter-clockwise seen from above)."""
    r = max(0.001, min(r, w / 2, d / 2))
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + d - r, 0), (x + r, y + d - r, 90), (x + r, y + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


class Scene:
    def __init__(self):
        self.items: list[tuple[list[tuple[float, float]], QColor]] = []
        self.off = (0.0, 0.0, 0.0)  # everything drawn is moved by this (to place one console on another)

    # ----- low level -----

    def at(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.off = (x, y, z)

    def poly(self, pts3, color: QColor) -> None:
        ox, oy, oz = self.off
        self.items.append(([project(p[0] + ox, p[1] + oy, p[2] + oz) for p in pts3], color))

    def prism(self, outline, z0: float, z1: float, color: str, taper: float = 1.0, top: str | None = None) -> None:
        """Extrude an outline from z0 to z1 (optionally narrowing toward the top). Sides are lit by their direction."""
        cx = sum(p[0] for p in outline) / len(outline)
        cy = sum(p[1] for p in outline) / len(outline)
        upper = [(cx + (x - cx) * taper, cy + (y - cy) * taper) for x, y in outline]
        sides = []
        n = len(outline)
        for i in range(n):
            (x0, y0), (x1, y1) = outline[i], outline[(i + 1) % n]
            nx, ny = (y1 - y0), -(x1 - x0)  # outward normal for a counter-clockwise outline
            length = math.hypot(nx, ny) or 1.0
            nx, ny = nx / length, ny / length
            if nx + ny <= 0.02:  # faces away from the viewer
                continue
            brightness = 0.50 + 0.34 * (nx * LIGHT[0] + ny * LIGHT[1]) / math.hypot(*LIGHT) * 1.0
            (u0, v0), (u1, v1) = upper[i], upper[(i + 1) % n]
            sides.append(((x0 + x1) / 2 + (y0 + y1) / 2, [(x0, y0, z0), (x1, y1, z0), (u1, v1, z1), (u0, v0, z1)], brightness))
        for _depth, pts, brightness in sorted(sides, key=lambda s: s[0]):
            self.poly(pts, shade(color, brightness + 0.18))
        self.poly([(x, y, z1) for x, y in upper], shade(top or color, TOP))

    # ----- bodies -----

    def box(self, x, y, z, w, d, h, color: str, r: float = 0.0, taper: float = 1.0, top: str | None = None):
        outline = rrect(x, y, w, d, r) if r > 0 else [(x + w, y), (x + w, y + d), (x, y + d), (x, y)]
        self.prism(outline, z, z + h, color, taper, top)
        return (x, y, z, w, d, h)

    def disc(self, cx, cy, z, r, h, color: str, taper: float = 1.0, top: str | None = None):
        self.prism(circle(cx, cy, r), z, z + h, color, taper, top)
        return (cx - r, cy - r, z, 2 * r, 2 * r, h)

    def tilted(self, origin, ex, ey, ez, color: str):
        """A box whose three edge vectors you give (for a lid opened at an angle). Returns its origin and edges."""
        ox, oy, oz = origin
        corners = {}
        for a in (0, 1):
            for b in (0, 1):
                for c in (0, 1):
                    corners[(a, b, c)] = (ox + a * ex[0] + b * ey[0] + c * ez[0], oy + a * ex[1] + b * ey[1] + c * ez[1], oz + a * ex[2] + b * ey[2] + c * ez[2])
        faces = {
            "top": ([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], _cross(ex, ey)),
            "front": ([(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], _cross(ez, ex)),
            "side": ([(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], _cross(ey, ez)),
        }
        factors = {"top": TOP, "front": FRONT, "side": SIDE}
        for name, (idx, normal) in faces.items():
            self.poly([corners[i] for i in idx], shade(color, factors[name]))
        return origin, ex, ey, ez

    # ----- decals: paint on a face of a body, in centimetres from its left / bottom / back -----

    def d_front(self, b, u0, v0, u1, v1, color: str, lit: float = FRONT, lift: float = 0.02) -> None:
        x, y, z, w, d, h = b
        yy = y + d + lift
        self.poly([(x + u0, yy, z + v0), (x + u1, yy, z + v0), (x + u1, yy, z + v1), (x + u0, yy, z + v1)], shade(color, lit))

    def d_top(self, b, u0, v0, u1, v1, color: str, lit: float = TOP, lift: float = 0.02) -> None:
        x, y, z, w, d, h = b
        zz = z + h + lift
        self.poly([(x + u0, y + v0, zz), (x + u1, y + v0, zz), (x + u1, y + v1, zz), (x + u0, y + v1, zz)], shade(color, lit))

    def d_side(self, b, u0, v0, u1, v1, color: str, lit: float = SIDE, lift: float = 0.02) -> None:
        x, y, z, w, d, h = b
        xx = x + w + lift
        self.poly([(xx, y + u0, z + v0), (xx, y + u1, z + v0), (xx, y + u1, z + v1), (xx, y + u0, z + v1)], shade(color, lit))

    def c_front(self, b, u, v, r, color: str, lit: float = FRONT, n: int = 24) -> None:
        x, y, z, w, d, h = b
        yy = y + d + 0.02
        self.poly([(x + u + r * math.cos(t), yy, z + v + r * math.sin(t)) for t in (2 * math.pi * i / n for i in range(n))], shade(color, lit))

    def c_top(self, b, u, v, r, color: str, lit: float = TOP, n: int = 24) -> None:
        x, y, z, w, d, h = b
        zz = z + h + 0.02
        self.poly([(x + u + r * math.cos(t), y + v + r * math.sin(t), zz) for t in (2 * math.pi * i / n for i in range(n))], shade(color, lit))

    def c_side(self, b, u, v, r, color: str, lit: float = SIDE, n: int = 24) -> None:
        x, y, z, w, d, h = b
        xx = x + w + 0.02
        self.poly([(xx, y + u + r * math.cos(t), z + v + r * math.sin(t)) for t in (2 * math.pi * i / n for i in range(n))], shade(color, lit))

    # ----- the same decals placed by fraction of the face (0..1), which is how they're read off a photo -----

    def ff(self, b, x0, y0, x1, y1, color: str, lit: float = FRONT) -> None:
        """Front face: x0..x1 across from the left, y0..y1 up from the bottom."""
        w, h = b[3], b[5]
        self.d_front(b, x0 * w, y0 * h, x1 * w, y1 * h, color, lit)

    def ft(self, b, x0, y0, x1, y1, color: str, lit: float = TOP) -> None:
        """Top face: x across from the left, y from the back (0) to the front (1)."""
        w, d = b[3], b[4]
        self.d_top(b, x0 * w, y0 * d, x1 * w, y1 * d, color, lit)

    def fs(self, b, y0, z0, y1, z1, color: str, lit: float = SIDE) -> None:
        """Right-hand face: y from the back (0) to the front (1), z up from the bottom."""
        d, h = b[4], b[5]
        self.d_side(b, y0 * d, z0 * h, y1 * d, z1 * h, color, lit)

    def fcf(self, b, cx, cy, r, color: str, lit: float = FRONT) -> None:
        self.c_front(b, cx * b[3], cy * b[5], r, color, lit)

    def fct(self, b, cx, cy, r, color: str, lit: float = TOP) -> None:
        self.c_top(b, cx * b[3], cy * b[4], r, color, lit)

    def p_top(self, b, pts, color: str, lit: float = TOP) -> None:
        x, y, z, w, d, h = b
        self.poly([(x + u, y + v, z + h + 0.02) for u, v in pts], shade(color, lit))

    def d_on(self, face, u0, v0, u1, v1, color: str, lit: float = FRONT) -> None:
        """A rectangle on the front face of a tilted box (u along its x edge, v along its z edge)."""
        origin, ex, ey, ez = face
        ex_l, ez_l = _len(ex), _len(ez)
        pts = []
        for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
            pts.append(tuple(origin[i] + ey[i] + ex[i] * u / ex_l + ez[i] * v / ez_l + 0.0 for i in range(3)))
        self.poly(pts, shade(color, lit))

    def beam(self, p0, p1, width: float, color: str) -> None:
        """A thin straight bar between two points (a tripod leg, say), drawn as a flat strip facing the viewer."""
        dx, dy, dz = (p1[i] - p0[i] for i in range(3))
        nx, ny = -dy, dx
        length = math.hypot(nx, ny)
        if length < 1e-6:
            nx, ny, length = 1.0, -1.0, math.sqrt(2.0)
        nx, ny = nx / length * width / 2, ny / length * width / 2
        self.poly([(p0[0] - nx, p0[1] - ny, p0[2]), (p0[0] + nx, p0[1] + ny, p0[2]), (p1[0] + nx, p1[1] + ny, p1[2]), (p1[0] - nx, p1[1] - ny, p1[2])], shade(color, 0.8))

    # ----- painting -----

    def render(self, width: int | None = None, box: float = 0.95, smooth: bool = True) -> QImage:
        """Paint the scene. With a width, it is drawn straight at that many pixels across (or as tall as `box`
        times that, for a tall console), with hard pixel edges unless smooth is on. Without, at full size."""
        QGuiApplication.instance() or QGuiApplication([])
        xs = [p[0] for pts, _c in self.items for p in pts]
        ys = [p[1] for pts, _c in self.items for p in pts]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        f = 1.0 if width is None else min(width / span_x, width * box / span_y)
        pad = 2 if width else 6
        left, top = min(xs) * f - pad, min(ys) * f - pad
        image = QImage(int(span_x * f + 2 * pad) + 1, int(span_y * f + 2 * pad) + 1, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, smooth)
        painter.setPen(Qt.PenStyle.NoPen)
        for pts, color in self.items:
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([QPointF(x * f - left, y * f - top) for x, y in pts]))
        painter.end()
        return image


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(v):
    return math.sqrt(sum(c * c for c in v)) or 1.0


# ============================================================ eras

@dataclass(frozen=True)
class Era:
    label: str
    width: int  # the widest a picture is, in pixels
    colors: int  # the most colours it uses
    smooth: bool  # soft edges (a 3D chip's filtering) rather than hard pixels
    blur: float = 0.0  # extra softness, like a filtered texture


ERAS = {
    "8-bit": Era("8-bit", 56, 12, False),
    "16-bit": Era("16-bit", 80, 26, False),
    "32-bit": Era("32-bit", 100, 44, False),
    "64-bit": Era("64-bit", 116, 56, True, 0.6),
    "128-bit": Era("128-bit", 132, 80, True),
    "HD": Era("HD", 152, 120, True),
}
OUTLINE = (13, 14, 19, 255)


def pixelate(image: QImage | Image.Image, era: Era) -> Image.Image:
    """Limit the colours and add the outline. (The picture was already drawn at the era's own size.)"""
    if isinstance(image, QImage):
        image = to_pil(image)
    image = image.crop(image.getbbox())
    if era.blur:
        image = image.filter(ImageFilter.GaussianBlur(era.blur))
    alpha = np.array(image.split()[3]) >= 140
    rgb = ImageEnhance.Color(image.convert("RGB")).enhance(1.1)
    quant = np.array(rgb.quantize(colors=era.colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB"))
    h, w = alpha.shape
    out = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    out[1:-1, 1:-1, :3] = quant
    out[1:-1, 1:-1, 3] = np.where(alpha, 255, 0)
    solid = out[:, :, 3] > 0
    edge = np.zeros_like(solid)
    edge[1:, :] |= solid[:-1, :]
    edge[:-1, :] |= solid[1:, :]
    edge[:, 1:] |= solid[:, :-1]
    edge[:, :-1] |= solid[:, 1:]
    out[edge & ~solid] = OUTLINE
    return Image.fromarray(out)


def to_pil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (image.width(), image.height()), bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine(), 1)
