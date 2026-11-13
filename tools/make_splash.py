#!/usr/bin/env python3
"""Draws the boot screens, resources/graphics/splash.svg (cloud, light) and splash-dusk.svg (dusk, dark): the Arcadia mark
over the word Arcadia, as plain paths (the SVG renderer has no text). Also draws the window icon.

Run from the repository root:  python3 tools/make_splash.py   (needs fontTools: pip install fonttools)
"""

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONT = "resources/fonts/Fraunces-SemiBold.ttf"
WORD = "Arcadia"
OUT = {"resources/graphics/splash.svg": "#3a3150", "resources/graphics/splash-dusk.svg": "#f6f1fa"}


def word_paths(text: str, size: float, tracking: float) -> tuple[str, float]:
    font = TTFont(FONT)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    x, parts = 0.0, []
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        parts.append(pen.getCommands())
        x += glyphs[name].width * scale + tracking
    return " ".join(parts), x - tracking


# The mark (es-app/assets/arcadia.svg): a lowercase "a" and a pink dot on a lavender tile, the sister of Deckhand's "d.".
MARK = '''  <g transform="translate(530 140) scale(0.859375)">
    <rect width="256" height="256" rx="58" fill="#cdbdf0"/>
    <circle cx="110" cy="144" r="41" fill="none" stroke="#2f2448" stroke-width="27"/>
    <path d="M151 103v82" stroke="#2f2448" stroke-width="27" stroke-linecap="round"/>
    <circle cx="194" cy="178" r="15" fill="#f08fae"/>
  </g>'''


def main() -> None:
    d, width = word_paths(WORD, 112, 2)
    word_x = (1280 - width) / 2
    for out, ink in OUT.items():
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#f2b6cf" stop-opacity="0.45"/>
      <stop offset="1" stop-color="#f2b6cf" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="640" cy="250" r="250" fill="url(#glow)"/>
{MARK}
  <path transform="translate({word_x:.1f} 520)" fill="{ink}" d="{d}"/>
</svg>
'''
        open(out, "w").write(svg)
        print("wrote", out, f"(word {width:.0f}px wide)")


if __name__ == "__main__":
    main()


def window_icon(path: str = "resources/graphics/window_icon_256.png") -> None:
    """The same mark as es-app/assets/arcadia.svg, drawn with Pillow for the window icon."""
    from PIL import Image, ImageDraw

    s = 4  # draw big, then shrink, for smooth edges
    W = 256 * s
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=58 * s, fill=(0xCD, 0xBD, 0xF0, 255))
    ink = (0x2F, 0x24, 0x48, 255)
    w = 27 * s
    # the bowl of the "a": a ring
    r = 41 * s + w // 2
    d.ellipse([110 * s - r, 144 * s - r, 110 * s + r, 144 * s + r], outline=ink, width=w)
    # its stem, with round ends
    d.line([(151 * s, 103 * s), (151 * s, 185 * s)], fill=ink, width=w)
    for y in (103, 185):
        d.ellipse([151 * s - w // 2, y * s - w // 2, 151 * s + w // 2, y * s + w // 2], fill=ink)
    # the dot
    d.ellipse([(194 - 15) * s, (178 - 15) * s, (194 + 15) * s, (178 + 15) * s], fill=(0xF0, 0x8F, 0xAE, 255))
    img.resize((256, 256), Image.LANCZOS).save(path)
    print("wrote", path)


if __name__ == "__main__":
    window_icon()
