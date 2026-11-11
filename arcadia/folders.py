"""Games that live in a folder rather than a single file.

PS3 game dumps and Wii U "loadiine" dumps are directories. A directory counts as a game
when it contains a marker file; that file is what gets passed to the emulator, and the
title is read from the folder's own metadata (the folder name alone is something like
"BLUS30443").
"""

from __future__ import annotations

import html
import re
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FolderRule:
    markers: tuple[str, ...]  # glob patterns relative to the game folder; the first file found is launched
    title_files: tuple[str, ...]  # files that may carry the game's title


FOLDER_RULES: dict[str, FolderRule] = {
    "ps3": FolderRule(
        markers=("PS3_GAME/USRDIR/EBOOT.BIN", "USRDIR/EBOOT.BIN"),
        title_files=("PS3_GAME/PARAM.SFO", "PARAM.SFO"),
    ),
    "wiiu": FolderRule(markers=("code/*.rpx",), title_files=("meta/meta.xml",)),
}


def parse_sfo_title(path: Path) -> str | None:
    """Read TITLE from a PARAM.SFO (the PlayStation metadata file)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:4] != b"\x00PSF" or len(data) < 20:
        return None
    key_table, data_table, count = struct.unpack_from("<III", data, 8)
    for i in range(min(count, 512)):
        base = 20 + i * 16
        if base + 16 > len(data):
            break
        key_offset, _fmt, length, _max_length, data_offset = struct.unpack_from("<HHIII", data, base)
        start = key_table + key_offset
        end = data.find(b"\x00", start)
        if end == -1 or data[start:end] != b"TITLE":
            continue
        raw = data[data_table + data_offset : data_table + data_offset + length]
        text = re.sub(r"\s+", " ", raw.split(b"\x00")[0].decode("utf-8", "replace")).strip()
        return text or None
    return None


def parse_meta_title(path: Path) -> str | None:
    """Read the English title from a Wii U meta.xml."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for tag in ("longname_en", "shortname_en"):
        match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
        if match:
            title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
            if title:
                return title
    return None


def _title_from(path: Path) -> str | None:
    if path.suffix.lower() == ".sfo":
        return parse_sfo_title(path)
    if path.suffix.lower() == ".xml":
        return parse_meta_title(path)
    return None


def find_game_folder(folder: Path, system_id: str) -> tuple[Path, str] | None:
    """If folder is a game for this system, return (file to launch, title); otherwise None."""
    rule = FOLDER_RULES.get(system_id)
    if rule is None or not folder.is_dir():
        return None
    for pattern in rule.markers:
        hits = sorted(p for p in folder.glob(pattern) if p.is_file())
        if hits:
            title = None
            for name in rule.title_files:
                title = _title_from(folder / name)
                if title:
                    break
            return hits[0], title or folder.name
    return None
