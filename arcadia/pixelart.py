"""The picture shown for each console: your own, the one that ships with Arcadia, or a generic cartridge.

* Your own: a PNG/WebP/JPEG named after the console (nes.png, snes.png, ...) in the media/consoles folder.
* The ones that ship with Arcadia (arcadia/assets/consoles/): pixel art made from photographs of the real
  consoles, plus a few drawn ones; see ATTRIBUTION.md there and the scripts in tools/ that make them.
* Logos you downloaded (media/logos, see logos.py), when the picture style is "logos": drawn in each console's era.
* Anything else (a console you added yourself) gets the generic cartridge.

Pictures are fitted into the same box, scaled with crisp pixels, and given a soft glow on hover.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

W, H = 128, 96  # the box a console is fitted into when shown (only the 4:3 shape matters)


# Your own artwork: a picture named after the console (nes.png, snes.png, psx.webp ...) in this folder is
# shown instead of the built-in render. Transparent backgrounds are best; any empty border is trimmed.
ART_TYPES = (".png", ".webp", ".jpg", ".jpeg")
_art_dir: Path | None = None


def _signature(folder: Path | None) -> tuple:
    """Which of your pictures exist and when they last changed, so nothing is redrawn unless that changes."""
    if folder is None or not folder.is_dir():
        return ()
    try:
        return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in folder.iterdir() if p.suffix.lower() in ART_TYPES))
    except OSError:
        return ()


_art_sig: tuple = ()
_logo_dir: Path | None = None
_style = "logos"
STYLES = ("logos", "drawings")


def configure(custom_dir: Path | None, logo_dir: Path | None = None, style: str | None = None) -> None:
    """Say where your own pictures and your downloaded logos are, and which style to prefer. Cheap to call
    again: the caches are only reset when something has actually changed."""
    global _art_dir, _logo_dir, _style, _art_sig
    style = style if style in STYLES else _style
    signature = (_signature(custom_dir), _signature(logo_dir), style)
    if (custom_dir, logo_dir, style) == (_art_dir, _logo_dir, _style) and signature == _art_sig:
        return
    _art_dir, _logo_dir, _style, _art_sig = custom_dir, logo_dir, style, signature
    for cached in (sprite_image, scaled, glow, _load_custom_cached, _load_bundled):
        cached.cache_clear()


def set_art_dir(folder: Path | None) -> None:
    """Where to look for your own console pictures (None = just the bundled ones)."""
    configure(folder, _logo_dir, _style)


def style() -> str:
    return _style


def art_dir() -> Path | None:
    return _art_dir


def custom_file(view_id: str) -> Path | None:
    if _art_dir is None or "/" in view_id or "\\" in view_id or view_id.startswith("."):
        return None
    for ext in ART_TYPES:
        path = _art_dir / f"{view_id}{ext}"
        if path.is_file():
            return path
    return None


def _load_custom(path: Path) -> QImage | None:
    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    # trim empty (transparent) borders so every picture is fitted by what's actually drawn
    xs = [x for x in range(image.width()) if any(image.pixelColor(x, y).alpha() > 8 for y in range(0, image.height(), 2))]
    ys = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() > 8 for x in range(0, image.width(), 2))]
    if not xs or not ys:
        return None
    return image.copy(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def is_custom(view_id: str) -> bool:
    return custom_file(view_id) is not None and _load_custom_cached(view_id) is not None


@lru_cache(maxsize=None)
def _load_custom_cached(view_id: str) -> QImage | None:
    path = custom_file(view_id)
    return _load_custom(path) if path else None


# The pictures that ship with Arcadia: pixel art made from photographs of the real consoles (see
# tools/make_console_art.py and arcadia/assets/consoles/ATTRIBUTION.md). A console without one falls
# back to the drawn 3D render above.
ASSETS = Path(__file__).resolve().parent / "assets" / "consoles"


def bundled_file(view_id: str) -> Path | None:
    """The picture to use for a console: its downloaded logo (in the logos style), else the bundled drawing."""
    if "/" in view_id or "\\" in view_id or view_id.startswith("."):
        return None
    if _style == "logos" and _logo_dir is not None:
        logo = _logo_dir / f"{view_id}.png"
        if logo.is_file():
            return logo
    path = ASSETS / f"{view_id}.png"
    return path if path.is_file() else None


def is_logo(view_id: str) -> bool:
    return not is_custom(view_id) and bundled_file(view_id) is not None and bundled_file(view_id).parent == _logo_dir


@lru_cache(maxsize=None)
def _load_bundled(view_id: str) -> QImage | None:
    path = bundled_file(view_id)
    if path is None:
        return None
    image = QImage(str(path))
    return None if image.isNull() else image.convertToFormat(QImage.Format.Format_ARGB32)


def is_bundled(view_id: str) -> bool:
    return not is_custom(view_id) and _load_bundled(view_id) is not None


@lru_cache(maxsize=None)
def sprite_image(view_id: str) -> QImage:
    custom = _load_custom_cached(view_id)
    if custom is not None:
        return custom
    bundled = _load_bundled(view_id)
    if bundled is not None:
        return bundled
    generic = _load_bundled("cartridge")
    if generic is not None:
        return generic
    blank = QImage(48, 36, QImage.Format.Format_ARGB32)  # only if the assets folder is missing
    blank.fill(QColor("#55555b"))
    return blank


# ----- drawing: hard-edged scaling and the glow -----

@lru_cache(maxsize=512)
def scaled(view_id: str, width: int) -> QPixmap:
    """The console fitted into a width x (3/4 width) box, standing on its floor, with crisp pixels (no
    smoothing). Every console is fitted the same way, so a handheld fills the box as much as a big console."""
    box_w, box_h = width, round(width * H / W)
    src = sprite_image(view_id)
    fit = min(box_w * 0.96 / src.width(), box_h * 0.94 / src.height())
    tw, th = max(1, round(src.width() * fit)), max(1, round(src.height() * fit))
    if is_custom(view_id):  # your own pictures are scaled smoothly
        big = src.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    elif is_bundled(view_id):
        # pixel art: enlarge by whole pixels first so every pixel stays a clean square, then ease down to the exact size
        k = max(1, -(-tw // src.width()) + 1)
        blocky = src.scaled(QSize(src.width() * k, src.height() * k), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        big = blocky.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    else:
        big = src.scaled(QSize(tw, th), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    out = QImage(box_w, box_h, QImage.Format.Format_ARGB32)
    out.fill(0)
    painter = QPainter(out)
    painter.drawImage((box_w - tw) // 2, box_h - th - round(box_h * 0.03), big)
    painter.end()
    return QPixmap.fromImage(out)


@lru_cache(maxsize=256)
def glow(view_id: str, width: int, color: str) -> QPixmap:
    """A soft halo in `color` the shape of the sprite, a little larger than it. (width is rounded so the
    cache stays small while the sprite animates in size.)"""
    pad = glow_padding(width)
    base = scaled(view_id, width)
    sil = QImage(base.width() + 2 * pad, base.height() + 2 * pad, QImage.Format.Format_ARGB32_Premultiplied)
    sil.fill(0)
    painter = QPainter(sil)
    painter.drawPixmap(pad, pad, base)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(sil.rect(), QColor(color))
    painter.end()
    # blur by shrinking and growing it again, smoothly; twice for a wider, softer spread
    small = sil.scaled(max(1, sil.width() // 6), max(1, sil.height() // 6), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    halo = small.scaled(sil.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(sil.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    painter = QPainter(out)
    painter.drawImage(0, 0, halo)
    painter.setOpacity(0.7)
    painter.drawImage(0, 0, halo)
    painter.end()
    return QPixmap.fromImage(out)


def glow_padding(width: int) -> int:
    return max(20, width // 3)
