#!/usr/bin/env python3
"""Draws resources/graphics/splash.svg: the Arcadia mark over the word Arcadia, as plain paths (the SVG renderer has no text).

Run from the repository root:  python3 tools/make_splash.py   (needs fontTools: pip install fonttools)
"""

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONT = "resources/fonts/Fraunces-SemiBold.ttf"
WORD = "Arcadia"
OUT = "resources/graphics/splash.svg"


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


# The mark: a soft amber tile with a gamepad drawn into it, the same shape as the console tiles.
MARK = '''  <g transform="translate(530 140)">
    <rect x="0" y="0" width="220" height="220" rx="64" fill="#f4a259"/>
    <path d="M58 84h104a30 30 0 0 1 0 60h-14l-14-12H74l-14 12H58a30 30 0 0 1 0-60z" fill="none" stroke="#2a1708" stroke-width="10" stroke-linejoin="round"/>
    <path d="M70 114h28M84 100v28" stroke="#2a1708" stroke-width="10" stroke-linecap="round"/>
    <circle cx="140" cy="106" r="7" fill="#2a1708"/>
    <circle cx="158" cy="122" r="7" fill="#2a1708"/>
  </g>'''


def main() -> None:
    d, width = word_paths(WORD, 112, 2)
    word_x = (1280 - width) / 2
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#f4a259" stop-opacity="0.32"/>
      <stop offset="1" stop-color="#f4a259" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="640" cy="250" r="250" fill="url(#glow)"/>
{MARK}
  <path transform="translate({word_x:.1f} 520)" fill="#f7ecde" d="{d}"/>
</svg>
'''
    open(OUT, "w").write(svg)
    print("wrote", OUT, f"(word {width:.0f}px wide)")


if __name__ == "__main__":
    main()


def window_icon(path: str = "resources/graphics/window_icon_256.png") -> None:
    """The same mark as es-app/assets/arcadia.svg, drawn with Pillow for the window icon."""
    from PIL import Image, ImageDraw

    s = 4  # draw big, then shrink, for smooth edges
    W = 256 * s
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=70 * s, fill=(244, 162, 89, 255))
    ink = (42, 23, 8, 255)
    w = 11 * s
    # gamepad outline
    d.rounded_rectangle([50 * s, 96 * s, 206 * s, 164 * s], radius=34 * s, outline=ink, width=w)
    d.line([(78 * s, 130 * s), (110 * s, 130 * s)], fill=ink, width=w)
    d.line([(94 * s, 114 * s), (94 * s, 146 * s)], fill=ink, width=w)
    for cx, cy in ((158, 120), (178, 140)):
        d.ellipse([(cx - 8) * s, (cy - 8) * s, (cx + 8) * s, (cy + 8) * s], fill=ink)
    img.resize((256, 256), Image.LANCZOS).save(path)
    print("wrote", path)


if __name__ == "__main__":
    window_icon()
