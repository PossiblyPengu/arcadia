"""Save-state snapshots.

Emulators store saves and save states in their own folders, named after the
ROM (for example 'Game.srm' or 'Game.state1'). A snapshot copies every file in
the system's save folder whose name starts with the ROM's name followed by a dot,
into a timestamped folder under the Arcadia savestate directory. Restoring copies
them back, after first taking an automatic backup of the current files.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path


class SaveStateError(Exception):
    pass


def game_state_dir(state_root: Path, rom: Path) -> Path:
    digest = hashlib.sha1(str(rom).encode("utf-8")).hexdigest()[:16]
    return state_root / digest


def _game_files(save_dir: Path, rom: Path) -> list[Path]:
    if not save_dir.is_dir():
        return []
    prefix = rom.stem + "."
    return sorted(p for p in save_dir.iterdir() if p.is_file() and p.name.startswith(prefix))


def create_snapshot(save_dir: Path, rom: Path, state_root: Path, label: str = "") -> Path:
    files = _game_files(save_dir, rom)
    if not files:
        raise SaveStateError(f"No save files for '{rom.stem}' found in {save_dir}.")
    game_dir = game_state_dir(state_root, rom)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = game_dir / f"{stamp}{'-' + label if label else ''}"
    dest.mkdir(parents=True, exist_ok=False)
    (game_dir / "rom.txt").write_text(str(rom) + "\n", encoding="utf-8")
    for f in files:
        shutil.copy2(f, dest / f.name)
    return dest


def list_snapshots(state_root: Path, rom: Path) -> list[Path]:
    game_dir = game_state_dir(state_root, rom)
    if not game_dir.is_dir():
        return []
    return sorted((p for p in game_dir.iterdir() if p.is_dir()), reverse=True)


def restore_snapshot(snapshot: Path, save_dir: Path, rom: Path, state_root: Path) -> None:
    if not snapshot.is_dir():
        raise SaveStateError(f"Snapshot not found: {snapshot}")
    save_dir.mkdir(parents=True, exist_ok=True)
    # Back up whatever is there now, so a restore can always be undone.
    if _game_files(save_dir, rom):
        create_snapshot(save_dir, rom, state_root, label="auto-before-restore")
    for f in snapshot.iterdir():
        if f.is_file():
            shutil.copy2(f, save_dir / f.name)
