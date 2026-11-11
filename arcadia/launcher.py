"""Turn a system's launch template into an argument list for QProcess/subprocess."""

from __future__ import annotations

import shlex
from pathlib import Path


class LaunchError(Exception):
    pass


def build_command(template: str, rom: Path) -> list[str]:
    """Substitute the ROM path into a launch template.

    Example: 'retroarch -L /cores/snes9x.so {rom}' ->
             ['retroarch', '-L', '/cores/snes9x.so', '/roms/snes/Game (USA).sfc']
    If the template has no {rom}, the ROM path is appended as the last argument.
    """
    if not template or not template.strip():
        raise LaunchError("No launch command is set for this system. Add one in Settings.")
    quoted = shlex.quote(str(rom))
    if "{rom}" in template:
        command = template.replace("{rom}", quoted)
    else:
        command = f"{template} {quoted}"
    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise LaunchError(f"Launch command could not be parsed: {exc}") from exc
    if not args:
        raise LaunchError("Launch command is empty after substitution.")
    return args
