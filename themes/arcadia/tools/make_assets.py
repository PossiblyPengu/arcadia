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
    ((0xF7, 0xC1, 0x9A), (0x4A, 0x2A, 0x14)),  # peach
    ((0xF5, 0xDD, 0x9B), (0x46, 0x38, 0x12)),  # butter
    ((0xBC, 0xD9, 0xB0), (0x26, 0x39, 0x1F)),  # sage
    ((0xAD, 0xDF, 0xCF), (0x16, 0x3A, 0x31)),  # mint
    ((0xB3, 0xCD, 0xEF), (0x1B, 0x2C, 0x45)),  # sky
    ((0xCD, 0xBD, 0xF0), (0x2F, 0x24, 0x48)),  # lavender
    ((0xF2, 0xB6, 0xCF), (0x4A, 0x1F, 0x33)),  # pink
    ((0xF4, 0xB0, 0xA6), (0x4A, 0x22, 0x1C)),  # rose
    ((0xD4, 0xCE, 0xE0), (0x2E, 0x2A, 0x3A)),  # cloud, for greys
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
    "peach": "dreamcast pcengine pcenginecd tg16 tg-cd atari2600 atari7800 atari5200 atarilynx amiga amigacd32 scummvm",
    "butter": "arcade mame fbneo fba neogeo neogeocd cps cps1 cps2 cps3 ngp ngpc gameandwatch auto-favorites",
    "sage": "gb sgb n64 n64dd xbox xbox360 xboxone virtualboy pokemini",
    "mint": "gamegear wonderswan wonderswancolor nds psvita",
    "sky": "genesis megadrive megadrivejp segacd megacd saturn sega32x ps2 ps3 ps4 psp wii wiiu auto-allgames",
    "lavender": "snes sfc snesna satellaview gba gc auto-lastplayed",
    "pink": "gbc",
    "rose": "nes famicom fds mastersystem mark3 switch n3ds sg-1000",
    "cloud": "psx c64 dos pc windows",
}
NAMED = {n: i for i, key in enumerate(["peach", "butter", "sage", "mint", "sky", "lavender", "pink", "rose", "cloud"])
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


def play_button() -> tuple[str, str]:
    """The Play button as two layers of the same size, both white so the theme can tint them: the pill (accent) and
    the play mark with the word (the text colour that goes on the accent)."""
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
    head = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
    return (f'{head}<path fill="#ffffff" d="{pill}"/></svg>\n',
            f'{head}<path fill="#ffffff" d="{tri} {" ".join(parts)}"/></svg>\n')


def placeholder() -> Image.Image:
    """The cover shown in the list variant for a game without art: a soft lavender tile with a gamepad."""
    s = 2
    W, H = COVER[0] * s, COVER[1] * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(W * 0.1), fill=(0xE4, 0xDA, 0xF3, 255))
    ink, lw = (0xA9, 0x9C, 0xC8, 255), int(W * 0.03)
    cx, cy, pw, ph = W / 2, H * 0.46, W * 0.5, W * 0.22
    d.rounded_rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2], radius=int(ph / 2), outline=ink, width=lw)
    d.line([(cx - pw * 0.3, cy), (cx - pw * 0.1, cy)], fill=ink, width=lw)
    d.line([(cx - pw * 0.2, cy - pw * 0.1), (cx - pw * 0.2, cy + pw * 0.1)], fill=ink, width=lw)
    for dx, dy in ((0.17, -0.05), (0.27, 0.05)):
        r = W * 0.022
        d.ellipse([cx + pw * dx - r, cy + pw * dy - r, cx + pw * dx + r, cy + pw * dy + r], fill=ink)
    return img.resize(COVER, Image.LANCZOS)


def pastel_variables() -> None:
    """One small include per system with its pastel and ink, for the theme's title tiles and header chip."""
    out = ASSETS / "pastels"
    out.mkdir(exist_ok=True)

    def xml(color: tuple[int, int, int], ink: tuple[int, int, int]) -> str:
        hexed = lambda c: "".join(f"{v:02x}" for v in c)
        return (f"<theme>\n    <variables>\n        <systemPastel>{hexed(color)}</systemPastel>\n"
                f"        <systemInk>{hexed(ink)}</systemInk>\n    </variables>\n</theme>\n")

    (out / "_default.xml").write_text(xml(*PASTELS[-1]))
    for f in sorted((ASSETS / "tiles").glob("*.webp")):
        (out / f"{f.stem}.xml").write_text(xml(*pastel(f.stem)))


def vectors() -> None:
    (ASSETS / "ring.svg").write_text(ring(TILE, TILE[0] * 0.13))
    (ASSETS / "cover-ring.svg").write_text(ring(COVER, COVER[0] * 0.1))
    pill, label = play_button()
    (ASSETS / "play-pill.svg").write_text(pill)
    (ASSETS / "play-label.svg").write_text(label)
    (ASSETS / "play.svg").unlink(missing_ok=True)
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
    pastel_variables()
    print(len(names), "system tiles and glows")


if __name__ == "__main__":
    import sys

    if "--vectors" in sys.argv:
        vectors()
        pastel_variables()
    else:
        main()
