"""Is each system actually ready to play? Checks only things that can really be checked:
whether an emulator is installed in Arcadia's folder, whether its Flatpak is installed,
whether the RetroArch core file a command names exists, and whether a plain command resolves.

It never guesses about things it can't see, such as BIOS files an emulator wants in its own
folders: those are listed in the README, not reported here as found or missing.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from arcadia.config import Config, SystemConfig
from arcadia.emulators import CATALOG, Installer

OK, PROBLEM, NONE = "ok", "problem", "none"


@dataclass(frozen=True)
class LauncherStatus:
    state: str  # "ok" | "problem" | "none"
    summary: str  # short text for a table cell
    detail: str = ""  # what to do about it


@dataclass(frozen=True)
class SystemRow:
    system: SystemConfig
    games: int
    launcher: LauncherStatus


_FLATPAK_RUN = re.compile(r"^\s*flatpak\s+run\s+(?:--\S+\s+)*([A-Za-z0-9_][A-Za-z0-9_.\-]*)")
_CORE_ARG = re.compile(r"(?:^|\s)-L\s+(\S+)")


def flatpak_app(command: str) -> str | None:
    """The app ID in 'flatpak run <id> ...', or None if this isn't a Flatpak command."""
    match = _FLATPAK_RUN.match(command)
    return match.group(1) if match else None


def core_path(command: str) -> Path | None:
    """The RetroArch core file named by '-L <path>', if there is one."""
    match = _CORE_ARG.search(command)
    return Path(os.path.expanduser(match.group(1))) if match else None


def flatpak_installed(
    app_id: str,
    run: Callable = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> bool | None:
    """True/False if flatpak can say whether the app is installed, None if flatpak isn't available."""
    if which("flatpak") is None:
        return None
    try:
        result = run(["flatpak", "info", app_id], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def check_launcher(
    system: SystemConfig,
    config: Config,
    installer: Installer | None = None,
    flatpak_check: Callable[[str], bool | None] = flatpak_installed,
    which: Callable[[str], str | None] = shutil.which,
) -> LauncherStatus:
    """What will happen when a game in this system is launched, and whether it can work."""
    installer = installer or Installer(config.emulators_path)
    spec = CATALOG.get(system.emulator) if system.emulator else None
    installed = installer.get(spec.id) if spec else None
    if spec is not None and installed is not None:
        return LauncherStatus(OK, f"{spec.name} {installed.version}", "Installed in Arcadia's folder.")

    command = system.command.strip()
    if not command:
        if spec is not None:
            return LauncherStatus(PROBLEM, "Not set up", f"Install {spec.name} from File → Emulators…")
        return LauncherStatus(NONE, "No launch command", "Set one in Settings.")

    here = f" Or install {spec.name} in Arcadia's folder (File → Emulators…)." if spec else ""
    app = flatpak_app(command)
    if app:
        present = flatpak_check(app)
        if present is None:
            return LauncherStatus(PROBLEM, "Flatpak isn't available", "Install Flatpak, or set a different launch command." + here)
        if not present:
            return LauncherStatus(PROBLEM, f"{app} not installed", f"flatpak install flathub {app}.{here}")
        core = core_path(command)
        if core is not None and not core.is_file():
            return LauncherStatus(
                PROBLEM,
                f"Core missing: {core.name}",
                f"Open RetroArch → Online Updater → Core Downloader and download {core.name}.",
            )
        return LauncherStatus(OK, f"{app} (Flatpak)", "")

    try:
        program = shlex.split(command)[0]
    except (ValueError, IndexError):
        return LauncherStatus(PROBLEM, "Launch command can't be read", "Check it in Settings.")
    program = os.path.expanduser(program)
    if which(program) or (os.path.isabs(program) and os.path.isfile(program)):
        return LauncherStatus(OK, os.path.basename(program), "")
    return LauncherStatus(PROBLEM, f"{os.path.basename(program)} not found", "Check the launch command in Settings.")


def status_rows(
    config: Config,
    game_counts: dict[str, int],
    installer: Installer | None = None,
    flatpak_check: Callable[[str], bool | None] = flatpak_installed,
    which: Callable[[str], str | None] = shutil.which,
    only_with_games: bool = True,
) -> list[SystemRow]:
    """One row per system. By default only systems that have games or an installed emulator, since a
    checklist of thirty-odd systems you don't use is noise. Each Flatpak is asked about only once."""
    installer = installer or Installer(config.emulators_path)
    cache: dict[str, bool | None] = {}

    def cached(app_id: str) -> bool | None:
        if app_id not in cache:
            cache[app_id] = flatpak_check(app_id)
        return cache[app_id]

    rows = []
    for system in config.systems:
        games = game_counts.get(system.id, 0)
        has_local = bool(system.emulator) and installer.get(system.emulator) is not None
        if only_with_games and not games and not has_local:
            continue
        rows.append(SystemRow(system, games, check_launcher(system, config, installer, cached, which)))
    return rows


def tree_size(path: Path) -> int:
    """Total bytes of the files under a folder (links are not followed). 0 if it doesn't exist."""
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except (NotADirectoryError, FileNotFoundError, PermissionError):
            continue
    return total


def folder_sizes(config: Config) -> dict[str, int]:
    """How much space each part of the setup takes."""
    return {
        "ROMs": tree_size(config.rom_root_path),
        "Emulators": tree_size(config.emulators_path),
        "Save states": tree_size(config.savestate_path),
        "Covers and metadata": tree_size(config.media_path),
        "Backups": tree_size(config.backups_path),
    }
