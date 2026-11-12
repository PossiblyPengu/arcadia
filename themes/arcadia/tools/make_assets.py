#!/usr/bin/env python3
"""Makes the theme's generated artwork: a 1-pixel box, soft gradients, the focus ring, one pastel console tile and one
soft glow per system.

Run from the repository root:  python3 themes/arcadia/tools/make_assets.py
Needs Pillow. Console names, makers and brand colours come from the Linear theme bundled with ES-DE
(themes/linear-es-de/system/metadata), and the console pictures from its systemart. Each brand colour is moved to the
nearest of Arcadia's pastels (DESIGN.md), so the shelf of consoles reads as one warm set.
"""

from __future__ import annotations

import colorsys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
LINEAR = ROOT.parent / "linear-es-de" / "system"
TITLE_FONT = ROOT.parent.parent / "resources" / "fonts" / "Fraunces-SemiBold.ttf"

# Arcadia's pastels and the dark ink drawn on each (DESIGN.md).
PASTELS = [
    ((0xF4, 0xA2, 0x59), (0x2A, 0x17, 0x08)),  # amber
    ((0xF2, 0xC2, 0x7A), (0x33, 0x24, 0x0B)),  # sand
    ((0xA8, 0xC6, 0x9F), (0x1C, 0x2A, 0x1B)),  # sage
    ((0x9F, 0xD0, 0xC4), (0x13, 0x2C, 0x27)),  # mint
    ((0x9F, 0xB8, 0xD6), (0x16, 0x24, 0x36)),  # blue
    ((0xB9, 0xA6, 0xDC), (0x2B, 0x22, 0x40)),  # lavender
    ((0xE6, 0xA3, 0xC4), (0x3A, 0x18, 0x2A)),  # pink
    ((0xE9, 0x89, 0x7A), (0x3A, 0x1F, 0x19)),  # rose
    ((0xC9, 0xB8, 0xA6), (0x2A, 0x21, 0x1C)),  # oat, for greys
]
TILE = (440, 500)
def glow(color: tuple[int, int, int], size: int = 256) -> Image.Image:
    """A soft ellipse of light, brightest at the centre, fading to nothing before the edge."""
    img = Image.new("RGBA", (size, size), color + (0,))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([size * 0.28, size * 0.28, size * 0.72, size * 0.72], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.1))
    img.putalpha(mask.point(lambda v: int(v * 0.55)))
    return img


def metadata(name: str) -> dict[str, str]:
    """The Linear theme's variables for a system (its defaults filled in from _default.xml)."""
    out: dict[str, str] = {}
    for f in (LINEAR / "metadata" / "_default.xml", LINEAR / "metadata" / f"{name}.xml"):
        if f.exists():
            variables = ET.parse(f).getroot().find("variables")
            for v in variables if variables is not None else []:
                out[v.tag] = (v.text or "").strip()
    return out


# Familiar consoles get the pastel nearest their own colours; the rest get a stable pastel from their name.
FAMILIAR = {
    "amber": "dreamcast pcengine pcenginecd tg16 tg-cd atari2600 atari7800 atari5200 atarilynx amiga amigacd32 scummvm",
    "sand": "arcade mame fbneo fba neogeo neogeocd cps cps1 cps2 cps3 ngp ngpc gameandwatch auto-favorites",
    "sage": "gb sgb n64 n64dd xbox xbox360 xboxone virtualboy pokemini",
    "mint": "gamegear wonderswan wonderswancolor nds psvita",
    "blue": "genesis megadrive megadrivejp segacd megacd saturn sega32x ps2 ps3 ps4 psp wii wiiu auto-allgames",
    "lavender": "snes sfc snesna satellaview gba gc auto-lastplayed",
    "pink": "gbc",
    "rose": "nes famicom fds mastersystem mark3 switch n3ds sg-1000",
    "oat": "psx c64 dos pc windows",
}
NAMED = {n: i for i, key in enumerate(["amber", "sand", "sage", "mint", "blue", "lavender", "pink", "rose", "oat"])
         for n in FAMILIAR[key].split()}


