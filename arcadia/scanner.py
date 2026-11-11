"""Find ROM files on disk and turn their names into readable titles.

Games made of several files are linked together:
* an .m3u playlist is the game, and the disc files it lists are its children;
* a Switch base game owns the updates and DLC whose title IDs belong to it;
* for PS3 and Wii U, a whole folder is one game (see folders.py).
Children are stored (so they can be shown and passed to the emulator) but hidden from the library.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from arcadia.bundles import SWITCH_EXTS, parse_switch, read_m3u
from arcadia.config import SystemConfig
from arcadia.folders import FOLDER_RULES, find_game_folder

_TAG = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_ARTICLE = re.compile(r"^(.*), (The|A|An)$")

# Playlists are always launchable, whatever a system's extension list says.
ALWAYS_ACCEPTED = {".m3u"}


@dataclass(frozen=True)
class Game:
    system_id: str
    path: Path
    title: str
    parent_key: str | None = None  # set for files that belong to another game
    kind: str = "game"  # game | disc | update | dlc

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


def _link_playlists(games: dict[Path, Game]) -> None:
    """The discs an .m3u lists become children of the playlist."""
    claimed: set[Path] = set()
    for playlist in sorted(p for p in games if p.suffix.lower() == ".m3u"):
        for entry in read_m3u(playlist):
            if entry == playlist or entry in claimed or entry not in games:
                continue
            if games[entry].parent_key is None and entry.suffix.lower() != ".m3u":
                games[entry] = replace(games[entry], parent_key=games[playlist].key, kind="disc")
                claimed.add(entry)


def _link_switch_bundles(games: dict[Path, Game]) -> None:
    """Attach updates and DLC to the base game that shares their title ID block."""
    groups: dict[int, dict[str, list[Path]]] = {}
    for path in games:
        if path.suffix.lower() not in SWITCH_EXTS:
            continue
        info = parse_switch(path.name)
        if info is not None:
            groups.setdefault(info.group, {"base": [], "update": [], "dlc": []})[info.role].append(path)
    for roles in groups.values():
        bases = sorted(roles["base"])
        for role in ("update", "dlc"):
            for path in sorted(roles[role]):
                if bases:
                    games[path] = replace(games[path], parent_key=games[bases[0]].key, kind=role)
                else:  # no base game here: show it on its own, labelled so it isn't mistaken for a game
                    label = "update" if role == "update" else "DLC"
                    games[path] = replace(games[path], title=f"{games[path].title} ({label})", kind=role)


def scan_system(rom_root: Path, system: SystemConfig) -> list[Game]:
    folder = rom_root / system.folder
    if not folder.is_dir():
        return []
    extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in system.extensions} | ALWAYS_ACCEPTED
    games: dict[Path, Game] = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        here = Path(dirpath)
        if system.id in FOLDER_RULES and here != folder:
            hit = find_game_folder(here, system.id)
            if hit is not None:  # the whole folder is one game: don't look inside it
                launch, title = hit
                games[launch] = Game(system_id=system.id, path=launch, title=title)
                dirnames.clear()
                continue
        for name in sorted(filenames):
            path = here / name
            if not name.startswith(".") and path.suffix.lower() in extensions:
                games[path] = Game(system_id=system.id, path=path, title=clean_title(path.stem))
    _link_playlists(games)
    _link_switch_bundles(games)
    return list(games.values())
