"""Console logos, fetched to your own machine and drawn in the pixel style of each console's era.

Arcadia doesn't ship logos (they're the makers' trademarks). Instead, File -> View -> "Download console logos"
fetches each console's logo image from Wikipedia / Wikimedia Commons and keeps it in your own media folder
(media/logos), purely to label the console on screen. Each download is then redrawn at the pixel size and colour
depth of the console's generation (the same eras as the console pictures), on a light or dark plaque so that
black or white logos both show up.

The originals are kept (media/logos/source) so the pixel versions can be redone without downloading again.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from arcadia.emulators import EmulatorError, Fetcher
from arcadia.eras import STYLES, EraStyle, era_of

SOURCES = Path(__file__).resolve().parent / "assets" / "logo_sources.json"
HOSTS = frozenset({"en.wikipedia.org", "commons.wikimedia.org", "upload.wikimedia.org", "thumb.wikimedia.org"})
OUTLINE = (13, 14, 19, 255)
WIDTH_FETCH = 330  # how wide a picture to ask the server to render a logo at (it is only ever drawn at ~150 pixels)


def sources() -> dict[str, list[str]]:
    """console id -> Wikipedia / Commons file names to try, best first."""
    try:
        data = json.loads(SOURCES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: [str(n) for n in v] for k, v in data.items() if isinstance(v, list)}


def logo_dir(media: Path) -> Path:
    return media / "logos"


def source_dir(media: Path) -> Path:
    return media / "logos" / "source"


def _fetcher() -> Fetcher:
    return Fetcher(api_base="https://en.wikipedia.org", hosts=HOSTS, timeout=30.0)


def _url(host: str, name: str, width: int | None = WIDTH_FETCH) -> str:
    from urllib.parse import quote

    base = f"https://{host}/wiki/Special:FilePath/{quote(name.replace(' ', '_'))}"
    return f"{base}?width={width}" if width else base


# ----------------------------------------------------------------------------
# Turning a logo into pixel art
# ----------------------------------------------------------------------------

def _opaque_box(image: QImage, threshold: int = 24) -> tuple[int, int, int, int] | None:
    w, h = image.width(), image.height()
    left, top, right, bottom = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if image.pixelColor(x, y).alpha() > threshold:
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    return None if right < 0 else (left, top, right - left + 1, bottom - top + 1)


def _flatten_white(image: QImage) -> QImage:
    """A logo saved on a white background (a JPEG, say) gets its near-white edges made transparent."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32)
    corner = out.pixelColor(0, 0)
    if corner.alpha() < 250 or min(corner.red(), corner.green(), corner.blue()) < 235:
        return out
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            if min(c.red(), c.green(), c.blue()) >= 240:
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return out


