#!/usr/bin/env python3
"""Make arcadia/assets/icon.png: the generic cartridge, enlarged with hard pixels, on a rounded dark tile."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
cart = Image.open(ROOT / "arcadia" / "assets" / "consoles" / "cartridge.png").convert("RGBA")
size = 256
tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(tile)
for y in range(size):  # a soft purple-to-dark gradient
    shade = int(26 + 34 * (1 - y / size))
    draw.line([(0, y), (size, y)], fill=(shade + 12, shade, shade + 44, 255))
mask = Image.new("L", (size, size), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=52, fill=255)
tile.putalpha(mask)
scale = max(1, int((size * 0.72) // max(cart.size)))
big = cart.resize((cart.width * scale, cart.height * scale), Image.NEAREST)
tile.alpha_composite(big, ((size - big.width) // 2, (size - big.height) // 2))
tile.save(ROOT / "arcadia" / "assets" / "icon.png", optimize=True)
print("icon", tile.size)
