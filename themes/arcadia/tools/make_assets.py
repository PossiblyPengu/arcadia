#!/usr/bin/env python3
"""Makes the theme's generated artwork: a 1-pixel box, soft gradients and one tinted glow per system.

Run from the repository root:  python3 themes/arcadia/tools/make_assets.py
Needs Pillow. The system list comes from the bundled es_systems.xml; each system's glow hue comes from its name (a few
well-known consoles get their familiar colour), so every system has a stable colour of its own.
"""

from __future__ import annotations

import colorsys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
BRAND = {
    "nes": "#e4372f", "famicom": "#e4372f", "snes": "#8e7cc3", "sfc": "#8e7cc3", "n64": "#3fae5a", "gc": "#7a6ad8",
    "wii": "#4fc3f7", "wiiu": "#29a8d8", "switch": "#ff4a55", "gb": "#8fae3b", "gbc": "#a26bd6", "gba": "#6a5acd",
    "nds": "#6bb7e8", "n3ds": "#e5484d", "genesis": "#2f6fdb", "megadrive": "#2f6fdb", "mastersystem": "#d83a3a",
    "gamegear": "#4d8ad6", "segacd": "#3b7ddd", "saturn": "#5a7fb5", "dreamcast": "#f28c28", "psx": "#8a93a6",
    "ps2": "#3a64c8", "ps3": "#4a5d86", "psp": "#5b6b8c", "xbox": "#52b043", "pcengine": "#f0a030", "neogeo": "#d4af37",
    "arcade": "#e8573f", "atari2600": "#c9812b", "atari7800": "#c24a3a", "atarilynx": "#d88a2c", "wonderswan": "#3aa0c8",
    "ngp": "#d4af37", "virtualboy": "#e0242c", "msx": "#4aa3df", "amiga": "#e8903a", "dos": "#8a8f99", "scummvm": "#d9a441",
}


def tint(name: str) -> tuple[int, int, int]:
    if name in BRAND:
        h = BRAND[name].lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    hue = (zlib.crc32(name.encode()) % 360) / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.58, 0.62)
    return int(r * 255), int(g * 255), int(b * 255)


def glow(color: tuple[int, int, int], size: int = 256) -> Image.Image:
    """A soft ellipse of light, brightest at the centre, fading to nothing before the edge."""
    img = Image.new("RGBA", (size, size), color + (0,))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([size * 0.28, size * 0.28, size * 0.72, size * 0.72], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.1))
    img.putalpha(mask.point(lambda v: int(v * 0.55)))
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "glow").mkdir(exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(ASSETS / "pixel.png")
    # vertical fade: transparent at the top to opaque at the bottom, white (tinted by the theme)
    fade = Image.new("RGBA", (4, 256))
    for y in range(256):
        fade.putpixel((0, y), (255, 255, 255, y))
        for x in range(1, 4):
            fade.putpixel((x, y), (255, 255, 255, y))
    fade.save(ASSETS / "fade-down.png")
    fade.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(ASSETS / "fade-up.png")
    glow(tint("default")).save(ASSETS / "glow" / "default.png", optimize=True)
    names = [s.findtext("name") for s in ET.parse(ROOT.parent.parent / "resources/systems/linux/es_systems.xml").getroot().iter("system")]
    for name in sorted(set(names)):
        glow(tint(name)).save(ASSETS / "glow" / f"{name}.png", optimize=True)
    print(len(names), "system glows")


if __name__ == "__main__":
    main()
