"""Back up and restore the things that can't be re-downloaded: saves, settings, and the library.

What goes in a backup (one zip file):
    config.json                    Arcadia's settings
    data/library.db, imports.json  favorites, playtime, and the import undo journal
    states/                        save-state snapshots
    saves/                         in-game saves Arcadia keeps (RetroArch's, if enabled)
    media/                         covers and metadata (only if asked: it can be large)
    emulators/<id>/{config,data,state}/   each installed emulator's own settings and saves

What does not: ROMs, the emulators' programs (they can be installed again), their caches, and
anything a Flatpak emulator keeps under ~/.var/app, which Arcadia doesn't manage.

A restore is deliberately narrow. Only the paths above are accepted, so a backup file can put
saves and settings back and nothing else (never a program inside an emulator's app/ folder). It
unpacks into a staging folder first, moves whatever it replaces to backups/before-restore-<time>/
rather than deleting it, and puts everything back if it fails part way.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from arcadia import __version__
from arcadia.config import Config

MANIFEST = "manifest.json"
FORMAT = 1
EMULATOR_DATA = ("config", "data", "state")  # not "app" (the program) and not "cache"
_EMULATOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_TOP = {"config.json", "data", "states", "saves", "media", "emulators"}
_DATA_FILES = {"library.db", "imports.json"}


class BackupError(Exception):
    """A message meant for the user."""


@dataclass
class BackupResult:
    path: Path
    files: int
    bytes: int
    emulators: list[str] = field(default_factory=list)


@dataclass
class BackupInfo:
    created: str
    files: int
    bytes: int
    includes_media: bool
    emulators: list[str]
    areas: dict[str, int]  # files per area ("settings", "library", "save states", "covers", "emulators")
    arcadia_version: str = ""


@dataclass
class RestoreResult:
    files: int
    replaced_to: Path | None  # where what was replaced was put aside, if anything was
    areas: list[str]


# ----------------------------------------------------------------------------
# Making a backup
# ----------------------------------------------------------------------------

def _files_under(root: Path) -> Iterator[Path]:
    """Regular files under a folder, in a stable order, never following links."""
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_file() and not path.is_symlink():
                yield path


def _snapshot_database(db: Path, dest: Path) -> None:
    """A consistent copy of the library database, even while Arcadia has it open."""
    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _items(config: Config, config_path: Path, include_media: bool, tmp: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    items: list[tuple[Path, str]] = []
    if config_path.is_file():
        items.append((config_path, "config.json"))
    if config.db_path.is_file():
        snapshot = tmp / "library.db"
        try:
            _snapshot_database(config.db_path, snapshot)
            items.append((snapshot, "data/library.db"))
        except sqlite3.Error as exc:
            raise BackupError(f"couldn't read the library database: {exc}") from exc
    if config.journal_path.is_file():
        items.append((config.journal_path, "data/imports.json"))
    for f in _files_under(config.savestate_path):
        items.append((f, f"states/{f.relative_to(config.savestate_path).as_posix()}"))
    for f in _files_under(config.saves_path):
        items.append((f, f"saves/{f.relative_to(config.saves_path).as_posix()}"))
    if include_media:
        for f in _files_under(config.media_path):
            items.append((f, f"media/{f.relative_to(config.media_path).as_posix()}"))
    emulators: list[str] = []
    if config.emulators_path.is_dir():
        for folder in sorted(p for p in config.emulators_path.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if not _EMULATOR_ID.match(folder.name):
                continue
            before = len(items)
            for sub in EMULATOR_DATA:
                for f in _files_under(folder / sub):
                    items.append((f, f"emulators/{folder.name}/{sub}/{f.relative_to(folder / sub).as_posix()}"))
            if len(items) > before:
                emulators.append(folder.name)
    return items, emulators


def create_backup(
    config: Config,
    config_path: Path,
    dest_dir: Path | None = None,
    include_media: bool = False,
    progress: Callable[[int, int], None] | None = None,
    now: datetime | None = None,
) -> BackupResult:
    dest_dir = dest_dir or config.backups_path
    now = now or datetime.now(timezone.utc)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arcadia-backup-") as tmp_name:
        items, emulators = _items(config, config_path, include_media, Path(tmp_name))
        if not items:
            raise BackupError("there's nothing to back up yet: no saves, settings or library data")
        total_bytes = sum(p.stat().st_size for p, _ in items)
        manifest = {
            "arcadia_backup": FORMAT,
            "arcadia_version": __version__,
            "created": now.isoformat(timespec="seconds"),
            "includes_media": include_media,
            "emulators": emulators,
            "files": len(items),
            "bytes": total_bytes,
        }
        stamp = now.astimezone().strftime("%Y%m%d-%H%M%S")
        final = dest_dir / f"Arcadia-backup-{stamp}.zip"
        n = 2
        while final.exists():
            final = dest_dir / f"Arcadia-backup-{stamp}-{n}.zip"
            n += 1
        partial = final.with_name(final.name + ".part")
        try:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
                for i, (path, arcname) in enumerate(items, 1):
                    zf.write(path, arcname)
                    if progress:
                        progress(i, len(items))
            os.replace(partial, final)
        except (OSError, zipfile.BadZipFile) as exc:
            partial.unlink(missing_ok=True)
            raise BackupError(f"the backup couldn't be written: {getattr(exc, 'strerror', None) or exc}") from exc
    return BackupResult(final, len(items), total_bytes, emulators)


# ----------------------------------------------------------------------------
# Reading and restoring
# ----------------------------------------------------------------------------

def _checked(name: str) -> PurePosixPath:
    """A member's path, accepted only if it is one a backup is allowed to hold."""
    path = PurePosixPath(name.replace("\\", "/"))
    parts = path.parts
    if not parts or path.is_absolute() or ".." in parts or "" in parts:
        raise BackupError(f"the backup contains an unsafe path ({name})")
    top = parts[0]
    if name == MANIFEST:
        return path
    ok = False
    if top == "config.json":
        ok = len(parts) == 1
    elif top == "data":
        ok = len(parts) == 2 and parts[1] in _DATA_FILES
    elif top in ("states", "saves", "media"):
        ok = len(parts) >= 2
    elif top == "emulators":
        ok = len(parts) >= 4 and bool(_EMULATOR_ID.match(parts[1])) and parts[2] in EMULATOR_DATA
    if not ok:
        raise BackupError(f"the backup contains something Arcadia doesn't restore ({name})")
    return path


