"""Games made of several files: multi-disc sets and base games with updates / DLC.

Everything here works from file names and playlist text, so the scanner (what's in the
library) and the sorter (what's in the downloads folder) can share it.

Multi-disc games
    "Final Fantasy VII (USA) (Disc 1).cue", "... (Disc 2).cue" are grouped under one
    .m3u playlist, which is what emulators like RetroArch and DuckStation load.

Updates and DLC (Nintendo Switch)
    Title IDs encode the relationship, so files can be linked without opening them:
      base game  0100ABCD00012000   (low 12 bits 000)
      update     0100ABCD00012800   (base | 0x800: same ID block)
      DLC        0100ABCD00013xxx   (the next ID block up)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------
# Multi-disc names
# ----------------------------------------------------------------------------

_PAREN_DISC = re.compile(
    r"\s*[\(\[]\s*(?:disc|disk|cd)\s*([0-9]+|[a-d])(?:\s*(?:of|/)\s*([0-9]+))?\s*[\)\]]", re.IGNORECASE
)
_BARE_DISC = re.compile(r"(?<![a-z0-9])(?:disc|disk|cd)[ _.\-]?([0-9]+)(?![a-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class DiscInfo:
    base: str  # the title without its disc tag: "Final Fantasy VII (USA)"
    number: int  # 1-based
    total: int | None  # from "(Disc 1 of 3)", if the name says so


def parse_disc(stem: str) -> DiscInfo | None:
    """'Game (USA) (Disc 2).cue' -> DiscInfo('Game (USA)', 2, None). None if it isn't a disc tag."""
    match = _PAREN_DISC.search(stem)
    total = None
    if match:
        raw = match.group(1)
        number = int(raw) if raw.isdigit() else ord(raw.lower()) - ord("a") + 1  # (Disc A) -> 1
        total = int(match.group(2)) if match.group(2) else None
    else:
        match = _BARE_DISC.search(stem)
        if not match:
            return None
        number = int(match.group(1))
    if number < 1:
        return None
    base = re.sub(r"\s+", " ", stem[: match.start()] + stem[match.end() :]).strip(" -_.")
    if not base:
        return None
    return DiscInfo(base, number, total)


def read_m3u(path: Path) -> list[Path]:
    """Files an .m3u playlist lists (relative entries resolve against the playlist's folder)."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = Path(line)
        entries.append(entry if entry.is_absolute() else path.parent / entry)
    return entries


def write_m3u(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_m3u_lines(existing: list[str], new: list[str]) -> list[str]:
    """Combine playlist lines, ordering by disc number where the names have one.
    Entries without a disc number keep their place after the numbered ones."""
    seen: set[str] = set()
    lines = []
    for line in [*existing, *new]:
        if line not in seen:
            seen.add(line)
            lines.append(line)

    def order(item: tuple[int, str]) -> tuple[int, int]:
        index, line = item
        info = parse_disc(Path(line).stem)
        return (info.number if info else 10_000, index)

    return [line for _i, line in sorted(enumerate(lines), key=order)]


# ----------------------------------------------------------------------------
# Switch base games, updates and DLC
# ----------------------------------------------------------------------------

SWITCH_EXTS = {".nsp", ".xci", ".nsz", ".xcz"}

_TITLE_ID = re.compile(r"\[(01[0-9a-fA-F]{14})\]")
_VERSION = re.compile(r"\[v(\d+)\]|\(v([0-9][0-9.]*)\)", re.IGNORECASE)


@dataclass(frozen=True)
class SwitchInfo:
    title_id: str  # 16 hex digits, upper case
    role: str  # "base" | "update" | "dlc"
    group: int  # same for a base game and all of its updates and DLC
    version: str  # "v65536", "v1.2.0", or ""


def parse_switch(name: str) -> SwitchInfo | None:
    """Read the title ID (and version) out of a file name like 'Game [0100ABCD00012000][v0].nsp'."""
    match = _TITLE_ID.search(name)
    if not match:
        return None
    title_id = match.group(1).upper()
    value = int(title_id, 16)
    low = value & 0xFFF
    if low == 0x000:
        role, group = "base", value >> 12
    elif low == 0x800:
        role, group = "update", value >> 12
    else:
        role, group = "dlc", (value >> 12) - 1
    version = ""
    found = _VERSION.search(name)
    if found:
        version = f"v{found.group(1) or found.group(2)}"
    return SwitchInfo(title_id, role, group, version)
