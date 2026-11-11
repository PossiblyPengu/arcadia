"""RetroArch: settings Arcadia applies when it launches it, and downloading/updating its cores.

Settings go in a small file that is passed with RetroArch's own `--appendconfig` option. It is read
on top of the user's retroarch.cfg and never edits it, so removing Arcadia's settings is just a
matter of turning "Manage RetroArch" off. The keys used (system_directory, savefile_directory,
video_fullscreen, video_vsync, video_scale_integer, savestate_auto_save, savestate_auto_load) are
ordinary retroarch.cfg keys.

Cores come from libretro's build server, the same place RetroArch's own Core Downloader uses. A
core is a single .so file inside a zip; only that one file, named exactly as expected, is extracted.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from arcadia.config import Config
from arcadia.emulators import EmulatorError, Fetcher
from arcadia.setup_status import core_path

BUILDBOT_HOST = "buildbot.libretro.com"
CORE_URL = "https://" + BUILDBOT_HOST + "/nightly/linux/x86_64/latest/{name}.zip"
RETROARCH_APP = "org.libretro.RetroArch"
_CORE_NAME = re.compile(r"^[a-z0-9][a-z0-9_]*_libretro\.so$")
MAX_CORE_BYTES = 400 * 1024 * 1024


# ----------------------------------------------------------------------------
# Settings applied at launch
# ----------------------------------------------------------------------------

def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _flag(on: bool) -> str:
    return _q("true" if on else "false")


def config_text(config: Config) -> str:
    lines = [
        "# Written by Arcadia each time it starts RetroArch. Applied on top of your retroarch.cfg.",
        f"system_directory = {_q(str(config.bios_path))}",
        f"video_fullscreen = {_flag(config.ra_fullscreen)}",
        f"video_vsync = {_flag(config.ra_vsync)}",
        f"video_scale_integer = {_flag(config.ra_integer_scale)}",
        f"savestate_auto_save = {_flag(config.ra_auto_save_state)}",
        f"savestate_auto_load = {_flag(config.ra_auto_save_state)}",
    ]
    if config.ra_saves_in_home:
        lines.append(f"savefile_directory = {_q(str(config.saves_path))}")
    return "\n".join(lines) + "\n"


def appendconfig_path(config: Config) -> Path:
    return config.data_path / "retroarch-arcadia.cfg"


def write_appendconfig(config: Config) -> Path:
    path = appendconfig_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if config.ra_saves_in_home:
        config.saves_path.mkdir(parents=True, exist_ok=True)
    text = config_text(config)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return path


def retroarch_index(args: Sequence[str]) -> int | None:
    """Where RetroArch's own arguments start in a launch command, or None if it isn't RetroArch."""
    if not args:
        return None
    if Path(args[0]).name == "flatpak":
        for i, a in enumerate(args[1:], 1):
            if a == RETROARCH_APP:
                return i + 1
        return None
    return 1 if Path(args[0]).name.lower() == "retroarch" else None


def with_appendconfig(args: list[str], path: Path) -> list[str]:
    """The command with --appendconfig added right after the program. Unchanged if it isn't RetroArch,
    or if the user already passes their own --appendconfig."""
    start = retroarch_index(args)
    if start is None or any(a.startswith("--appendconfig") for a in args):
        return list(args)
    return [*args[:start], f"--appendconfig={path}", *args[start:]]


# ----------------------------------------------------------------------------
# Cores
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class CoreRow:
    name: str  # file name, e.g. snes9x_libretro.so
    path: Path
    systems: tuple[str, ...]
    installed: bool


def cores_in_use(config: Config) -> list[CoreRow]:
    """The cores the configured RetroArch commands load, and whether each file is there."""
    found: dict[Path, list[str]] = {}
    for system in config.systems:
        path = core_path(system.command)
        if path is not None and _CORE_NAME.match(path.name):
            found.setdefault(path, []).append(system.name or system.id)
    return [CoreRow(p.name, p, tuple(names), p.is_file()) for p, names in sorted(found.items(), key=lambda kv: kv[0].name)]


def core_fetcher() -> Fetcher:
    return Fetcher(api_base="https://" + BUILDBOT_HOST, hosts=frozenset({BUILDBOT_HOST}))


def install_core(dest: Path, fetcher: Fetcher | None = None, progress: Callable[[int, int], None] | None = None) -> None:
    """Download the latest build of the core named by dest, and put it there atomically.
    Whatever is already there is untouched unless the whole download checks out."""
    name = dest.name
    if not _CORE_NAME.match(name):
        raise EmulatorError(f"{name} isn't a core name Arcadia will download")
    fetcher = fetcher or core_fetcher()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".core-") as tmp:
        archive = Path(tmp) / "core.zip"
        fetcher.download(CORE_URL.format(name=name), archive, progress)
        try:
            with zipfile.ZipFile(archive) as zf:
                members = [i for i in zf.infolist() if i.filename == name]
                if len(members) != 1:
                    raise EmulatorError(f"the download didn't contain {name}")
                member = members[0]
                if member.file_size > MAX_CORE_BYTES:
                    raise EmulatorError("the core is larger than Arcadia will accept")
                staged = Path(tmp) / name
                with zf.open(member) as src, open(staged, "wb") as out:
                    written = 0
                    while chunk := src.read(256 * 1024):
                        written += len(chunk)
                        if written > MAX_CORE_BYTES:
                            raise EmulatorError("the core is larger than Arcadia will accept")
                        out.write(chunk)
        except zipfile.BadZipFile as exc:
            raise EmulatorError("the download wasn't a readable zip file") from exc
        if staged.stat().st_size < 1024 or staged.read_bytes()[:4] != b"\x7fELF":
            raise EmulatorError("the download isn't a Linux program file")
        staged.chmod(0o755)
        os.replace(staged, dest)


@dataclass
class CoreOutcome:
    name: str
    ok: bool
    error: str = ""
    was_installed: bool = False


def update_cores(
    rows: Sequence[CoreRow],
    fetcher: Fetcher | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[CoreOutcome]:
    """Install or refresh each core. One failing never stops the others. progress covers the batch (100 per core)."""
    outcomes = []
    total = 100 * len(rows)
    for i, row in enumerate(rows):
        def report(done: int, size: int, base=i * 100) -> None:
            if progress and size > 0:
                progress(base + min(99, int(done * 100 / size)), total)

        try:
            install_core(row.path, fetcher, report)
            outcomes.append(CoreOutcome(row.name, True, was_installed=row.installed))
        except (EmulatorError, OSError) as exc:
            outcomes.append(CoreOutcome(row.name, False, str(exc), row.installed))
        if progress:
            progress((i + 1) * 100, total)
    return outcomes


# ----------------------------------------------------------------------------
# Flatpak access
# ----------------------------------------------------------------------------

def access_paths(config: Config) -> list[Path]:
    """The folders Flatpak emulators need to be able to read and write: the Arcadia folder, or
    (in the older layout) the ROM, BIOS and data folders, and the ROM folder if it's elsewhere."""
    paths: list[Path] = []
    if config.home_path:
        paths.append(config.home_path)
    else:
        paths += [config.bios_path, config.data_path, config.saves_path]
    if not config.home_path or config.rom_root.strip():
        paths.append(config.rom_root_path)
    out: list[Path] = []
    for p in paths:
        if ":" in str(p):  # Flatpak reads ':' as the start of a mode (":ro"), so such a path can't be given safely
            continue
        if p not in out:
            out.append(p)
    return out


def grant_commands(apps: Sequence[str], paths: Sequence[Path]) -> list[list[str]]:
    return [["flatpak", "override", "--user", f"--filesystem={p}", app] for app in apps for p in paths]


def shell_form(commands: Sequence[Sequence[str]]) -> str:
    return "\n".join(" ".join(shlex.quote(a) for a in c) for c in commands)


@dataclass
class GrantResult:
    ok: bool
    done: int = 0
    output: str = ""


def grant_access(
    apps: Sequence[str],
    paths: Sequence[Path],
    run: Callable = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> GrantResult:
    """Run the `flatpak override --user` commands. They only widen what those apps can reach, for this
    user, and can be undone with `flatpak override --user --reset <app>`."""
    commands = grant_commands(apps, paths)
    if not commands:
        return GrantResult(True)
    if which("flatpak") is None:
        return GrantResult(False, 0, "flatpak isn't available")
    done = 0
    for command in commands:
        try:
            result = run(command, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return GrantResult(False, done, f"flatpak couldn't be run: {exc}")
        if result.returncode != 0:
            return GrantResult(False, done, ((result.stderr or "") + (result.stdout or "")).strip()[-300:])
        done += 1
    return GrantResult(True, done)