def _mean_luminance(image: QImage) -> float:
    total, count = 0.0, 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if c.alpha() > 128:
                total += (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
                count += 1
    return total / count if count else 0.5


def _median_cut(pixels: list[tuple[int, int, int]], count: int) -> list[tuple[int, int, int]]:
    """At most `count` representative colours for these pixels."""
    boxes = [pixels]
    while len(boxes) < count:
        boxes.sort(key=len, reverse=True)
        box = boxes.pop(0)
        if len(box) < 2:
            boxes.append(box)
            break
        spans = [max(p[i] for p in box) - min(p[i] for p in box) for i in range(3)]
        axis = spans.index(max(spans))
        box.sort(key=lambda p: p[axis])
        mid = len(box) // 2
        boxes += [box[:mid], box[mid:]]
    return [tuple(sum(p[i] for p in b) // len(b) for i in range(3)) for b in boxes if b]


def _quantize(image: QImage, count: int) -> QImage:
    w, h = image.width(), image.height()
    seen: dict[tuple[int, int, int], int] = {}
    for y in range(h):
        for x in range(w):
            c = image.pixelColor(x, y)
            if c.alpha() > 0:
                key = (c.red(), c.green(), c.blue())
                seen[key] = seen.get(key, 0) + 1
    if len(seen) <= count:
        return image
    flat = [k for k, n in seen.items() for _ in range(min(n, 12))]  # weight by how common, without huge lists
    palette = _median_cut(flat, count)
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    out = QImage(image)
    for y in range(h):
        for x in range(w):
            c = image.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            key = (c.red(), c.green(), c.blue())
            if key not in cache:
                cache[key] = min(palette, key=lambda p: (p[0] - key[0]) ** 2 + (p[1] - key[1]) ** 2 + (p[2] - key[2]) ** 2)
            r, g, b = cache[key]
            out.setPixelColor(x, y, QColor(r, g, b, c.alpha()))
    return out


def _outline(image: QImage) -> QImage:
    w, h = image.width(), image.height()
    out = QImage(w + 2, h + 2, QImage.Format.Format_ARGB32)
    out.fill(0)
    painter = QPainter(out)
    painter.drawImage(1, 1, image)
    painter.end()
    solid = [[out.pixelColor(x, y).alpha() > 0 for x in range(w + 2)] for y in range(h + 2)]
    dark = QColor(*OUTLINE[:3])
    for y in range(h + 2):
        for x in range(w + 2):
            if solid[y][x]:
                continue
            if (x > 0 and solid[y][x - 1]) or (x < w + 1 and solid[y][x + 1]) or (y > 0 and solid[y - 1][x]) or (y < h + 1 and solid[y + 1][x]):
                out.setPixelColor(x, y, dark)
    return out


def pixelate_logo(source: QImage, era: EraStyle) -> QImage:
    """The logo redrawn in an era's pixel style: scaled to the era's width, put on a plaque (light for a dark
    logo, dark for a light one), reduced to the era's number of colours, with hard or soft edges, and outlined."""
    image = _flatten_white(source)
    box = _opaque_box(image)
    if box is None:
        raise EmulatorError("the logo picture was empty")
    image = image.copy(*box)
    pad = max(2, round(era.width * 0.055))
    inner_w = era.width - 2 * pad
    scale = min(inner_w / image.width(), (era.width * 0.5) / image.height())
    w, h = max(2, round(image.width() * scale)), max(2, round(image.height() * scale))
    small = image.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    dark_logo = _mean_luminance(small) < 0.55
    plate = QColor("#eceef2") if dark_logo else QColor("#26262e")
    canvas = QImage(w + 2 * pad, h + 2 * pad, QImage.Format.Format_ARGB32)
    canvas.fill(0)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, era.smooth)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(plate)
    painter.drawRoundedRect(QRectF(0, 0, canvas.width(), canvas.height()), pad * 1.2, pad * 1.2)
    painter.drawImage(pad, pad, small)
    painter.end()
    if not era.smooth:  # hard pixels: every pixel is either there or not
        for y in range(canvas.height()):
            for x in range(canvas.width()):
                c = canvas.pixelColor(x, y)
                if 0 < c.alpha() < 255:
                    c.setAlpha(255 if c.alpha() >= 140 else 0)
                    canvas.setPixelColor(x, y, c)
    return _outline(_quantize(canvas, era.colors))


def style_for(console_id: str) -> EraStyle:
    return STYLES[era_of(console_id) or "16-bit"]


# ----------------------------------------------------------------------------
# Downloading
# ----------------------------------------------------------------------------

@dataclass
class LogoResult:
    done: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def render_logo(media: Path, console_id: str) -> Path:
    """(Re)draw one console's pixel logo from its saved original."""
    original = source_dir(media) / f"{console_id}.png"
    image = QImage(str(original))
    if image.isNull():
        raise EmulatorError("the saved logo couldn't be read")
    out = logo_dir(media) / f"{console_id}.png"
    pixelate_logo(image, style_for(console_id)).save(str(out))
    return out


def fetch_logos(
    media: Path,
    ids: list[str] | None = None,
    fetcher: Fetcher | None = None,
    progress: Callable[[int, int], None] | None = None,
    pause: float = 0.4,
) -> LogoResult:
    """Download each console's logo (trying the file names in order), save the original, and draw the pixel version.
    One failing never stops the others."""
    fetcher = fetcher or _fetcher()
    wanted = sources()
    ids = [i for i in (ids or sorted(wanted)) if i in wanted]
    result = LogoResult()
    source_dir(media).mkdir(parents=True, exist_ok=True)
    logo_dir(media).mkdir(parents=True, exist_ok=True)
    for n, console_id in enumerate(ids, 1):
        error = "no logo found"
        for name in wanted[console_id]:
            for host, width in (("en.wikipedia.org", WIDTH_FETCH), ("commons.wikimedia.org", WIDTH_FETCH), ("en.wikipedia.org", None), ("commons.wikimedia.org", None)):
                target = source_dir(media) / f"{console_id}.png"
                try:
                    for attempt in range(3):  # a "too many requests" answer is waited out, not given up on
                        try:
                            fetcher.download(_url(host, name, width), target)
                            break
                        except EmulatorError as exc:
                            if "429" not in str(exc) and "too many" not in str(exc).lower() or attempt == 2:
                                raise
                            time.sleep(pause * 10 * (attempt + 1))
                    if QImage(str(target)).isNull():
                        raise EmulatorError("that wasn't a picture")  # an SVG with no rendered size, say
                    render_logo(media, console_id)
                    result.done.append(console_id)
                    break
                except (EmulatorError, OSError) as exc:
                    error = str(exc)
                    target.unlink(missing_ok=True)
                    time.sleep(pause)
            else:
                continue
            break
        else:
            result.failed[console_id] = error
        if progress:
            progress(n, len(ids))
        time.sleep(pause)
    return result
