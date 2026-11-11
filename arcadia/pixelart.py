"""Pixel art for each console, drawn in code.

These are small, original, stylised sprites (32 x 22 pixels, shown scaled up with hard edges): the
silhouette and colours of each console, not official artwork. A sprite is a handful of rectangles and
discs on a tiny canvas; a one-pixel dark outline is added automatically.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, qRgba

W, H = 32, 22
OUTLINE = QColor("#0d0e13")

PALETTE = {
    "w": "#f4f4ee", "g": "#c9c9c3", "G": "#8f8f8a", "d": "#55555b", "D": "#25252b", "k": "#101015",
    "e": "#ddd6bf", "E": "#aaa28a",
    "r": "#d6322c", "R": "#8e1d1a", "o": "#f28a1a", "O": "#a85a0c", "y": "#f2c200", "Y": "#a98700",
    "n": "#3fae5a", "N": "#22763a", "t": "#2bb3a3", "T": "#16766b", "c": "#35b6e8", "C": "#1c7aa3",
    "b": "#3e7bd6", "B": "#24478f", "p": "#7b4fd6", "P": "#4b2f93", "m": "#e84393", "M": "#99245f",
    "L": "#9bbc0f", "l": "#4d6a12", "s": "#1f2a44", "S": "#2e4a78", "W": "#6b4423",
}


class Canvas:
    def __init__(self):
        self.pixels: dict[tuple[int, int], str] = {}

    def rect(self, x: int, y: int, w: int, h: int, color: str) -> "Canvas":
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < W and 0 <= yy < H:
                    self.pixels[(xx, yy)] = color
        return self

    def px(self, x: int, y: int, color: str) -> "Canvas":
        return self.rect(x, y, 1, 1, color)

    def disc(self, cx: float, cy: float, r: float, color: str) -> "Canvas":
        for yy in range(H):
            for xx in range(W):
                if (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r:
                    self.pixels[(xx, yy)] = color
        return self

    def art(self, x: int, y: int, rows: list[str], legend: dict[str, str] | None = None) -> "Canvas":
        """Draw rows of characters ('.' is empty); characters are palette keys."""
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch != ".":
                    self.px(x + dx, y + dy, (legend or {}).get(ch, ch))
        return self

    def image(self) -> QImage:
        image = QImage(W, H, QImage.Format.Format_ARGB32)
        image.fill(0)
        for (x, y), key in self.pixels.items():
            image.setPixelColor(x, y, QColor(PALETTE[key]))
        # one-pixel outline around the shape
        outline = qRgba(OUTLINE.red(), OUTLINE.green(), OUTLINE.blue(), 255)
        edge = [
            (x, y)
            for y in range(H)
            for x in range(W)
            if (x, y) not in self.pixels
            and any((x + dx, y + dy) in self.pixels for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        ]
        for x, y in edge:
            image.setPixel(x, y, outline)
        return image


def _handheld_v(c: Canvas, body: str, shade: str, screen: str, btn: str) -> Canvas:
    """A tall handheld: Game Boy shape."""
    c.rect(8, 1, 16, 20, body).rect(8, 19, 16, 2, shade).rect(23, 1, 1, 20, shade)
    c.rect(10, 3, 12, 9, "d").rect(12, 5, 8, 5, screen).rect(11, 12, 10, 1, "D")
    c.rect(10, 15, 4, 1, "D").rect(11, 14, 2, 3, "D")  # d-pad
    c.rect(17, 16, 2, 2, btn).rect(20, 14, 2, 2, btn)
    c.rect(11, 19, 4, 1, "D").rect(16, 19, 4, 1, "D")  # start / select
    return c


def _handheld_h(c: Canvas, body: str, shade: str, screen: str, btn: str) -> Canvas:
    """A wide handheld: GBA / Game Gear / PSP shape."""
    c.rect(2, 5, 28, 13, body).rect(2, 16, 28, 2, shade)
    c.rect(9, 6, 14, 10, "D").rect(10, 7, 12, 8, screen)
    c.rect(4, 10, 4, 1, "D").rect(5, 9, 2, 3, "D")  # d-pad
    c.rect(25, 9, 2, 2, btn).rect(23, 11, 2, 2, btn)
    return c


def _clamshell(c: Canvas, body: str, shade: str, top: int = 16) -> Canvas:
    """A folding two-screen handheld: DS / 3DS."""
    left = (W - top) // 2
    c.rect(left - 3, 1, top + 6, 20, body).rect(left - 3, 19, top + 6, 2, shade)
    c.rect(left, 3, top, 7, "D").rect(left + 1, 4, top - 2, 5, "S")
    c.rect(left - 3, 11, top + 6, 1, shade)  # hinge
    c.rect(left, 13, top, 6, "D").rect(left + 1, 14, top - 2, 4, "s")
    c.rect(left - 2, 15, 1, 3, "D").rect(left + top + 1, 15, 1, 3, "D")
    return c


def nes() -> Canvas:
    c = Canvas().rect(2, 6, 28, 12, "g").rect(2, 6, 28, 2, "w").rect(2, 16, 28, 2, "G")
    c.rect(5, 9, 22, 4, "D").rect(5, 9, 22, 1, "d").rect(5, 14, 10, 1, "r")
    return c.rect(21, 14, 2, 1, "r").rect(24, 14, 2, 1, "r")


def snes() -> Canvas:
    c = Canvas().rect(3, 7, 26, 11, "g").rect(3, 7, 26, 2, "w").rect(3, 16, 26, 2, "G")
    c.rect(10, 9, 12, 5, "G").rect(12, 11, 8, 2, "D")
    return c.rect(5, 10, 2, 2, "p").rect(8, 10, 2, 2, "p").rect(23, 10, 5, 2, "P")


def n64() -> Canvas:
    c = Canvas().rect(4, 9, 24, 9, "d").rect(4, 9, 24, 2, "G").rect(2, 12, 4, 6, "d").rect(26, 12, 4, 6, "d")
    c.rect(11, 2, 10, 8, "G").rect(13, 3, 6, 4, "r").rect(11, 8, 10, 1, "d")
    for x, color in ((8, "b"), (12, "n"), (16, "y"), (20, "r")):
        c.rect(x, 15, 3, 2, color)
    return c


def gc() -> Canvas:
    c = Canvas().rect(5, 5, 22, 14, "p").rect(5, 5, 22, 2, "w").rect(5, 17, 22, 2, "P").rect(25, 5, 2, 14, "P")
    c.rect(12, 2, 8, 3, "P").rect(14, 3, 4, 1, "D").disc(16, 12, 4.5, "P").disc(16, 12, 2, "g")
    return c.rect(15, 11, 2, 2, "D")


def wii() -> Canvas:
    c = Canvas().rect(11, 2, 10, 18, "w").rect(19, 2, 2, 18, "g").rect(12, 6, 8, 1, "D").rect(12, 7, 8, 1, "G")
    return c.rect(13, 16, 2, 1, "c").rect(17, 16, 2, 1, "c").rect(12, 11, 8, 1, "g")


def wiiu() -> Canvas:
    c = Canvas().rect(3, 8, 26, 10, "w").rect(3, 16, 26, 2, "g").rect(6, 10, 20, 1, "D").rect(6, 11, 20, 1, "G")
    return c.rect(24, 14, 2, 1, "c").rect(6, 14, 8, 1, "g")


def switch() -> Canvas:
    c = Canvas().rect(8, 4, 16, 14, "D").rect(9, 5, 14, 11, "S").rect(10, 6, 12, 9, "s")
    c.rect(2, 4, 6, 14, "c").rect(24, 4, 6, 14, "r").rect(3, 7, 2, 2, "D").rect(26, 12, 2, 2, "D")
    return c.rect(3, 4, 4, 1, "C").rect(25, 4, 4, 1, "R").rect(13, 19, 6, 1, "d")


def gb() -> Canvas:
    return _handheld_v(Canvas(), "g", "G", "L", "m")


def gbc() -> Canvas:
    return _handheld_v(Canvas(), "t", "T", "L", "m")


def gba() -> Canvas:
    c = _handheld_h(Canvas(), "p", "P", "L", "w")
    return c.rect(3, 4, 4, 1, "P").rect(25, 4, 4, 1, "P")


def nds() -> Canvas:
    return _clamshell(Canvas(), "g", "G", 14)


def n3ds() -> Canvas:
    c = _clamshell(Canvas(), "r", "R", 18)
    return c.rect(27, 5, 1, 4, "w")


def genesis() -> Canvas:
    c = Canvas().rect(3, 7, 26, 11, "D").rect(3, 7, 26, 2, "d").rect(9, 9, 14, 5, "d").rect(11, 11, 10, 2, "k")
    return c.rect(5, 15, 6, 1, "w").rect(5, 16, 6, 1, "r").rect(22, 15, 4, 2, "G")


def sms() -> Canvas:
    c = Canvas().rect(3, 8, 26, 10, "D").rect(3, 8, 26, 2, "r").rect(6, 11, 20, 4, "d").rect(8, 12, 16, 2, "k")
    return c.rect(5, 16, 3, 1, "r")


def gamegear() -> Canvas:
    c = _handheld_h(Canvas(), "D", "k", "t", "r")
    return c.rect(10, 7, 12, 8, "T").rect(11, 8, 10, 6, "c").rect(3, 5, 2, 2, "d")


def segacd() -> Canvas:
    c = Canvas().rect(2, 11, 28, 9, "D").rect(2, 11, 28, 1, "d").rect(6, 13, 20, 3, "d").rect(8, 14, 16, 1, "k")
    return c.rect(8, 3, 16, 8, "d").rect(10, 5, 12, 4, "D").rect(10, 5, 12, 1, "G").rect(5, 17, 4, 1, "r")


def saturn() -> Canvas:
    c = Canvas().rect(3, 8, 26, 11, "d").rect(3, 8, 26, 2, "G").rect(3, 17, 26, 2, "D")
    c.disc(16, 13, 5, "D").disc(16, 13, 2.5, "G").rect(5, 11, 2, 1, "r").rect(5, 13, 2, 1, "n")
    return c.rect(25, 11, 2, 1, "r")


def dreamcast() -> Canvas:
    c = Canvas().rect(4, 5, 24, 15, "w").rect(4, 18, 24, 2, "g").rect(26, 5, 2, 15, "g")
    c.disc(16, 12, 6.5, "g").disc(16, 12, 5, "w").disc(16, 12, 2.5, "o")
    return c.rect(6, 7, 3, 1, "D").rect(23, 7, 3, 1, "D")


def psx() -> Canvas:
    c = Canvas().rect(3, 9, 26, 10, "g").rect(3, 9, 26, 1, "w").rect(3, 17, 26, 2, "G")
    c.rect(8, 5, 16, 5, "G").rect(10, 4, 12, 1, "G").rect(10, 6, 12, 3, "g")
    return c.rect(5, 12, 2, 2, "d").rect(23, 12, 2, 2, "d").rect(15, 13, 2, 2, "d")


def ps2() -> Canvas:
    c = Canvas().rect(10, 1, 12, 20, "D").rect(10, 1, 2, 20, "d").rect(20, 1, 2, 20, "k")
    return c.rect(13, 4, 6, 1, "b").rect(13, 7, 6, 1, "d").rect(13, 16, 6, 1, "d").rect(15, 18, 2, 1, "b")


def ps3() -> Canvas:
    c = Canvas().rect(3, 5, 26, 14, "D").rect(3, 5, 26, 2, "d").rect(3, 5, 4, 14, "G").rect(3, 5, 4, 2, "g")
    return c.rect(10, 12, 16, 1, "G").rect(10, 13, 16, 2, "k").rect(24, 8, 2, 1, "w")


def psp() -> Canvas:
    c = _handheld_h(Canvas(), "D", "k", "S", "m")
    return c.rect(8, 6, 16, 10, "d").rect(9, 7, 14, 8, "S").rect(10, 8, 12, 6, "c").rect(26, 8, 2, 2, "n").rect(24, 10, 2, 2, "b")


def xbox() -> Canvas:
    c = Canvas().rect(3, 6, 26, 13, "D").rect(3, 6, 26, 2, "d").rect(3, 17, 26, 2, "k")
    c.disc(16, 12.5, 5.5, "N").disc(16, 12.5, 4.5, "n")
    for i in range(5):
        c.px(14 + i, 10 + i, "D").px(18 - i, 10 + i, "D")
    return c


def pcengine() -> Canvas:
    c = Canvas().rect(8, 5, 16, 14, "w").rect(8, 17, 16, 2, "g").rect(22, 5, 2, 14, "g")
    return c.rect(10, 8, 12, 3, "D").rect(10, 13, 12, 1, "r").rect(10, 15, 5, 1, "b")


def neogeo() -> Canvas:
    c = Canvas().rect(3, 6, 26, 13, "D").rect(3, 6, 26, 2, "d").rect(3, 13, 26, 1, "y")
    return c.rect(6, 9, 20, 3, "k").rect(6, 15, 2, 2, "r").rect(10, 15, 2, 2, "b").rect(14, 15, 2, 2, "y").rect(18, 15, 2, 2, "n")


def arcade() -> Canvas:
    c = Canvas().rect(8, 1, 16, 20, "B").rect(9, 2, 14, 3, "y").rect(10, 3, 12, 1, "o")
    c.rect(10, 6, 12, 8, "D").rect(11, 7, 10, 6, "N").rect(12, 8, 8, 4, "n")
    c.rect(7, 14, 18, 3, "d").rect(12, 14, 1, 2, "r").rect(11, 16, 3, 1, "D")
    return c.rect(17, 15, 2, 1, "y").rect(20, 15, 2, 1, "c").rect(9, 18, 14, 3, "P")


def atari2600() -> Canvas:
    c = Canvas().rect(3, 7, 26, 12, "D").rect(3, 7, 26, 2, "d").rect(3, 13, 26, 6, "W").rect(3, 13, 26, 1, "O")
    return c.rect(6, 9, 3, 1, "g").rect(11, 9, 3, 1, "g").rect(23, 9, 3, 1, "g").rect(12, 10, 8, 2, "k")


def atari7800() -> Canvas:
    c = Canvas().rect(3, 6, 26, 13, "D").rect(3, 6, 26, 2, "d")
    for y in (9, 11, 13):
        c.rect(6, y, 20, 1, "d")
    return c.rect(5, 16, 3, 1, "r").rect(24, 16, 3, 1, "G")


def lynx() -> Canvas:
    c = _handheld_h(Canvas(), "D", "k", "L", "o")
    return c.rect(2, 5, 28, 2, "d").rect(9, 7, 14, 9, "k").rect(10, 8, 12, 7, "L")


def wonderswan() -> Canvas:
    return _handheld_v(Canvas(), "w", "g", "L", "b")


def ngp() -> Canvas:
    c = _handheld_h(Canvas(), "S", "s", "L", "r")
    return c.rect(9, 6, 14, 10, "k").rect(10, 7, 12, 8, "c")


def virtualboy() -> Canvas:
    c = Canvas().rect(4, 3, 24, 10, "D").rect(4, 3, 24, 2, "d").rect(6, 5, 7, 6, "r").rect(19, 5, 7, 6, "r")
    c.rect(7, 6, 5, 4, "R").rect(20, 6, 5, 4, "R").rect(13, 5, 6, 3, "d")
    return c.rect(14, 13, 4, 5, "d").rect(7, 18, 18, 3, "d").rect(7, 18, 18, 1, "G")


def msx() -> Canvas:
    c = Canvas().rect(2, 8, 28, 11, "d").rect(2, 8, 28, 2, "G").rect(2, 17, 28, 2, "D")
    for y in (11, 13, 15):
        for x in range(4, 26, 2):
            c.px(x, y, "g")
    return c.rect(26, 11, 3, 5, "D").rect(22, 5, 6, 3, "D")


def amiga() -> Canvas:
    c = Canvas().rect(2, 8, 28, 11, "e").rect(2, 17, 28, 2, "E").rect(2, 8, 28, 1, "w")
    c.rect(4, 10, 18, 5, "E").rect(4, 11, 18, 1, "d").rect(4, 13, 18, 1, "d").rect(24, 10, 4, 5, "g")
    return c.rect(24, 16, 5, 1, "D").rect(5, 16, 3, 1, "r").rect(9, 16, 3, 1, "n")


def recent() -> Canvas:
    c = Canvas().disc(16, 11, 10, "w").disc(16, 11, 8.5, "g").disc(16, 11, 7.5, "w")
    c.rect(16, 5, 1, 7, "D").rect(16, 11, 5, 1, "D").rect(15, 10, 3, 3, "r")
    for x, y in ((16, 3), (16, 18), (7, 11), (24, 11)):
        c.px(x, y, "D")
    return c


def favorites() -> Canvas:
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
    c = Canvas().art(8, 5, heart, {"x": "m"})
    return c.rect(10, 6, 3, 2, "w").rect(9, 8, 2, 1, "w")


def all_games() -> Canvas:
    c = Canvas()
    for x, y, body, label in ((2, 9, "d", "b"), (11, 6, "G", "r"), (20, 3, "g", "y")):
        c.rect(x, y, 10, 13, body).rect(x + 2, y + 2, 6, 5, label).rect(x + 3, y + 10, 4, 3, "D")
    return c


def cartridge() -> Canvas:
    """For consoles Arcadia has no sprite for (ones you add yourself)."""
    c = Canvas().rect(9, 2, 14, 18, "G").rect(9, 2, 14, 2, "g").rect(11, 5, 10, 8, "b").rect(13, 7, 6, 4, "c")
    return c.rect(11, 16, 10, 3, "D").rect(9, 4, 1, 14, "d")


SPRITES: dict[str, Callable[[], Canvas]] = {
    "nes": nes, "snes": snes, "n64": n64, "gc": gc, "wii": wii, "wiiu": wiiu, "switch": switch,
    "gb": gb, "gbc": gbc, "gba": gba, "nds": nds, "n3ds": n3ds,
    "genesis": genesis, "sms": sms, "gamegear": gamegear, "segacd": segacd, "saturn": saturn, "dreamcast": dreamcast,
    "psx": psx, "ps2": ps2, "ps3": ps3, "psp": psp, "xbox": xbox,
    "pcengine": pcengine, "neogeo": neogeo, "arcade": arcade,
    "atari2600": atari2600, "atari7800": atari7800, "lynx": lynx, "wonderswan": wonderswan, "ngp": ngp,
    "virtualboy": virtualboy, "msx": msx, "amiga": amiga,
    "__recent__": recent, "__favorites__": favorites, "__all__": all_games,
}


@lru_cache(maxsize=None)
def sprite_image(view_id: str) -> QImage:
    return SPRITES.get(view_id, cartridge)().image()


# ----- drawing: hard-edged scaling and the glow -----

def scaled(view_id: str, width: int) -> QPixmap:
    """The sprite at this width with crisp pixels (no smoothing)."""
    height = round(width * H / W)
    return QPixmap.fromImage(sprite_image(view_id).scaled(QSize(width, height), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation))


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
