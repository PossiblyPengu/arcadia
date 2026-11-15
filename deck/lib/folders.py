#!/usr/bin/env python3
"""Point every emulator Arcadia installs at the same BIOS folder and the same ROM folder.

Arcadia starts games itself (it hands the emulator the game file), so this is for the times you open an emulator on
its own: its game list shows your games from Arcadia's ROM folder (~/ROMs/<console>), and it finds BIOS files and keys
in your BIOS folder (~/Emulation/bios), the folder "Check BIOS files" looks in.

Each emulator keeps these in its own settings file, in its own format; the setting names here are the emulators' own
(checked against their source code). Only what's missing is filled in: a folder or path you set yourself is never
changed, and a settings file that's changed is backed up first (to ~/Arcadia/backups). A fresh install has no settings
file yet: then a small one is written with just these, and the emulator adds its defaults the first time it starts.

    folders.py set-up APP_ID [APP_ID…]     for those emulators (Flatpak ids)

Environment: ARCADIA_BIOS_DIR (your BIOS folder), ARCADIA_ROMS (Arcadia's ROM folder, default ~/ROMs).

Not here: RetroArch, DuckStation and PCSX2 get their BIOS folder linked to yours (emulators.link_bios); RPCS3's
firmware is installed from RPCS3's own menu (File → Install Firmware), as it can't be done without its window.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BACKUPS = Path(os.environ.get("ARCADIA_HOME") or HOME / "Arcadia") / "backups"


# The emulators this knows (Flatpak ids).
SUPPORTED = ("org.libretro.RetroArch", "org.duckstation.DuckStation", "net.pcsx2.PCSX2", "org.ppsspp.PPSSPP",
             "org.DolphinEmu.dolphin-emu", "org.flycast.Flycast", "io.mgba.mGBA", "net.kuribo64.melonDS",
             "org.azahar_emu.Azahar", "dev.eden_emu.eden", "info.cemu.Cemu", "app.xemu.xemu")


def _app(app_id: str, *rel: str) -> Path:
    return HOME / ".var" / "app" / app_id / Path(*rel)


def _read(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None


def _save(path: Path, lines: list[str], existed: bool) -> None:
    if existed:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUPS / f"{path.parent.name}-{path.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(path)


# ── INI files: [section] then key = value (DuckStation, PCSX2, PPSSPP, Dolphin, Flycast, mGBA, Azahar, Eden) ──────

def _section(lines: list[str], name: str) -> tuple[int, int] | None:
    start = next((i for i, l in enumerate(lines) if l.strip() == f"[{name}]"), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[.+\]\s*$", lines[i])), len(lines))
    return start, end


def _ini_get(lines: list[str], section: str, key: str) -> str | None:
    span = _section(lines, section)
    if span is None:
        return None
    for line in lines[span[0] + 1:span[1]]:
        k, sep, v = line.partition("=")
        if sep and k.strip() == key:
            return v.strip()
    return None


def _ini_put(lines: list[str], section: str, key: str, value: str, sep: str = " = ") -> None:
    """Set key in section (adding the section if needed). Replaces an existing line for key."""
    span = _section(lines, section)
    if span is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"[{section}]", f"{key}{sep}{value}"]
        return
    for i in range(span[0] + 1, span[1]):
        k, eq, _ = lines[i].partition("=")
        if eq and k.strip() == key:
            lines[i] = f"{key}{sep}{value}"
            return
    end = span[1]
    while end > span[0] + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, f"{key}{sep}{value}")


class Ini:
    """One INI settings file: fill in keys that are missing or empty, then save once."""

    def __init__(self, path: Path, sep: str = " = "):
        self.path, self.sep = path, sep
        got = _read(path)
        self.existed, self.lines, self.changed = got is not None, got or [], []

    def get(self, section: str, key: str) -> str | None:
        return _ini_get(self.lines, section, key)

    def fill(self, section: str, key: str, value: str, empty=("",)) -> bool:
        if self.get(section, key) not in (None, *empty):
            return False
        _ini_put(self.lines, section, key, value, self.sep)
        self.changed.append(key)
        return True

    def save(self) -> bool:
        if self.changed:
            _save(self.path, self.lines, self.existed)
        return bool(self.changed)


# ── TOML files: top-level keys, then [table] key = value (melonDS, xemu) ─────────────────────────────────────────────

def _toml_value(v) -> str:
    return "true" if v is True else "false" if v is False else json.dumps(str(v))


def _toml_fill(lines: list[str], table: str | None, key: str, value) -> bool:
    """Add `key = value` to table (None: the top level) unless the key is there already."""
    first_table = next((i for i, l in enumerate(lines) if re.match(r"\s*\[.+\]\s*$", l)), len(lines))
    if table is None:
        start, end = -1, first_table
    else:
        start = next((i for i, l in enumerate(lines) if l.strip() == f"[{table}]"), None)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines += [f"[{table}]", f"{key} = {_toml_value(value)}"]
            return True
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[.+\]\s*$", lines[i])), len(lines))
    if any(re.match(rf"\s*{re.escape(key)}\s*=", l) for l in lines[start + 1:end]):
        return False
    lines.insert(end if table is not None else first_table, f"{key} = {_toml_value(value)}")
    return True


def _toml(path: Path, wanted: list[tuple[str | None, str, object]]) -> list[str]:
    got = _read(path)
    lines, changed = got or [], []
    for table, key, value in wanted:
        if _toml_fill(lines, table, key, value):
            changed.append(key)
    if changed:
        _save(path, lines, got is not None)
    return changed


# ── Files linked in (keys): only where the emulator has none of its own ────────────────────────────────────────────

def _link(src: Path, dest: Path, template_ok: bool = False) -> bool:
    """Link dest → src, when src exists and dest is missing (or, with template_ok, only comments and blanks)."""
    if not src.is_file() or dest.is_symlink():
        return False
    if dest.exists():
        if not template_ok:
            return False
        try:
            if any(l.strip() and not l.lstrip().startswith("#") for l in dest.read_text(errors="replace").splitlines()):
                return False
        except OSError:
            return False
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src)
    return True


def _first(folder: Path, names: list[str]) -> Path | None:
    return next((folder / n for n in names if (folder / n).is_file()), None)


# ── Each emulator ────────────────────────────────────────────────────────────────────────────────────────────────

def _games(roms: Path, console: str) -> str:
    d = roms / console
    d.mkdir(parents=True, exist_ok=True)  # (Arcadia's own folder layout: making it is harmless)
    return str(d)


def _qt_game_dir(ini: Ini, folder: str) -> None:
    """Azahar and Eden (Qt settings): on a fresh settings file the old single "game folder" key, which they add to
    their own default entries; with a list already there, one more entry, unless it's listed."""
    size = ini.get("UI", "Paths\\gamedirs\\size")
    if size is None:
        ini.fill("UI", "Paths\\gameListRootDir", folder, empty=("", "."))
        ini.fill("UI", "Paths\\gameListDeepScan", "false")
        return
    n = int(size) if size.isdigit() else 0
    if any(ini.get("UI", f"Paths\\gamedirs\\{i}\\path") == folder for i in range(1, n + 1)):
        return
    n += 1
    for key, value in ((f"Paths\\gamedirs\\{n}\\path", folder), (f"Paths\\gamedirs\\{n}\\deep_scan", "false"),
                       (f"Paths\\gamedirs\\{n}\\expanded", "true")):
        _ini_put(ini.lines, "UI", key, value, ini.sep)
    _ini_put(ini.lines, "UI", "Paths\\gamedirs\\size", str(n), ini.sep)
    ini.changed.append("gamedirs")