def inspect_backup(zip_path: Path) -> BackupInfo:
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("that isn't a backup file Arcadia can read") from exc
    with zf:
        try:
            manifest = json.loads(zf.read(MANIFEST))
        except (KeyError, ValueError):
            raise BackupError("that zip isn't an Arcadia backup (it has no manifest)") from None
        if not isinstance(manifest, dict) or manifest.get("arcadia_backup") != FORMAT:
            raise BackupError("that backup was made by a version of Arcadia this one can't read")
        areas = {"settings": 0, "library": 0, "save states": 0, "saves": 0, "covers": 0, "emulators": 0}
        names = {"config.json": "settings", "data": "library", "states": "save states", "saves": "saves", "media": "covers", "emulators": "emulators"}
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = _checked(info.filename).parts
            if info.filename != MANIFEST:
                areas[names[parts[0]]] += 1
        return BackupInfo(
            created=str(manifest.get("created", "")),
            files=int(manifest.get("files", 0)),
            bytes=int(manifest.get("bytes", 0)),
            includes_media=bool(manifest.get("includes_media")),
            emulators=[str(e) for e in manifest.get("emulators", []) if _EMULATOR_ID.match(str(e))],
            areas=areas,
            arcadia_version=str(manifest.get("arcadia_version", "")),
        )


def _targets(config: Config, config_path: Path, staging: Path) -> list[tuple[Path, Path, str]]:
    """(unpacked piece, where it lives now, a name for it) for each piece present in the backup."""
    pairs: list[tuple[Path, Path, str]] = []
    if (staging / "config.json").is_file():
        pairs.append((staging / "config.json", config_path, "config.json"))
    for name, live in (("library.db", config.db_path), ("imports.json", config.journal_path)):
        if (staging / "data" / name).is_file():
            pairs.append((staging / "data" / name, live, f"data/{name}"))
    for top, live in (("states", config.savestate_path), ("saves", config.saves_path), ("media", config.media_path)):
        if (staging / top).is_dir():
            pairs.append((staging / top, live, top))
    emulators = staging / "emulators"
    if emulators.is_dir():
        for folder in sorted(p for p in emulators.iterdir() if p.is_dir()):
            for sub in EMULATOR_DATA:
                if (folder / sub).is_dir():
                    pairs.append((folder / sub, config.emulators_path / folder.name / sub, f"emulators/{folder.name}/{sub}"))
    return pairs


def restore_backup(
    config: Config,
    config_path: Path,
    zip_path: Path,
    progress: Callable[[int, int], None] | None = None,
    now: datetime | None = None,
) -> RestoreResult:
    info = inspect_backup(zip_path)  # also rejects anything that isn't allowed in a backup
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    config.backups_path.mkdir(parents=True, exist_ok=True)
    staging = config.backups_path / f".restore-{stamp}"
    aside = config.backups_path / f"before-restore-{stamp}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    swapped: list[tuple[Path, Path | None]] = []  # (live path now holding restored data, where the old one went)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                raise BackupError("the backup file is damaged, so nothing was restored")
            members = [i for i in zf.infolist() if not i.is_dir() and i.filename != MANIFEST]
            for n, member in enumerate(members, 1):
                target = staging.joinpath(*_checked(member.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                if progress:
                    progress(n, len(members))

        pairs = _targets(config, config_path, staging)
        for piece, live, name in pairs:
            put_aside: Path | None = None
            if live.exists():
                put_aside = aside / name
                put_aside.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(live), str(put_aside))
            swapped.append((live, put_aside))
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(piece), str(live))
    except BaseException as exc:
        for live, put_aside in reversed(swapped):  # put everything back as it was
            try:
                if live.is_dir():
                    shutil.rmtree(live)
                elif live.exists():
                    live.unlink()
                if put_aside is not None and put_aside.exists():
                    shutil.move(str(put_aside), str(live))
            except OSError:
                pass
        if isinstance(exc, BackupError):
            raise
        if isinstance(exc, (OSError, zipfile.BadZipFile)):
            raise BackupError(f"the restore failed and was undone: {getattr(exc, 'strerror', None) or exc}") from exc
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return RestoreResult(
        files=sum(info.areas.values()),
        replaced_to=aside if aside.exists() else None,
        areas=[area for area, count in info.areas.items() if count],
    )
