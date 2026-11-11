"""Bring an existing library into the Arcadia folder.

A ROM folder is a set of per-system subfolders (nes/, psx/, "Game Boy Advance"/, ...). Arcadia
matches each subfolder to a system by name, shows what it would do, and then moves (or copies)
what's inside into <Arcadia folder>/roms/<system>/.

Rules it keeps:
* Nothing is ever overwritten. A file or folder already in the destination is skipped.
* Moves are verified (across drives the copy is checked before the original is removed) and are
  recorded, so File > Undo last import puts them back. Copies leave the originals untouched.
* Subfolders it doesn't recognise are listed and left alone unless the user assigns a system.
* The library database, covers and save-state snapshots are copied, never deleted from where
  they were, so the old setup still works until the user is happy.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from arcadia.config import Config
from arcadia.sorter import Journal, Move, SortError, _tree_stats, safe_move

# Folder names other front ends and set-ups use, per system (matched ignoring case and punctuation).
ALIASES: dict[str, tuple[str, ...]] = {
    "nes": ("famicom", "nintendoentertainmentsystem", "fds"),
    "snes": ("superfamicom", "supernintendo", "sfc", "snesna"),
    "n64": ("nintendo64",),
    "gc": ("gamecube", "ngc", "nintendogamecube"),
    "wii": ("nintendowii",),
    "wiiu": ("nintendowiiu",),
    "switch": ("nsw", "nintendoswitch"),
    "gb": ("gameboy",),
    "gbc": ("gameboycolor",),
    "gba": ("gameboyadvance",),
    "nds": ("ds", "nintendods"),
    "n3ds": ("3ds", "nintendo3ds"),
    "genesis": ("megadrive", "md", "segagenesis", "segamegadrive", "genesiswide", "megadrivejapan"),
    "sms": ("mastersystem", "segamastersystem"),
    "gamegear": ("gg", "segagamegear"),
    "segacd": ("megacd", "scd", "segamegacd"),
    "saturn": ("segasaturn",),
    "dreamcast": ("dc", "segadreamcast"),
    "psx": ("ps1", "playstation", "psone", "playstation1", "sonyplaystation"),
    "ps2": ("playstation2", "sonyplaystation2"),
    "ps3": ("playstation3", "sonyplaystation3"),
    "psp": ("playstationportable", "sonypsp"),
    "xbox": ("microsoftxbox", "originalxbox"),
    "pcengine": ("tg16", "turbografx16", "turbografx", "pce", "pcenginecd", "tg16cd"),
    "neogeo": ("neogeoaes", "neogeomvs"),
    "arcade": ("mame", "mamelibretro", "fba", "fbneo", "fbalpha", "mame2003", "mame2010"),
    "atari2600": ("atari26", "a2600"),
    "atari7800": ("atari78", "a7800"),
    "lynx": ("atarilynx",),
    "wonderswan": ("ws", "wswan", "wswanc", "wonderswancolor"),
    "ngp": ("neogeopocket", "ngpc", "neogeopocketcolor"),
    "virtualboy": ("vb", "nintendovirtualboy"),
    "msx": ("msx1", "msx2", "msx2plus"),
    "amiga": ("amiga500", "amiga1200", "amigacd32", "commodoreamiga"),
}


class ConsolidateError(Exception):
    """A message meant for the user."""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def match_system(folder_name: str, config: Config) -> str | None:
    """Which system a folder is for, going by its name. None if no system fits or two compete."""
    wanted = _norm(folder_name)
    if not wanted:
        return None
    found: set[str] = set()
    for system in config.systems:
        names = {_norm(system.folder), _norm(system.id), _norm(system.name), *ALIASES.get(system.id, ())}
        if wanted in names:
            found.add(system.id)
    return next(iter(found)) if len(found) == 1 else None


@dataclass
class SourceFolder:
    path: Path
    system_id: str | None  # the guess; the user may change it
    files: int
    bytes: int
    entries: int  # items directly inside, which is what gets moved


def _inside(inner: Path, outer: Path) -> bool:
    inner, outer = inner.resolve(), outer.resolve()
    return inner == outer or outer in inner.parents


def scan_source(source: Path, config: Config, dest_root: Path) -> list[SourceFolder]:
    """The subfolders of an existing ROM folder, each matched to a system where its name allows."""
    if not source.is_dir():
        raise ConsolidateError("that folder doesn't exist")
    if source.resolve() == dest_root.resolve():
        raise ConsolidateError("that's already the ROM folder inside the Arcadia folder")
    found = []
    for sub in sorted((p for p in source.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.name.lower()):
        if _inside(dest_root, sub) or _inside(sub, dest_root):
            continue  # the new ROM folder itself, or something that contains it: never move it into itself
        files = size = 0
        for _dirpath, _dirnames, names in os.walk(sub):
            for name in names:
                files += 1
                try:
                    size += os.path.getsize(os.path.join(_dirpath, name))
                except OSError:
                    pass
        entries = sum(1 for c in sub.iterdir() if not c.name.startswith("."))
        found.append(SourceFolder(sub, match_system(sub.name, config), files, size, entries))
    return found


@dataclass
class BringInResult:
    moved: int = 0
    copied: int = 0
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    bytes: int = 0


def _copy_verified(src: Path, dst: Path) -> None:
    """Copy a file or folder next to its destination, check it, then put it in place. The source stays."""
    partial = dst.with_name(dst.name + ".arcadia-part")
    try:
        if src.is_dir():
            shutil.copytree(src, partial, symlinks=True)
            if _tree_stats(partial) != _tree_stats(src):
                raise SortError(f"copy of {src.name} was incomplete")
        else:
            shutil.copy2(src, partial)
            if partial.stat().st_size != src.stat().st_size:
                raise SortError(f"copy of {src.name} was incomplete")
        os.replace(partial, dst)
    except (OSError, shutil.Error) as exc:
        _discard(partial)
        raise SortError(f"could not copy {src.name}: {getattr(exc, 'strerror', None) or exc}") from exc
    except SortError:
        _discard(partial)
        raise


def _discard(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def bring_in(
    chosen: list[tuple[SourceFolder, str | None]],
    config: Config,
    dest_root: Path,
    mode: str,
    journal: Journal,
    progress: Callable[[int, int, str], None] | None = None,
) -> BringInResult:
    """Move or copy what's inside each chosen folder into dest_root/<system folder>/.
    chosen pairs each folder with the system it was assigned (None = leave it alone)."""
    if mode not in ("move", "copy"):
        raise ConsolidateError("mode must be 'move' or 'copy'")
    work = []
    refused: list[tuple[Path, str]] = []
    for folder, system_id in chosen:
        if system_id is None:
            continue
        if _inside(dest_root, folder.path) or _inside(folder.path, dest_root):
            # Moving it would put the Arcadia folder's own contents inside the ROM folder. This is
            # checked here as well as when scanning, so a caller can't get this wrong.
            refused.append((folder.path, "it contains, or is inside, the Arcadia ROM folder"))
            continue
        dest_dir = dest_root / config.system(system_id).folder
        children = sorted(c for c in folder.path.iterdir() if not c.name.startswith("."))
        work.extend((child, dest_dir) for child in children)

    result = BringInResult(skipped=list(refused))
    moves: list[Move] = []
    for done, (child, dest_dir) in enumerate(work, 1):
        if progress:
            progress(done, len(work), child.name)
        target = dest_dir / child.name
        if _inside(dest_dir, child):
            result.skipped.append((child, "the destination is inside it"))
            continue
        if target.exists():
            result.skipped.append((child, "already exists in the Arcadia folder"))
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            size = _tree_stats(child)[1] if child.is_dir() else child.stat().st_size
            if mode == "move":
                safe_move(child, target)
                moves.append(Move(str(child), str(target)))
                result.moved += 1
            else:
                _copy_verified(child, target)
                result.copied += 1
            result.bytes += size
        except (SortError, OSError) as exc:
            result.skipped.append((child, str(exc)))
    journal.record(moves)  # only moves can be undone; copies leave the originals where they were
    return result


# ----------------------------------------------------------------------------
# Library data: favorites, playtime, covers, save-state snapshots
# ----------------------------------------------------------------------------

def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(f.is_file() for f in path.rglob("*"))


def migrate_data(config: Config, home: Path) -> list[str]:
    """Copy the library database, import journal, covers and save-state snapshots into the Arcadia
    folder. The originals stay where they are. Returns what was done, in plain words."""
    notes: list[str] = []
    new = Config.new_install(home)  # where the same things live inside the new folder

    new.data_path.mkdir(parents=True, exist_ok=True)
    if config.db_path.is_file() and not _same(config.db_path, new.db_path):
        if new.db_path.exists():
            notes.append("Left the library database alone: the Arcadia folder already has one.")
        else:
            source = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
            try:
                target = sqlite3.connect(str(new.db_path))
                try:
                    source.backup(target)  # consistent even while Arcadia has it open
                finally:
                    target.close()
            finally:
                source.close()
            notes.append("Copied your library: favorites, play counts and playtime.")
    if config.journal_path.is_file() and not _same(config.journal_path, new.journal_path) and not new.journal_path.exists():
        shutil.copy2(config.journal_path, new.journal_path)

    for label, old, fresh in (
        ("covers and metadata", config.media_path, new.media_path),
        ("save-state snapshots", config.savestate_path, new.savestate_path),
    ):
        if not _has_files(old) or _same(old, fresh):
            continue
        if _has_files(fresh):
            notes.append(f"Left the {label} alone: the Arcadia folder already has some.")
            continue
        if fresh.exists() and not any(fresh.iterdir()):
            fresh.rmdir()  # an empty folder from the layout: the copy takes its place
        fresh.parent.mkdir(parents=True, exist_ok=True)
        _copy_verified(old, fresh)
        notes.append(f"Copied your {label}.")
    return notes


def adopt_home(config: Config, home: Path, roms: bool, data: bool) -> None:
    """Point the configuration at the Arcadia folder. roms/data say which parts were brought in,
    so a part that wasn't keeps pointing where it did."""
    config.home_dir = str(home)
    if roms:
        config.rom_root = ""
    if data:
        config.data_dir = ""
        config.media_dir = ""
        config.savestate_dir = ""