def pastel(name: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """The system's pastel and ink (see FAMILIAR)."""
    if name in NAMED:
        return PASTELS[NAMED[name]]
    return PASTELS[zlib.crc32(name.encode()) % (len(PASTELS) - 1)]


def console_picture(name: str) -> Image.Image | None:
    """The console or controller from the Linear systemart, without the logo and year printed under it."""
    f = LINEAR / "systemart" / f"{name}.webp"
    if not f.exists():
        return None
    img = Image.open(f).convert("RGBA")
    alpha = img.getchannel("A")
    w, h = img.size
    rows = list((np.asarray(alpha) > 24).any(axis=1))
    # the first block of content rows that is followed by a clear gap is the picture
    start = next((y for y, v in enumerate(rows) if v), None)
    if start is None:
        return None
    end, gap = start, 0
    for y in range(start, h):
        if rows[y]:
            end, gap = y, 0
        else:
            gap += 1
            if gap > h * 0.025 and end - start > h * 0.2:
                break
    box = alpha.crop((0, start, w, end + 1)).getbbox()
    if box is None:
        return None
    return img.crop((box[0], start + box[1], box[2], start + box[3]))


def fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, sizes: range) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """The largest size at which text fits in one line, or else in two."""
    for size in sizes:
        font = ImageFont.truetype(str(TITLE_FONT), size)
        if draw.textlength(text, font=font) <= width:
            return font, [text]
    for size in sizes:
        font = ImageFont.truetype(str(TITLE_FONT), size)
        words = text.split()
        for i in range(len(words) - 1, 0, -1):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            if draw.textlength(a, font=font) <= width and draw.textlength(b, font=font) <= width:
                return font, [a, b]
    font = ImageFont.truetype(str(TITLE_FONT), sizes[-1])
    return font, [text]


def tile(name: str) -> Image.Image:
    """A pastel card: the console's picture on top, its name below in the card's own ink."""
    meta = metadata(name)
    color, ink = pastel(name)
    s = 2  # draw at double size, then shrink, for smooth edges
    W, H = TILE[0] * s, TILE[1] * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(W * 0.13), fill=color + (255,))
    # a lighter wash behind the picture
    wash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(wash).ellipse([W * 0.12, H * 0.06, W * 0.88, H * 0.66], fill=(255, 255, 255, 70))
    img = Image.alpha_composite(img, wash.filter(ImageFilter.GaussianBlur(W * 0.06)))
    d = ImageDraw.Draw(img)
    pic = console_picture(name)
    if pic is not None:
        box_w, box_h = W * 0.74, H * 0.5
        k = min(box_w / pic.width, box_h / pic.height)
        pic = pic.resize((max(1, int(pic.width * k)), max(1, int(pic.height * k))), Image.LANCZOS)
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        px, py = int((W - pic.width) / 2), int(H * 0.37 - pic.height / 2)
        shadow.paste((0, 0, 0, 60), (px, py + int(H * 0.012)), pic.getchannel("A"))
        img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(W * 0.012)))
        img.alpha_composite(pic, (px, py))
        d = ImageDraw.Draw(img)
    label = meta.get("systemName") or name
    font, lines = fit_text(d, label, int(W * 0.84), range(int(46 * s), int(26 * s), -2 * s))
    line_h = font.size * 1.12
    y = H * 0.79 - line_h * len(lines) / 2
    for line in lines:
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y), line, font=font, fill=ink + (255,))
        y += line_h
    return img.resize(TILE, Image.LANCZOS)


RING_MARGIN = 24  # px round the tile in a ring image, at tile scale
COVER = (300, 400)


