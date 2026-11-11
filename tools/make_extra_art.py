#!/usr/bin/env python3
"""Draw the pictures that have no photograph, in the same pixel-art style as the photographed consoles.

Arcade cabinet, the Recently played / Favorites / All games tiles, and the generic cartridge shown for a
console you add yourself. They are original to Arcadia: small 3D models (tools/voxel.py) rendered at an
isometric angle, then cut down to pixel art by the same step as the photographs (make_console_art.pixelate).
Needs PySide6, Pillow and numpy.

    python tools/make_extra_art.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from make_console_art import OUT, pixelate  # noqa: E402
from voxel import Model  # noqa: E402


def arcade() -> Model:
    blue, trim, dark = "#2b44a6", "#171720", "#26262e"
    m = Model().box(0, 0, 0, 28, 32, 24, blue).box(0, 0, 24, 28, 22, 26, blue).box(0, 22, 21, 28, 12, 4, dark)
    m.box(0, 0, 50, 28, 23, 7, trim)  # the marquee
    m.front(2, 51, 24, 5, "#ffcf3a").front(5, 53, 18, 1, "#f28a1a").front(3, 55, 22, 1, "#fff2a8")
    m.front(3, 29, 22, 19, trim).front(5, 31, 18, 15, "#14724c").front(7, 33, 14, 11, "#1f9a66")  # the screen
    for x, z in ((9, 41), (13, 41), (17, 41), (11, 38), (15, 38), (9, 35), (13, 35), (17, 35)):  # a few invaders
        m.front(x, z, 2, 1, "#c8ffd8")
    m.front(10, 5, 8, 13, dark).front(11, 6, 6, 11, "#3a3a46").front(12, 11, 2, 3, "#d6322c").front(15, 11, 2, 3, "#d6322c")  # coin door
    m.top(2, 24, 24, 8, dark)
    m.box(7, 27, 25, 1, 1, 5, "#c9c9d2").cyl(7.5, 27.5, 30, 2.2, 3, "#d6322c")  # the joystick
    for x, c in ((14, "#f2c200"), (18, "#35b6e8"), (22, "#3fae5a")):
        m.top_disc(x, 27, 1.8, c).top_disc(x + 1, 31, 1.8, c)
    m.side(0, 0, 33, 3, trim).side(0, 30, 33, 5, "#e8318f").side(0, 36, 33, 2, "#35d6e8").side(0, 40, 33, 3, "#f2c200")
    return m


def clock() -> Model:
    m = Model().cyl_y(18, 21, 18, 0, 8, "#d6322c").cyl_y(18, 21, 15.5, 7, 3, "#f4f4ee")
    m.cyl_y(9, 38, 4.5, 3, 3, "#f2c200").cyl_y(27, 38, 4.5, 3, 3, "#f2c200")  # the bells
    for x in (7, 26):
        m.box(x, 2, 0, 4, 4, 4, "#3a3a42")
    for hour in range(12):  # the numbers' places
        a = math.radians(hour * 30)
        m.front_disc(18 + 12.5 * math.sin(a), 21 + 12.5 * math.cos(a), 1.2 if hour % 3 else 1.9, "#25252b")
    for length, angle, r in ((8.5, math.radians(305), 1.5), (12.5, math.radians(60), 1.1)):  # 10:10
        for step in range(int(length * 2)):
            m.front_disc(18 + step / 2 * math.sin(angle), 21 + step / 2 * math.cos(angle), r, "#25252b")
    m.front_disc(18, 21, 1.8, "#d6322c")
    return m


def favorites() -> Model:
    m = Model()
    for xx in range(32):
        for zz in range(30):
            u, v = (xx + 0.5 - 16) / 12.3, (zz + 0.5 - 13.5) / 12.3
            if (u * u + v * v - 1) ** 3 - u * u * v ** 3 <= 0:
                for yy in range(9):
                    m.v[(xx, yy, zz)] = "#e0306e"
    m._dirty()
    front = m._lookup()[0]
    for (xx, zz), yy in front.items():
        u, v = (xx + 0.5 - 16) / 12.3, (zz + 0.5 - 13.5) / 12.3
        shade = v * 0.7 + u * 0.35
        m.v[(xx, yy, zz)] = "#ff86ad" if shade > 0.62 else "#f2487f" if shade > 0.2 else "#e0306e" if shade > -0.3 else "#b81f57"
    for x, z in ((8, 21), (9, 22), (10, 22), (8, 20), (7, 19)):  # a glint
        m.front(x, z, 1, 1, "#ffffff")
    return m


def _cartridge(m: Model, x: int, y: int, body: str, label: str, art: str) -> None:
    m.box(x, y, 0, 22, 5, 26, body)
    m.carve(x, y, 23, 3, 5, 3).carve(x + 19, y, 23, 3, 5, 3)
    m.top(x + 4, y, 14, 5, "#6e6e78")
    for k in range(4):  # the grip ridges
        m.front(x + 5 + k * 3, 22, 1, 1, "#55555f")
    m.front(x + 3, 9, 16, 13, label).front(x + 5, 12, 12, 7, art).front(x + 7, 14, 8, 3, "#ffffff")
    m.front(x + 2, 0, 18, 4, "#2a2a32").front(x + 4, 0, 14, 2, "#c9a24a")
    m.side(y, 2, 5, 21, "#44444c")


def all_games() -> Model:
    m = Model()
    _cartridge(m, 0, 18, "#6a6a76", "#3e7bd6", "#7fb0ff")
    _cartridge(m, 17, 9, "#9b9ba6", "#d6322c", "#ff7a70")
    _cartridge(m, 34, 0, "#cdcdd6", "#f2c200", "#ffe27a")
    return m


def cartridge() -> Model:
    m = Model()
    _cartridge(m, 0, 0, "#8d8d98", "#3e7bd6", "#7fb0ff")
    return m


MODELS = {"arcade": arcade, "__recent__": clock, "__favorites__": favorites, "__all__": all_games, "cartridge": cartridge}


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in MODELS.items():
        image = build().render()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "render.png"
            image.save(str(path))
            pixelate(Image.open(path).convert("RGBA")).save(OUT / f"{name}.png", optimize=True)
        print(f"{name}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
