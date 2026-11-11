"""The "Get started" checklist: what a new setup still needs, worked out from the real state of things.

Nothing here changes anything. `gather` looks (it may run `flatpak list` and `rclone listremotes`, so it
belongs in a background task) and `build_steps` turns what it saw into plain steps for the window.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from arcadia import bios, savesync
from arcadia.config import Config
from arcadia.emulators import Installer
from arcadia.updates import flatpaks_in_use, installed_flatpaks


@dataclass(frozen=True)
class Facts:
    games: int
    local_emulators: int  # installed into Arcadia's folder
    flatpak_emulators: int  # installed Flatpaks that systems launch through
    systems_missing_bios: int  # among systems that have games
    rclone: bool
    remotes: tuple[str, ...]  # names rclone knows, with the colon ("gdrive:")


@dataclass(frozen=True)
class Step:
    key: str  # "folder" | "games" | "emulators" | "bios" | "sync"
    title: str
    detail: str
    done: bool
    button: str
    optional: bool = False


def gather(config: Config, counts: dict[str, int]) -> Facts:
    installer = Installer(config.emulators_path)
    local = len(installer.installed())
    flatpaks = installed_flatpaks()
    flat = len(flatpaks_in_use(config, flatpaks, installer)) if flatpaks else 0
    missing = sum(1 for row in bios.check_bios(config) if row.state == "missing" and counts.get(row.system_id, 0) > 0)
    remotes: tuple[str, ...] = ()
    have_rclone = shutil.which("rclone") is not None
    if have_rclone:
        try:
            remotes = tuple(name for name, _kind in savesync.rclone_remotes())
        except savesync.SyncError:
            remotes = ()
    return Facts(sum(counts.values()), local, flat, missing, have_rclone, remotes)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build_steps(config: Config, facts: Facts) -> list[Step]:
    home = config.home_path
    folder = Step(
        "folder",
        "Your Arcadia folder",
        f"Everything lives in {home}." if home else "Arcadia is using separate folders (the older layout).",
        True,
        "Open folder",
    )
    games = Step(
        "games",
        "Add your games",
        f"{_plural(facts.games, 'game')} in your library." if facts.games else "Bring in an existing ROM folder, or sort ROMs from your Downloads folder. Arcadia files each one under the right system and asks when it isn't sure.",
        facts.games > 0,
        "Add games…" if not facts.games else "Add more…",
    )
    ready = facts.local_emulators + facts.flatpak_emulators
    parts = []
    if facts.local_emulators:
        parts.append(f"{_plural(facts.local_emulators, 'emulator')} installed in Arcadia's folder")
    if facts.flatpak_emulators:
        parts.append(f"{_plural(facts.flatpak_emulators, 'Flatpak emulator')} ready")
    emulators = Step(
        "emulators",
        "Get your emulators",
        ", ".join(parts) + "." if parts else "No emulators are ready yet. Install the ones you need, in one click each.",
        ready > 0,
        "Emulators…",
    )
    if not facts.games:
        bios_step = Step("bios", "BIOS files", "Some systems need BIOS files from your own consoles. Check this once your games are in.", False, "BIOS files…", True)
    elif facts.systems_missing_bios:
        bios_step = Step("bios", "BIOS files", f"{_plural(facts.systems_missing_bios, 'system')} with games still need a BIOS file.", False, "BIOS files…", True)
    else:
        bios_step = Step("bios", "BIOS files", "Every system you have games for has what it needs.", True, "BIOS files…", True)
    remote = config.sync_remote.strip()
    wanted = remote.split(":", 1)[0] + ":" if ":" in remote else ""
    if not facts.rclone:
        detail, done = "Optional: install rclone to keep your saves backed up in Google Drive and in step between devices.", False
    elif wanted and wanted in facts.remotes:
        detail, done = f"Saves sync to {remote} by themselves when Arcadia starts and after each game.", True
    elif facts.remotes:
        detail, done = f"rclone is installed, but there's no remote called “{wanted[:-1]}”. Pick one of yours ({', '.join(facts.remotes)}).", False
    else:
        detail, done = "rclone is installed. Run `rclone config` once and add a Google Drive remote.", False
    sync = Step("sync", "Sync your saves", detail, done, "Save sync…", True)
    return [folder, games, emulators, bios_step, sync]


def required_done(steps: list[Step]) -> bool:
    return all(s.done for s in steps if not s.optional)
