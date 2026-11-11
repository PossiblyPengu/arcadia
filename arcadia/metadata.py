"""Per-game metadata from optional sidecar files.

Layout under the media directory:
    <media>/<system_id>/<rom stem>.json    title, description, year, genre
    <media>/<system_id>/<rom stem>.png|jpg  cover art
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

COVER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass
class Metadata:
    title: str = ""
    description: str = ""
    year: str = ""
    genre: str = ""
    cover: Path | None = None


def load_metadata(media_dir: Path, system_id: str, rom: Path) -> Metadata:
    base = media_dir / system_id
    meta = Metadata()
    sidecar = base / f"{rom.stem}.json"
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            meta.title = str(data.get("title", ""))
            meta.description = str(data.get("description", ""))
            meta.year = str(data.get("year", ""))
            meta.genre = str(data.get("genre", ""))
    for ext in COVER_EXTENSIONS:
        candidate = base / f"{rom.stem}{ext}"
        if candidate.is_file():
            meta.cover = candidate
            break
    return meta
