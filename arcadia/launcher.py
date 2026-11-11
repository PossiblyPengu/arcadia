"""Turn a system's launch template into an argument list for QProcess/subprocess."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from arcadia.emulators import CATALOG, Installer
from arcadia.retroarch import retroarch_index, with_appendconfig, write_appendconfig

if TYPE_CHECKING:
    from arcadia.config import Config, SystemConfig


class LaunchError(Exception):
    pass


def build_command(template: str, rom: Path, extras: dict[str, list[Path]] | None = None) -> list[str]:
    """Substitute the ROM path into a launch template.

    Example: 'retroarch -L /cores/snes9x.so {rom}' ->
             ['retroarch', '-L', '/cores/snes9x.so', '/roms/snes/Game (USA).sfc']
    If the template has no {rom}, the ROM path is appended as the last argument.
    A leading '~' in any argument is expanded to the home directory.

    Other placeholders for the game's own path (each is quoted):
        {stem}     the file name without its extension (MAME wants this: mame -rompath {dir} {stem})
        {dir}      the folder the game is in

    Games made of several files can use extra placeholders, each replaced by the quoted
    paths of that kind of file (or by nothing if there are none):
        {updates}  update files linked to the game
        {dlc}      DLC files linked to the game
        {discs}    the discs of a multi-disc game
    """
    if not template or not template.strip():
        raise LaunchError("No launch command is set for this system. Add one in Settings.")
    command = template
    for name, paths in (extras or {}).items():
        command = command.replace("{" + name + "}", " ".join(shlex.quote(str(p)) for p in paths))
    for name in ("updates", "dlc", "discs"):  # placeholders with nothing to fill them
        command = command.replace("{" + name + "}", "")
    command = command.replace("{stem}", shlex.quote(rom.stem)).replace("{dir}", shlex.quote(str(rom.parent)))
    quoted = shlex.quote(str(rom))
    if "{rom}" in command:
        command = command.replace("{rom}", quoted)
    elif "{stem}" not in template and "{dir}" not in template:
        command = f"{command} {quoted}"  # no placeholder for the game at all: it goes last
    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise LaunchError(f"Launch command could not be parsed: {exc}") from exc
    if not args:
        raise LaunchError("Launch command is empty after substitution.")
    return [os.path.expanduser(a) for a in args]


@dataclass
class LaunchPlan:
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)  # extra environment variables for the emulator
    via: str = "command"  # "command", or "local:<emulator id>" for a copy Arcadia installed itself


def resolve_launch(
    config: "Config", system: "SystemConfig", rom: Path, extras: dict[str, list[Path]] | None = None
) -> LaunchPlan:
    """Work out how to start a game. A system with a managed emulator that is installed runs that
    copy, with its settings, saves and caches kept in its own folder. Otherwise the system's launch
    command is used, which by default is the emulator's Flatpak."""
    spec = CATALOG.get(system.emulator) if system.emulator else None
    if spec is not None:
        installer = Installer(config.emulators_path)
        installed = installer.get(spec.id)
        if installed is not None:
            template = f"{shlex.quote(str(installer.exe_path(installed)))} {spec.args}"
            return LaunchPlan(build_command(template, rom, extras), installer.launch_env(spec.id), f"local:{spec.id}")
        if not system.command.strip():
            raise LaunchError(f"{spec.name} isn't installed. Install it from File → Emulators…")
    args = build_command(system.command, rom, extras)
    if config.manage_retroarch and retroarch_index(args) is not None:
        try:
            args = with_appendconfig(args, write_appendconfig(config))
        except OSError:
            pass  # RetroArch still starts, just with the user's own settings
    return LaunchPlan(args)
