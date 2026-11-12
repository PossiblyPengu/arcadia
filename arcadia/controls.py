"""Starter controller settings for the emulators Arcadia installs.

Arcadia gives each emulator it installs its own settings folder, so it can put a starter controller setup there
before the first run: the Deck's gamepad (in Game Mode Steam presents it as a standard Xbox-style controller)
mapped the way each console expects. It is careful with what is already there:

* it only writes settings for the first controller port, and only when that file has no controller section yet;
* "Reset" replaces just that section and first keeps a copy of the whole file in backups/controls;
* anything else in the file is left exactly as it was.

DuckStation and PCSX2 keep controls in a plain settings file, which is what's written here (SDL-0/... names are
"the first connected standard gamepad"). RetroArch's hotkeys are in retroarch.py. Other emulators pick up a
standard gamepad themselves, so they get a one-line tip instead. These formats come from each emulator's
documentation and weren't run here, so the first launch on a real machine is the real test.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CONFIG, DATA = "config", "data"

_DUALSHOCK = {
    "Up": "DPadUp", "Right": "DPadRight", "Down": "DPadDown", "Left": "DPadLeft",
    "Triangle": "Y", "Circle": "B", "Cross": "A", "Square": "X",
    "Select": "Back", "Start": "Start",
    "L1": "LeftShoulder", "R1": "RightShoulder", "L2": "+LeftTrigger", "R2": "+RightTrigger",
    "L3": "LeftStick", "R3": "RightStick", "Analog": "Guide",
}
_PS2_STICKS = {
    "LUp": "-LeftY", "LRight": "+LeftX", "LDown": "+LeftY", "LLeft": "-LeftX",
    "RUp": "-RightY", "RRight": "+RightX", "RDown": "+RightY", "RLeft": "-RightX",
}
_PS1_STICKS = {
    "LLeft": "-LeftX", "LRight": "+LeftX", "LDown": "+LeftY", "LUp": "-LeftY",
    "RLeft": "-RightX", "RRight": "+RightX", "RDown": "+RightY", "RUp": "-RightY",
}


def _pad(kind: str, fixed: list[tuple[str, str]], buttons: dict[str, str]) -> list[str]:
    lines = ["[Pad1]", f"Type = {kind}"]
    lines += [f"{k} = {v}" for k, v in fixed]
    lines += [f"{k} = SDL-0/{v}" for k, v in buttons.items()]
    return lines


def _pcsx2_pad() -> list[str]:
    fixed = [("InvertL", "0"), ("InvertR", "0"), ("Deadzone", "0"), ("AxisScale", "1.33"), ("LargeMotorScale", "1"),
             ("SmallMotorScale", "1"), ("ButtonDeadzone", "0"), ("PressureModifier", "0.5")]
    return _pad("DualShock2", fixed, {**_DUALSHOCK, **_PS2_STICKS}) + ["LargeMotor = SDL-0/LargeMotor", "SmallMotor = SDL-0/SmallMotor"]


@dataclass(frozen=True)
class Seed:
    name: str
    relative: tuple[str, ...]  # settings file, under the emulator's own folder
    section: str
    body: list[str]


SEEDS: dict[str, Seed] = {
    "duckstation": Seed("DuckStation", (DATA, "duckstation", "settings.ini"), "Pad1", _pad("AnalogController", [], {**_DUALSHOCK, **_PS1_STICKS})),
    "pcsx2": Seed("PCSX2", (CONFIG, "PCSX2", "inis", "PCSX2.ini"), "Pad1", _pcsx2_pad()),
}

TIPS = "It picks up a standard gamepad on its own. If a button is wrong, open its Controller settings once, choose your controller and press its default / auto-map button."


def supported(emu_id: str) -> bool:
    return emu_id in SEEDS


def settings_file(emu_id: str, folder: Path) -> Path:
    return folder.joinpath(*SEEDS[emu_id].relative)


def _section_span(lines: list[str], name: str) -> tuple[int, int] | None:
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"[{name.lower()}]"), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[.+\]\s*$", lines[i])), len(lines))
    return start, end


def _has_controls(lines: list[str], span: tuple[int, int] | None) -> bool:
    """A controller section counts as set up if it binds anything to a device."""
    if span is None:
        return False
    return any("SDL-" in l or "Keyboard/" in l or "Pointer-" in l or "XInput-" in l for l in lines[span[0] + 1:span[1]])


@dataclass
class Outcome:
    action: str  # "created", "added", "replaced", "kept"
    path: Path
    backup: Path | None = None


def status(emu_id: str, folder: Path) -> str:
    """What's there: "none" (no settings file or no controls yet), "set" (it has controls, ours or yours)."""
    path = settings_file(emu_id, folder)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "none"
    return "set" if _has_controls(lines, _section_span(lines, SEEDS[emu_id].section)) else "none"


def apply(emu_id: str, folder: Path, backups: Path, force: bool = False) -> Outcome:
    """Put the starter controls in place. Without force, anything already bound is kept. With force the controller
    section is replaced (and the whole file is copied to `backups` first)."""
    seed = SEEDS[emu_id]
    path = settings_file(emu_id, folder)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        existed = True
    except OSError:
        lines, existed = [], False
    span = _section_span(lines, seed.section)
    if _has_controls(lines, span) and not force:
        return Outcome("kept", path)
    backup = None
    if existed:
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"{emu_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.ini"
        shutil.copy2(path, backup)
    block = list(seed.body)
    if span is not None:
        lines[span[0]:span[1]] = block + [""]
        action = "replaced"
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += block
        action = "added" if existed else "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(path)
    return Outcome(action, path, backup)
