#!/usr/bin/env python3
"""Turn photographs of consoles into the pixel-art pictures Arcadia ships (arcadia/assets/consoles/*.png).

This is build-time tooling: Arcadia itself only loads the finished PNGs. Needs Pillow and numpy.

    python tools/make_console_art.py PHOTO_DIR [id ...]

PHOTO_DIR holds one photo per console, named <id>.<ext> (png/jpg/img). Each is cut out from its white
background, cropped (tools/console_crops.json), scaled down, limited to a small palette, and given a
one-pixel dark outline. Sources and licences are listed in arcadia/assets/consoles/ATTRIBUTION.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

MAX_W, MAX_H = 104, 78  # the pixel size of the biggest side of a finished picture
COLORS = 28
OUTLINE = (13, 14, 19, 255)
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "arcadia" / "assets" / "consoles"


def cut_out(image: Image.Image) -> Image.Image:
    """Make the (white) background transparent: only white connected to the picture's edge goes."""
    im = image.convert("RGBA")
    flat = Image.new("RGB", im.size, (255, 255, 255))
    flat.paste(im, mask=im.split()[3])
    work = flat.copy()
    sentinel = (255, 0, 255)
    w, h = work.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)] + [(x, 0) for x in range(0, w, max(1, w // 8))] + [(x, h - 1) for x in range(0, w, max(1, w // 8))] + [(0, y) for y in range(0, h, max(1, h // 8))] + [(w - 1, y) for y in range(0, h, max(1, h // 8))]
    for xy in seeds:
        pixel = work.getpixel(xy)
        if pixel != sentinel and min(pixel) >= 232:
            ImageDraw.floodfill(work, xy, sentinel, thresh=16)
    arr = np.array(work)
    background = (arr[:, :, 0] == 255) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 255)
    background |= _white_pockets(np.array(flat), background)
    out = np.array(flat.convert("RGBA"))
    out[:, :, 3] = np.where(background, 0, 255)
    return Image.fromarray(out)


def _white_pockets(rgb: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Pure white areas the edge fill couldn't reach (the gap inside a loop of cable, say). A console's own
    whites are never quite pure, so a sizeable patch of pure white is background."""
    white = (rgb.min(axis=2) >= 253) & ~background
    h, w = white.shape
    seen = np.zeros_like(white)
    pockets = np.zeros_like(white)
    for y0, x0 in zip(*np.nonzero(white)):
        if seen[y0, x0]:
            continue
        stack, patch = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            patch.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(patch) >= 120:
            ys, xs = zip(*patch)
            pockets[list(ys), list(xs)] = True
    return pockets


def pixelate(image: Image.Image) -> Image.Image:
    box = image.getbbox()
    image = image.crop(box)
    w, h = image.size
    scale = min(MAX_W / w, MAX_H / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = image.resize(size, Image.BOX)
    alpha = np.array(small.split()[3]) >= 150
    rgb = small.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.12)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    quant = np.array(rgb.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB"))
    out = np.zeros((size[1] + 2, size[0] + 2, 4), dtype=np.uint8)
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


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    photos = Path(argv[0])
    crops = json.loads((HERE / "console_crops.json").read_text())
    wanted = argv[1:] or sorted(crops)
    OUT.mkdir(parents=True, exist_ok=True)
    for cid in wanted:
        found = next((p for p in photos.glob(f"{cid}.*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".img")), None)
        if found is None:
            print(f"{cid}: no photo, skipped")
            continue
        image = Image.open(found)
        left, top, right, bottom = crops.get(cid, [0, 0, 1, 1])
        w, h = image.size
        image = image.crop((int(left * w), int(top * h), int(right * w), int(bottom * h)))
        pixelate(cut_out(image)).save(OUT / f"{cid}.png", optimize=True)
        print(f"{cid}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