def set_up(app_id: str, bios: Path, roms: Path) -> list[str]:
    """Fill in that emulator's BIOS and ROM folders. Returns what changed (nothing: [])."""
    did: list[str] = []
    has_bios = bios.is_dir()

    def ini(rel: tuple[str, ...], sep: str = " = ") -> Ini:
        return Ini(_app(app_id, *rel), sep)

    if app_id == "org.libretro.RetroArch":
        path = _app(app_id, "config", "retroarch", "retroarch.cfg")
        got = _read(path)
        lines = got or []
        idx = next((i for i, l in enumerate(lines) if re.match(r"\s*rgui_browser_directory\s*=", l)), None)
        current = re.sub(r'.*=\s*"?([^"]*)"?\s*$', r"\1", lines[idx]).strip() if idx is not None else ""
        if current in ("", "default"):
            line = f'rgui_browser_directory = "{roms}"'
            if idx is None:
                lines.append(line)
            else:
                lines[idx] = line
            _save(path, lines, got is not None)
            did.append(f"RetroArch opens games from {roms}")
    elif app_id == "org.duckstation.DuckStation":
        f = ini(("data", "duckstation", "settings.ini"))
        if f.get("GameList", "Paths") is None and f.fill("GameList", "RecursivePaths", _games(roms, "psx")):
            did.append(f"DuckStation lists games from {roms / 'psx'}")
        f.save()
    elif app_id == "net.pcsx2.PCSX2":
        f = ini(("config", "PCSX2", "inis", "PCSX2.ini"))
        if f.get("GameList", "Paths") is None and f.fill("GameList", "RecursivePaths", _games(roms, "ps2")):
            did.append(f"PCSX2 lists games from {roms / 'ps2'}")
        f.save()
    elif app_id == "org.ppsspp.PPSSPP":
        f = ini(("config", "ppsspp", "PSP", "SYSTEM", "ppsspp.ini"))
        if f.fill("General", "CurrentDirectory", _games(roms, "psp")):
            did.append(f"PPSSPP opens games from {roms / 'psp'}")
        f.save()
    elif app_id == "org.DolphinEmu.dolphin-emu":
        f = ini(("config", "dolphin-emu", "Dolphin.ini"))
        if f.get("General", "ISOPaths") in (None, "", "0"):
            for key, value in (("ISOPaths", "2"), ("ISOPath0", _games(roms, "gc")), ("ISOPath1", _games(roms, "wii"))):
                _ini_put(f.lines, "General", key, value)
            f.changed.append("ISOPaths")
            did.append(f"Dolphin lists games from {roms / 'gc'} and {roms / 'wii'}")
        f.save()
    elif app_id == "org.flycast.Flycast":
        f = ini(("config", "flycast", "emu.cfg"))
        if has_bios and f.fill("config", "Dreamcast.BiosPath", str(bios)):
            did.append(f"Flycast finds BIOS files in {bios}")
        if f.fill("config", "Dreamcast.ContentPath", _games(roms, "dreamcast")):
            did.append(f"Flycast lists games from {roms / 'dreamcast'}")
        f.save()
    elif app_id == "io.mgba.mGBA":
        f = ini(("config", "mgba", "config.ini"), sep="=")
        gba_bios = bios / "gba_bios.bin"
        if gba_bios.is_file() and f.get("ports.qt", "gba.bios") in (None, ""):
            f.fill("ports.qt", "gba.bios", str(gba_bios))
            f.fill("ports.qt", "useBios", "1")
            did.append(f"mGBA uses {gba_bios}")
        f.save()
    elif app_id == "net.kuribo64.melonDS":
        wanted: list[tuple[str | None, str, object]] = [(None, "LastROMFolder", _games(roms, "nds"))]
        files = [bios / n for n in ("bios9.bin", "bios7.bin", "firmware.bin")]
        if all(p.is_file() for p in files):
            wanted += [("Emu", "ExternalBIOSEnable", True), ("DS", "BIOS9Path", str(files[0])),
                       ("DS", "BIOS7Path", str(files[1])), ("DS", "FirmwarePath", str(files[2]))]
        changed = _toml(_app(app_id, "config", "melonDS", "melonDS.toml"), wanted)
        if "LastROMFolder" in changed:
            did.append(f"melonDS opens games from {roms / 'nds'}")
        if "BIOS9Path" in changed:
            did.append(f"melonDS uses the DS BIOS and firmware in {bios}")
    elif app_id == "org.azahar_emu.Azahar":
        f = ini(("config", "azahar-emu", "qt-config.ini"), sep="=")
        _qt_game_dir(f, _games(roms, "n3ds"))
        if f.save():
            did.append(f"Azahar lists games from {roms / 'n3ds'}")
    elif app_id == "dev.eden_emu.eden":
        keys = [k for k in ("prod.keys", "title.keys") if _link(bios / k, _app(app_id, "data", "eden", "keys", k))]
        if keys:
            did.append(f"Eden uses {' and '.join(keys)} from {bios}")
        f = ini(("config", "eden", "qt-config.ini"), sep="=")
        _qt_game_dir(f, _games(roms, "switch"))
        if f.save():
            did.append(f"Eden lists games from {roms / 'switch'}")
    elif app_id == "info.cemu.Cemu":
        if _link(bios / "keys.txt", _app(app_id, "data", "Cemu", "keys.txt"), template_ok=True):
            did.append(f"Cemu uses keys.txt from {bios}")
        did += _cemu_game_path(_app(app_id, "config", "Cemu", "settings.xml"), _games(roms, "wiiu"))
    elif app_id == "app.xemu.xemu":
        wanted = []
        boot = _first(bios, ["mcpx_1.0.bin"])
        flash = _first(bios, ["Complex_4627v1.03.bin", "Complex_4627.bin"])
        if boot:
            wanted.append(("sys.files", "bootrom_path", str(boot)))
        if flash:
            wanted.append(("sys.files", "flashrom_path", str(flash)))
        if wanted and _toml(_app(app_id, "data", "xemu", "xemu", "xemu.toml"), wanted):
            did.append(f"xemu uses the Xbox BIOS files in {bios}")
    return did


