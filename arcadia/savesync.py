"""Keep saves in step between devices through a folder you choose (Syncthing, a cloud drive, an SD card).

Arcadia doesn't talk to any service: it just makes the chosen folder and your saves match, and
whatever syncs that folder does the rest. Each side of the sync is a labelled folder:

    saves     Arcadia's saves/ folder         (RetroArch's in-game saves, if you keep them there)
    states    Arcadia's states/ folder        (save-state snapshots)
    retroarch RetroArch Flatpak's own saves   (used while RetroArch saves aren't kept in Arcadia's folder)

The rules, in order of what matters most:

* Nothing is ever deleted. A file missing on one side is copied there.
* A file that changed on only one side since the last sync is copied to the other side.
* A file that changed on *both* sides is a conflict: the newer one wins, and the loser is kept in
  the sync folder's _conflicts/ (or, on this device, backups/savesync/) rather than thrown away.
* Whatever is about to be overwritten on this device is first copied to backups/savesync/<time>/.
* Copies are made to a temporary name and renamed, so a half-copied save never replaces a good one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from arcadia.config import Config
from arcadia.retroarch import RETROARCH_APP

SYNC_SUBDIR = "Arcadia"
RETROARCH_FLATPAK_SAVES = Path.home() / ".var" / "app" / RETROARCH_APP / "config" / "retroarch" / "saves"
IGNORED_SUFFIXES = (".tmp", ".part", ".arcadia-tmp")


class SyncError(Exception):
    """A message meant for the user."""


def sources(config: Config, retroarch_saves: Path = RETROARCH_FLATPAK_SAVES) -> dict[str, Path]:
    found = {"saves": config.saves_path, "states": config.savestate_path}
    if not config.ra_saves_in_home and retroarch_saves.is_dir():
        found["retroarch"] = retroarch_saves
    return found


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "_conflicts"]
        for name in names:
            path = Path(folder) / name
            if name.startswith(".") or name.endswith(IGNORED_SUFFIXES) or path.is_symlink():
                continue
            found[path.relative_to(root).as_posix()] = path
    return found


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".arcadia-tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@dataclass
class SyncReport:
    pushed: int = 0  # copied to the sync folder
    pulled: int = 0  # copied from it to this device
    conflicts: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)  # where conflict losers / overwritten files went

    @property
    def changed(self) -> int:
        return self.pushed + self.pulled


class Plan:
    """What a sync would do, worked out without touching anything."""

    def __init__(self):
        self.push: list[tuple[str, str]] = []
        self.pull: list[tuple[str, str]] = []
        self.conflict: list[tuple[str, str, str]] = []  # label, rel, winner ("local" / "remote")
        self.unchanged = 0


def _decide(local: str | None, remote: str | None, base: str | None) -> str:
    if local == remote:
        return "same"
    if remote is None:
        return "push"
    if local is None:
        return "pull"
    if local == base:
        return "pull"
    if remote == base:
        return "push"
    return "conflict"


def _state_path(config: Config) -> Path:
    return config.data_path / "savesync.json"


def _load_state(config: Config) -> dict:
    try:
        data = json.loads(_state_path(config).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(config: Config, state: dict) -> None:
    path = _state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def remote_root(config: Config) -> Path:
    base = config.sync_path
    if base is None:
        raise SyncError("Choose a sync folder first.")
    return base / SYNC_SUBDIR


def check_folder(config: Config) -> None:
    """Refuse a sync folder that would make a mess: one inside the folders being synced, or containing them."""
    base = config.sync_path
    if base is None:
        raise SyncError("Choose a sync folder first.")
    base = base.resolve()
    if base.exists() and not base.is_dir():
        raise SyncError("The sync folder isn't a folder.")
    for label, root in sources(config).items():
        root = root.resolve()
        if base == root or base.is_relative_to(root) or root.is_relative_to(base):
            raise SyncError(f"The sync folder can't be inside (or contain) your {label} folder. Pick a separate folder.")


def sync(
    config: Config,
    dry_run: bool = False,
    now: datetime | None = None,
    progress: Callable[[int, int], None] | None = None,
    retroarch_saves: Path = RETROARCH_FLATPAK_SAVES,
) -> SyncReport:
    check_folder(config)
    remote_base = remote_root(config)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    aside = config.backups_path / "savesync" / stamp
    state = _load_state(config)
    report = SyncReport()

    work: list[tuple[str, str, Path | None, Path | None, str]] = []  # label, rel, local, remote, verdict
    new_state: dict = {}
    for label, local_root in sources(config, retroarch_saves).items():
        remote_dir = remote_base / label
        local_files, remote_files = _files(local_root), _files(remote_dir)
        base_for = state.get(label, {}) if isinstance(state.get(label), dict) else {}
        new_state[label] = {}
        for rel in sorted(set(local_files) | set(remote_files)):
            lpath, rpath = local_files.get(rel), remote_files.get(rel)
            try:
                lh = _hash(lpath) if lpath else None
                rh = _hash(rpath) if rpath else None
            except OSError as exc:
                report.errors.append(f"{label}/{rel}: {exc.strerror or exc}")
                continue
            verdict = _decide(lh, rh, base_for.get(rel))
            if verdict == "same":
                report.unchanged += 1
                new_state[label][rel] = lh
                continue
            work.append((label, rel, lpath, rpath, verdict))
            new_state[label][rel] = base_for.get(rel)

    for n, (label, rel, lpath, rpath, verdict) in enumerate(work, 1):
        local_root = sources(config, retroarch_saves)[label]
        local_dest, remote_dest = local_root / rel, remote_base / label / rel
        try:
            if verdict == "conflict":
                report.conflicts += 1
                winner_local = lpath.stat().st_mtime >= rpath.stat().st_mtime  # ties go to this device
                verdict = "push" if winner_local else "pull"
                loser_copy = (remote_base / "_conflicts" / stamp / label / rel) if winner_local else (aside / label / rel)
                if not dry_run:
                    _copy(rpath if winner_local else lpath, loser_copy)
                report.kept.append(str(loser_copy))
            if verdict == "push":
                if not dry_run:
                    _copy(lpath, remote_dest)
                    new_state[label][rel] = _hash(lpath)
                report.pushed += 1
            else:
                if not dry_run:
                    if local_dest.exists():  # keep what's about to be replaced
                        _copy(local_dest, aside / label / rel)
                    _copy(rpath, local_dest)
                    new_state[label][rel] = _hash(local_dest)
                report.pulled += 1
        except OSError as exc:
            report.errors.append(f"{label}/{rel}: {exc.strerror or exc}")
        if progress:
            progress(n, len(work))
    if not dry_run:
        _save_state(config, new_state)
    return report


# ----------------------------------------------------------------------------
# Google Drive (or any cloud) through rclone
# ----------------------------------------------------------------------------
#
# rclone does the logging-in and the transfers; Arcadia never sees a password or token. A local mirror
# folder (data/sync-cache) stands in for the cloud folder: pull the cloud folder into it, run the
# ordinary sync against it, push it back. Both transfers are `rclone copy`, which never deletes.

_REMOTE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\- ]*:[^\x00\n]*$")


def valid_remote(remote: str) -> bool:
    return bool(_REMOTE.match(remote.strip()))


def cache_dir(config: Config) -> Path:
    return config.data_path / "sync-cache"


def rclone_remotes(run: Callable = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> list[tuple[str, str]]:
    """(remote name with colon, its type) for each remote rclone knows, e.g. ("gdrive:", "drive")."""
    if which("rclone") is None:
        raise SyncError("rclone isn't installed. Install it (see the README), then set up a Google Drive remote with `rclone config`.")
    try:
        result = run(["rclone", "listremotes", "--long"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SyncError(f"rclone couldn't be run: {exc}") from exc
    if result.returncode != 0:
        raise SyncError(f"rclone couldn't list its remotes: {(result.stderr or '').strip()[-200:]}")
    found = []
    for line in result.stdout.splitlines():
        name, _, kind = line.partition(":")
        if name.strip():
            found.append((name.strip() + ":", kind.strip()))
    return found


def _rclone_copy(src: str, dest: str, run: Callable, timeout: int = 1800) -> None:
    try:
        result = run(["rclone", "copy", "--", src, dest], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SyncError(f"rclone couldn't be run: {exc}") from exc
    if result.returncode != 0:
        raise SyncError(f"rclone failed: {((result.stderr or '') + (result.stdout or '')).strip()[-300:] or 'unknown error'}")


def sync_remote(
    config: Config,
    dry_run: bool = False,
    now: datetime | None = None,
    progress: Callable[[int, int], None] | None = None,
    retroarch_saves: Path = RETROARCH_FLATPAK_SAVES,
    run: Callable = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> SyncReport:
    remote = config.sync_remote.strip()
    if not remote:
        raise SyncError("Choose a remote first.")
    if not valid_remote(remote):
        raise SyncError("The remote should look like  name:folder  (for example gdrive:Arcadia).")
    if which("rclone") is None:
        raise SyncError("rclone isn't installed. Install it (see the README), then set up a Google Drive remote with `rclone config`.")
    cache = cache_dir(config)
    cache.mkdir(parents=True, exist_ok=True)
    mirror = replace(config, sync_dir=str(cache))
    _rclone_copy(remote.rstrip("/") + "/" + SYNC_SUBDIR, str(cache / SYNC_SUBDIR), run)  # pull what other devices left
    report = sync(mirror, dry_run, now, progress, retroarch_saves)
    if not dry_run:
        _rclone_copy(str(cache / SYNC_SUBDIR), remote.rstrip("/") + "/" + SYNC_SUBDIR, run)  # share what changed here
    return report


def run_sync(config: Config, dry_run: bool = False, **kw) -> SyncReport:
    """Sync with whichever target is set: an rclone remote, else the chosen folder."""
    progress = kw.get("progress")
    if config.sync_remote.strip():
        return sync_remote(config, dry_run, progress=progress, **{k: v for k, v in kw.items() if k != "progress"})
    return sync(config, dry_run, progress=progress, **{k: v for k, v in kw.items() if k in ("now", "retroarch_saves")})
