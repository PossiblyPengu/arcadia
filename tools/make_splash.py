#!/usr/bin/env python3
"""Draws resources/graphics/splash.svg: the Arcadia mark over the word ARCADIA, as plain paths (the SVG renderer has no text).

Run from the repository root:  python3 tools/make_splash.py   (needs fontTools: pip install fonttools)
"""

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONT = "resources/fonts/Akrobat-Bold.ttf"
WORD = "ARCADIA"
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


def main() -> None:
    d, width = word_paths(WORD, 120, 18)
    word_x = (1280 - width) / 2
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#5aa9ff" stop-opacity="0.45"/>
      <stop offset="1" stop-color="#5aa9ff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="640" cy="250" r="230" fill="url(#glow)"/>
  <g transform="translate(475 90) scale(1.25)">
    <path d="M72 64h112a8 8 0 0 1 8 8v100l-18 20H80a8 8 0 0 1-8-8z" fill="#2b2f42" stroke="#5aa9ff" stroke-width="6" stroke-linejoin="round"/>
    <rect x="92" y="84" width="72" height="52" rx="8" fill="#0e1017" stroke="#9aa1b4" stroke-width="3"/>
    <path d="M104 118l16-22 12 14 8-8 16 16z" fill="#5aa9ff"/>
    <rect x="96" y="152" width="64" height="8" rx="4" fill="#9aa1b4"/>
    <rect x="96" y="168" width="40" height="8" rx="4" fill="#5d6477"/>
  </g>
  <path transform="translate({word_x:.1f} 520)" fill="#f1f3f9" d="{d}"/>
</svg>
'''
    open(OUT, "w").write(svg)
    print("wrote", OUT, f"(word {width:.0f}px wide)")


if __name__ == "__main__":
    main()


def window_icon(path: str = "resources/graphics/window_icon_256.png") -> None:
    """The same mark as es-app/assets/arcadia.svg, drawn with Pillow for the window icon."""
    from PIL import Image, ImageDraw, ImageFilter

    s = 4  # draw big, then shrink, for smooth edges
    W = 256 * s
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    bg = Image.new("RGBA", (W, W))
    for y in range(W):
        t = y / W
        c = tuple(int(a + (b - a) * t) for a, b in zip((27, 30, 43), (14, 16, 23)))
        ImageDraw.Draw(bg).line([(0, y), (W, y)], fill=c + (255,))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=56 * s, fill=255)
    img.paste(bg, (0, 0), mask)
    glow = Image.new("RGBA", (W, W), (90, 169, 255, 0))
    gm = Image.new("L", (W, W), 0)
    ImageDraw.Draw(gm).ellipse([60 * s, 66 * s, 196 * s, 198 * s], fill=120)
    glow.putalpha(gm.filter(ImageFilter.GaussianBlur(30 * s)))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    body = [(72 * s, 64 * s), (192 * s, 64 * s), (192 * s, 172 * s), (174 * s, 192 * s), (72 * s, 192 * s)]
    d.polygon(body, fill=(43, 47, 66, 255), outline=(90, 169, 255, 255), width=6 * s)
    d.rounded_rectangle([92 * s, 84 * s, 164 * s, 136 * s], radius=8 * s, fill=(14, 16, 23, 255), outline=(154, 161, 180, 255), width=3 * s)
    d.polygon([(104 * s, 118 * s), (120 * s, 96 * s), (132 * s, 110 * s), (140 * s, 102 * s), (156 * s, 118 * s)], fill=(90, 169, 255, 255))
    d.rounded_rectangle([96 * s, 152 * s, 160 * s, 160 * s], radius=4 * s, fill=(154, 161, 180, 255))
    d.rounded_rectangle([96 * s, 168 * s, 136 * s, 176 * s], radius=4 * s, fill=(93, 100, 119, 255))
    img.resize((256, 256), Image.LANCZOS).save(path)
    print("wrote", path)


if __name__ == "__main__":
    window_icon()
