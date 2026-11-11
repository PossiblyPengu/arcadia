"""Find ROM files on disk and turn their names into readable titles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from arcadia.config import SystemConfig

_TAG = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_ARTICLE = re.compile(r"^(.*), (The|A|An)$")


@dataclass(frozen=True)
class Game:
    system_id: str
    path: Path
    title: str

    @property
    def key(self) -> str:
        return str(self.path)


def clean_title(stem: str) -> str:
    """'Legend of Zelda, The (USA) [!]' -> 'The Legend of Zelda'."""
    title = _TAG.sub("", stem).strip()
    match = _ARTICLE.match(title)
    if match:
        title = f"{match.group(2)} {match.group(1)}"
    title = re.sub(r"\s+", " ", title).strip()
    return title or stem


def scan_system(rom_root: Path, system: SystemConfig) -> list[Game]:
    folder = rom_root / system.folder
    if not folder.is_dir():
        return []
    extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in system.extensions}
    games = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in extensions:
            games.append(Game(system_id=system.id, path=path, title=clean_title(path.stem)))
    return games
