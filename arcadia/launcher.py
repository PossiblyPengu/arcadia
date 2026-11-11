"""Turn a system's launch template into an argument list for QProcess/subprocess."""

from __future__ import annotations

import os
import shlex
from pathlib import Path


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