def ring(size: tuple[int, int], radius: float) -> str:
    """A focus ring: a rounded outline a little way outside an item, white so the theme can tint it."""
    gap, stroke, m = 10, 8, RING_MARGIN
    w, h = size[0] + 2 * m, size[1] + 2 * m
    off = m - gap - stroke / 2
    r = radius + gap + stroke / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect x="{off}" y="{off}" width="{w - 2 * off}" height="{h - 2 * off}" rx="{r:.1f}" '
            f'fill="none" stroke="#ffffff" stroke-width="{stroke}"/></svg>\n')


def play_button() -> str:
    """The Play button: a pill with a play mark and the word cut out of it, white so the theme can tint it.
    The cut-outs show the ground through, which gives dark text on the accent."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(str(ROOT.parent.parent / "resources" / "fonts" / "Nunito-ExtraBold.ttf"))
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = 25.0 / font["head"].unitsPerEm
    w, h, x, baseline, parts = 176, 64, 76.0, 41.0, []
    for ch in "Play":
        g = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        parts.append(pen.getCommands())
        x += glyphs[g].width * scale
    r = h / 2
    pill = f"M{r} 0H{w - r}A{r} {r} 0 0 1 {w - r} {h}H{r}A{r} {r} 0 0 1 {r} 0Z"
    tri = "M44 21.5v21a1.6 1.6 0 0 0 2.4 1.4l16.8-10.5a1.6 1.6 0 0 0 0-2.8L46.4 20.1A1.6 1.6 0 0 0 44 21.5Z"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<path fill="#ffffff" fill-rule="evenodd" d="{pill} {tri} {" ".join(parts)}"/></svg>\n')


def placeholder() -> Image.Image:
    """The cover shown in the list variant for a game without art: a warm tile with a small gamepad."""
    s = 2
    W, H = COVER[0] * s, COVER[1] * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(W * 0.1), fill=(0x36, 0x2A, 0x23, 255))
    ink, lw = (0x6B, 0x57, 0x48, 255), int(W * 0.03)
    cx, cy, pw, ph = W / 2, H * 0.46, W * 0.5, W * 0.22
    d.rounded_rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2], radius=int(ph / 2), outline=ink, width=lw)
    d.line([(cx - pw * 0.3, cy), (cx - pw * 0.1, cy)], fill=ink, width=lw)
    d.line([(cx - pw * 0.2, cy - pw * 0.1), (cx - pw * 0.2, cy + pw * 0.1)], fill=ink, width=lw)
    for dx, dy in ((0.17, -0.05), (0.27, 0.05)):
        r = W * 0.022
        d.ellipse([cx + pw * dx - r, cy + pw * dy - r, cx + pw * dx + r, cy + pw * dy + r], fill=ink)
    return img.resize(COVER, Image.LANCZOS)


def vectors() -> None:
    (ASSETS / "ring.svg").write_text(ring(TILE, TILE[0] * 0.13))
    (ASSETS / "cover-ring.svg").write_text(ring(COVER, COVER[0] * 0.1))
    (ASSETS / "play.svg").write_text(play_button())
    placeholder().save(ASSETS / "placeholder.png", optimize=True)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "glow").mkdir(exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(ASSETS / "pixel.png")
    (ASSETS / "tiles").mkdir(exist_ok=True)
    vectors()
    glow(PASTELS[-1][0]).save(ASSETS / "glow" / "default.png", optimize=True)
    names = {s.findtext("name") for s in ET.parse(ROOT.parent.parent / "resources/systems/linux/es_systems.xml").getroot().iter("system")}
    names |= {f.stem for f in (LINEAR / "systemart").glob("*.webp")}
    for name in sorted(names):
        glow(pastel(name)[0]).save(ASSETS / "glow" / f"{name}.png", optimize=True)
        tile(name).save(ASSETS / "tiles" / f"{name}.webp", quality=88, method=6)
    print(len(names), "system tiles and glows")


if __name__ == "__main__":
    import sys

    vectors() if "--vectors" in sys.argv else main()