def _cemu_game_path(path: Path, folder: str) -> list[str]:
    got = _read(path)
    entry = f"<Entry>{folder}</Entry>"
    if got is None:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<content>", "    <GamePaths>", f"        {entry}",
                 "    </GamePaths>", "</content>"]
    else:
        text = "\n".join(got)
        if folder in text:
            return []
        if "<GamePaths/>" in text:
            text = text.replace("<GamePaths/>", f"<GamePaths>\n        {entry}\n    </GamePaths>", 1)
        elif "<GamePaths>" in text:
            text = text.replace("<GamePaths>", f"<GamePaths>\n        {entry}", 1)
        elif "</content>" in text:
            text = text.replace("</content>", f"    <GamePaths>\n        {entry}\n    </GamePaths>\n</content>", 1)
        else:
            return []  # (not a settings file this understands: left alone)
        lines = text.splitlines()
    _save(path, lines, got is not None)
    return [f"Cemu lists games from {folder}"]


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "set-up":
        bios = Path(os.environ.get("ARCADIA_BIOS_DIR") or HOME / "Emulation" / "bios")
        roms = Path(os.environ.get("ARCADIA_ROMS") or HOME / "ROMs")
        for app_id in argv[1:]:
            for msg in set_up(app_id, bios, roms):
                print(msg)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
