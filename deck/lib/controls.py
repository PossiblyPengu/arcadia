#!/usr/bin/env python3
"""Starter controller settings for the Flatpak emulators on a Steam Deck.

In Game Mode the Deck's controller reaches every emulator as a standard Xbox-style gamepad. DuckStation and PCSX2
(Flatpak) get the first controller's buttons written into their settings file, and RetroArch gets the usual couch
hotkeys (hold Select: Start quits, X opens the menu, bumpers load / save a state), each only when nothing is set yet.

  controls.py            fill in what's missing
  controls.py --reset    replace those controller settings with these (the old file is copied to ~/ES-DE/backups/controls)

Nothing else in a settings file is touched. The setting names follow each emulator's documented format and have not
been run against the emulators themselves.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("HOME", "~")).expanduser()
BACKUPS = Path(os.environ.get("ES_DE_HOME", HOME / "ES-DE")) / "backups" / "controls"

_DUALSHOCK = {
    "Up": "DPadUp", "Right": "DPadRight", "Down": "DPadDown", "Left": "DPadLeft",
    "Triangle": "Y", "Circle": "B", "Cross": "A", "Square": "X", "Select": "Back", "Start": "Start",
    "L1": "LeftShoulder", "R1": "RightShoulder", "L2": "+LeftTrigger", "R2": "+RightTrigger",
    "L3": "LeftStick", "R3": "RightStick", "Analog": "Guide",
}
_PS2_STICKS = {"LUp": "-LeftY", "LRight": "+LeftX", "LDown": "+LeftY", "LLeft": "-LeftX",
               "RUp": "-RightY", "RRight": "+RightX", "RDown": "+RightY", "RLeft": "-RightX"}
_PS1_STICKS = {"LLeft": "-LeftX", "LRight": "+LeftX", "LDown": "+LeftY", "LUp": "-LeftY",
               "RLeft": "-RightX", "RRight": "+RightX", "RDown": "+RightY", "RUp": "-RightY"}


def _pad(kind: str, fixed: list[tuple[str, str]], buttons: dict[str, str]) -> list[str]:
    return [f"[Pad1]", f"Type = {kind}", *[f"{k} = {v}" for k, v in fixed], *[f"{k} = SDL-0/{v}" for k, v in buttons.items()]]


PCSX2_FIXED = [("InvertL", "0"), ("InvertR", "0"), ("Deadzone", "0"), ("AxisScale", "1.33"), ("LargeMotorScale", "1"),
               ("SmallMotorScale", "1"), ("ButtonDeadzone", "0"), ("PressureModifier", "0.5")]

# flatpak id -> (name, settings file under ~/.var/app/<id>, controller section lines)
INI_EMULATORS = {
    "org.duckstation.DuckStation": ("DuckStation", ("data", "duckstation", "settings.ini"),
                                    _pad("AnalogController", [], {**_DUALSHOCK, **_PS1_STICKS})),
    "net.pcsx2.PCSX2": ("PCSX2", ("config", "PCSX2", "inis", "PCSX2.ini"),
                        _pad("DualShock2", PCSX2_FIXED, {**_DUALSHOCK, **_PS2_STICKS}) + ["LargeMotor = SDL-0/LargeMotor", "SmallMotor = SDL-0/SmallMotor"]),
}
RETROARCH = "org.libretro.RetroArch"
# RetroArch, by the buttons of a standard (Xbox-style) pad: hold Select (6), then Start (7) quits, X (2) menu, L1 (4) / R1 (5) load / save state
RETROARCH_KEYS = {
    "input_enable_hotkey_btn": "6", "input_exit_emulator_btn": "7", "input_menu_toggle_btn": "2",
    "input_load_state_btn": "4", "input_save_state_btn": "5",
}


def flatpak_installed(app_id: str) -> bool:
    try:
        return subprocess.run(["flatpak", "info", app_id], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _backup(path: Path) -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    target = BACKUPS / f"{path.parent.name}-{path.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, target)
    return target


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(path)


def _span(lines: list[str], name: str):
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"[{name.lower()}]"), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[.+\]\s*$", lines[i])), len(lines))
    return start, end


def _bound(lines: list[str], span) -> bool:
    return span is not None and any(re.search(r"SDL-\d|Keyboard/|XInput-|Pointer-", l) for l in lines[span[0] + 1:span[1]])


def seed_ini(app_id: str, reset: bool = False) -> str:
    name, rel, body = INI_EMULATORS[app_id]
    path = HOME / ".var" / "app" / app_id / Path(*rel)
    try:
        lines, existed = path.read_text(encoding="utf-8").splitlines(), True
    except OSError:
        lines, existed = [], False
    span = _span(lines, "Pad1")
    if _bound(lines, span) and not reset:
        return f"{name}: already has controls, left as they are"
    note = ""
    if existed:
        note = f" (old file kept in {_backup(path)})"
    if span is not None:
        lines[span[0]:span[1]] = body + [""]
        what = "controls reset"
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += body
        what = "controls added" if existed else "controls created"
    _write(path, lines)
    return f"{name}: {what}{note}"


def seed_retroarch(reset: bool = False) -> str:
    path = HOME / ".var" / "app" / RETROARCH / "config" / "retroarch" / "retroarch.cfg"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "RetroArch: no retroarch.cfg yet (start RetroArch once, then run this again)"
    changed = []
    for key, value in RETROARCH_KEYS.items():
        idx = next((i for i, l in enumerate(lines) if re.match(rf"\s*{key}\s*=", l)), None)
        current = re.sub(r'.*=\s*"?([^"]*)"?\s*$', r"\1", lines[idx]).strip() if idx is not None else "nul"
        if current not in ("nul", "") and not reset:
            continue
        line = f'{key} = "{value}"'
        if idx is None:
            lines.append(line)
        elif lines[idx] != line:
            lines[idx] = line
        else:
            continue
        changed.append(key)
    if not changed:
        return "RetroArch: hotkeys already set, left as they are"
    note = _backup(path)
    _write(path, lines)
    return f"RetroArch: set {len(changed)} hotkey(s) (old file kept in {note})"


def main(argv: list[str]) -> int:
    reset = "--reset" in argv
    results = []
    for app_id in INI_EMULATORS:
        if flatpak_installed(app_id):
            results.append(seed_ini(app_id, reset))
    if flatpak_installed(RETROARCH):
        results.append(seed_retroarch(reset))
    if not results:
        results.append("None of DuckStation, PCSX2 or RetroArch (Flatpak) are installed, so there was nothing to set up.")
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
