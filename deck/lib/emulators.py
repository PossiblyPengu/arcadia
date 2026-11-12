#!/usr/bin/env python3
"""Which emulators your games need, and installing them.

Arcadia launches each console with the emulator named first in its systems file (es_systems.xml). For most classic
consoles that is RetroArch with a *core* (a plug-in per console), and the RetroArch app from Flathub comes without
cores. So "install RetroArch" alone leaves those games unable to start. This works out, from the games in your ROM
folders, exactly what is needed (the Flatpak apps and the RetroArch cores) and installs that:

    emulators.py plan                     one line per emulator, for Arcadia's Emulators screen (see `plan_lines`)
    emulators.py status                   one line for the Setup checklist:  done|detail
    emulators.py install --needed         what your games need and isn't there yet
    emulators.py install ID [ID…]         those apps (Flatpak ids or names), plus the cores your games need from them
    emulators.py remove ID                uninstall one app
    emulators.py update                   update the installed apps, and refresh RetroArch cores that changed

Apps come from Flathub (a user-level install, like Discover's). Cores come from libretro's own build server, the place
RetroArch's Core Downloader uses; each is checked against the server's published checksum before it is put in place.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
HOME = Path.home()
ESDE = Path(os.environ.get("ARCADIA_HOME", HOME / "Arcadia"))
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
RETROARCH = "org.libretro.RetroArch"
CORES_URL = os.environ.get("ARCADIA_CORES_URL", "https://buildbot.libretro.com/nightly/linux/x86_64/latest")
CORE_HOSTS = {"buildbot.libretro.com"}
TEST_MODE = "ARCADIA_CORES_URL" in os.environ  # tests serve the cores from 127.0.0.1
CORES_DIR = Path(os.environ.get("ARCADIA_RETROARCH_CORES",
                                HOME / ".var/app/org.libretro.RetroArch/config/retroarch/cores"))
SKIP = {".txt", ".xml", ".md", ".nfo", ".jpg", ".png", ".db"}

# The emulators Arcadia offers, in the order shown: Flatpak id, name, what it is for (when no games say it).
KNOWN = (
    (RETROARCH, "RetroArch", "NES, SNES, Mega Drive, N64, PlayStation and most classic consoles"),
    ("org.duckstation.DuckStation", "DuckStation", "PlayStation"),
    ("net.pcsx2.PCSX2", "PCSX2", "PlayStation 2"),
    ("org.ppsspp.PPSSPP", "PPSSPP", "PSP"),
    ("org.DolphinEmu.dolphin-emu", "Dolphin", "GameCube and Wii"),
    ("net.kuribo64.melonDS", "melonDS", "Nintendo DS"),
    ("org.azahar_emu.Azahar", "Azahar", "Nintendo 3DS"),
    ("io.mgba.mGBA", "mGBA", "Game Boy Advance"),
    ("org.flycast.Flycast", "Flycast", "Dreamcast"),
    ("net.rpcs3.RPCS3", "RPCS3", "PlayStation 3"),
    ("info.cemu.Cemu", "Cemu", "Wii U"),
    ("app.xemu.xemu", "xemu", "Xbox"),
)
NAMES = {i: n for i, n, _ in KNOWN}
_FLATPAK_ID = re.compile(r"^[A-Za-z][\w-]*(\.[\w-]+){2,}$")


class InstallError(Exception):
    pass


# ---- what Arcadia uses for each console --------------------------------------------------------------------------------

@dataclass
class Command:
    label: str  # e.g. "Beetle PSX"
    emulator: str  # the find-rule name, e.g. "RETROARCH" ("OS-SHELL" for shortcuts and scripts)
    core: str = ""  # e.g. "mednafen_psx" (RetroArch only)


@dataclass
class System:
    name: str  # ES-DE's system name, e.g. "psx"
    folder: str  # its ROM folder, e.g. "psx"
    fullname: str  # e.g. "Sony PlayStation"
    commands: list[Command]  # the first is what Arcadia uses unless you pick another

    def launcher(self) -> Command | None:
        """What actually runs the games. A shortcut-based default ("RPCS3 Shortcut") still needs the emulator it names,
        so that is the command that counts; a plain shortcut or script (Windows, ports, Steam) needs no emulator."""
        first = self.commands[0]
        if first.emulator != "OS-SHELL":
            return first
        word = (first.label.split() or [""])[0].upper()
        return next((c for c in self.commands[1:] if c.emulator == word), None)


def systems_files() -> list[Path]:
    """Arcadia's own systems file (copied next to the tools by install.sh, or the source tree's), then yours."""
    for d in (HERE / "systems", HERE.parents[1] / "resources/systems/linux"):
        if (d / "es_systems.xml").is_file():
            return [d / "es_systems.xml", ESDE / "custom_systems/es_systems.xml"]
    return [ESDE / "custom_systems/es_systems.xml"]


def find_rules_files() -> list[Path]:
    for d in (HERE / "systems", HERE.parents[1] / "resources/systems/linux"):
        if (d / "es_find_rules.xml").is_file():
            return [d / "es_find_rules.xml", ESDE / "custom_systems/es_find_rules.xml"]
    return [ESDE / "custom_systems/es_find_rules.xml"]


def load_systems(files: list[Path]) -> dict[str, System]:
    """By ROM folder. A later file (your custom systems) replaces a system of the same name."""
    by_name: dict[str, System] = {}
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except (OSError, ET.ParseError):
            continue
        for s in root.iter("system"):
            name = (s.findtext("name") or "").strip()
            path = (s.findtext("path") or "").strip()
            commands = []
            for cmd in s.findall("command"):
                text = cmd.text or ""
                emu = re.search(r"%EMULATOR_([A-Za-z0-9_-]+)%", text)
                core = re.search(r"%CORE_RETROARCH%/(\S+?)_libretro\.so", text)
                commands.append(Command(cmd.get("label", ""), emu.group(1).upper() if emu else "",
                                        core.group(1) if core else ""))
            if not name or not commands:
                continue
            folder = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or name
            by_name[name] = System(name, folder, (s.findtext("fullname") or name).strip(), commands)
    return {s.folder: s for s in by_name.values()}


def load_find_rules(files: list[Path]) -> dict[str, list[str]]:
    """Find-rule name → the Flatpak ids it looks for (e.g. RETROARCH → [org.libretro.RetroArch])."""
    rules: dict[str, list[str]] = {}
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except (OSError, ET.ParseError):
            continue
        for emu in root.iter("emulator"):
            ids = []
            for e in emu.iter("entry"):
                text = (e.text or "").strip()
                last = text.rsplit("/", 1)[-1]
                if "/flatpak/exports/bin/" in text or (_FLATPAK_ID.match(text) and "/" not in text):
                    if _FLATPAK_ID.match(last) and last not in ids:
                        ids.append(last)
            if ids:
                rules[emu.get("name", "").upper()] = ids
    return rules


def game_counts(roms: Path) -> dict[str, int]:
    """ROM folder → how many game files it has (two levels deep, like the Setup checklist counts them)."""
    counts: dict[str, int] = {}
    try:
        folders = [d for d in roms.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return counts
    for d in folders:
        n = 0
        for f in list(d.glob("*")) + list(d.glob("*/*")):
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() not in SKIP:
                n += 1
        if n:
            counts[d.name] = n
    return counts


# ---- what is installed -------------------------------------------------------------------------------------------------

def flatpak() -> str | None:
    return shutil.which("flatpak")


def installed(app_id: str) -> bool:
    exe = flatpak()
    return bool(exe) and subprocess.run([exe, "info", app_id], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL).returncode == 0


def core_installed(core: str) -> bool:
    return (CORES_DIR / f"{core}_libretro.so").is_file()


# ---- the plan ---------------------------------------------------------------------------------------------------------

@dataclass
class Emulator:
    id: str
    name: str
    blurb: str
    installed: bool = False
    games: list[tuple[str, int]] = field(default_factory=list)  # (console, games) your games need it for
    cores: dict[str, str] = field(default_factory=dict)  # core → console, the cores your games need (RetroArch)

    @property
    def needed(self) -> bool:
        return bool(self.games)

    def missing_cores(self) -> list[str]:
        return [c for c in self.cores if not core_installed(c)]

    @property
    def ready(self) -> bool:
        return self.installed and not self.missing_cores()


@dataclass
class Plan:
    emulators: list[Emulator]
    unsupported: list[tuple[str, int, str]]  # consoles with games nothing here installs: (console, games, what runs them)

    def needed(self) -> list[Emulator]:
        return [e for e in self.emulators if e.needed]


def make_plan(roms: Path, systems: dict[str, System], rules: dict[str, list[str]],
              is_installed=installed) -> Plan:
    emus = {i: Emulator(i, n, b) for i, n, b in KNOWN}
    unsupported: list[tuple[str, int, str]] = []
    for folder, n in sorted(game_counts(roms).items(), key=lambda kv: -kv[1]):
        s = systems.get(folder)
        if s is None:
            continue  # not a console folder Arcadia knows (Arcadia doesn't show it either)
        cmd = s.launcher()
        if cmd is None:
            if s.name == "windows":
                unsupported.append((s.fullname, n, "deckhand"))  # Windows programs are Deckhand's job
            continue  # shortcuts and scripts: nothing to install
        ids = rules.get(cmd.emulator, [])
        app = next((i for i in ids if i in emus), ids[0] if ids else "")
        if not app:
            unsupported.append((s.fullname, n, re.sub(r"\s*\(Standalone\)", "", cmd.label) or cmd.emulator.title()))
            continue
        if app not in emus:
            emus[app] = Emulator(app, re.sub(r"\s*\(Standalone\)", "", cmd.label) or app.rsplit(".", 1)[-1], "")
        emus[app].games.append((s.fullname, n))
        if cmd.core:
            emus[app].cores.setdefault(cmd.core, s.fullname)
    for e in emus.values():
        e.installed = is_installed(e.id)
    order = {i: k for k, (i, _, _) in enumerate(KNOWN)}
    ordered = sorted(emus.values(), key=lambda e: (not e.needed, -sum(n for _, n in e.games), order.get(e.id, 99)))
    return Plan(ordered, unsupported)


def plan_from_disk(roms: Path) -> Plan:
    return make_plan(roms, load_systems(systems_files()), load_find_rules(find_rules_files()))


def _games(n: int) -> str:
    return f"{n} game{'s' * (n != 1)}"


def describe(e: Emulator) -> str:
    """The emulator's line on the Emulators screen: what's missing first (the line may be cut short), then what for."""
    missing = e.missing_cores() if e.installed else []
    head = f"{len(missing)} core{'s' * (len(missing) != 1)} to add · " if missing else ""
    if e.games:
        shown = [f"{c} ({_games(n)})" for c, n in e.games[:3]]
        more = len(e.games) - 3
        return head + "for your " + ", ".join(shown) + (f" and {more} more" if more > 0 else "")
    return head + (e.blurb or "not needed for your games")


def plan_lines(plan: Plan) -> list[str]:
    """For the Emulators screen:  emu|id|name|state|needed|detail   and   none|console|games|what runs them
    ("deckhand" for Windows games, else the emulator Arcadia uses, which isn't on Flathub).
    state: ready (installed, with every core your games need), cores (installed, cores missing), missing."""
    out = []
    for e in plan.emulators:
        state = "ready" if e.ready else "cores" if e.installed else "missing"
        out.append("|".join(("emu", e.id, e.name, state, "1" if e.needed else "0", describe(e).replace("|", "/"))))
    for console, n, runner in plan.unsupported:
        out.append(f"none|{console}|{n}|{runner}")
    return out


def status_line(plan: Plan) -> str:
    """done|detail for the Setup checklist (a short line: it shares the row)."""
    need = plan.needed()
    if not need:
        n = sum(e.installed for e in plan.emulators)
        return f"0|{f'{n} installed' if n else 'add games first'}"
    todo = [e for e in need if not e.ready]
    if not todo:
        return "1|ready for all your games"
    if len(todo) == 1 and todo[0].installed:
        return "0|cores missing"
    names = ", ".join(e.name for e in todo[:2]) + (f" +{len(todo) - 2}" if len(todo) > 2 else "")
    return f"0|needs {names}"


# ---- installing -------------------------------------------------------------------------------------------------------

def say(text: str) -> None:
    print(text, flush=True)  # Arcadia shows each line as it comes


def log(text: str) -> None:
    try:
        (ESDE / "logs").mkdir(parents=True, exist_ok=True)
        with open(ESDE / "logs/deck.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" emulators: {text}\n")
    except OSError:
        pass


def _run(args: list[str]) -> tuple[int, str]:
    log(" ".join(args))
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.stdout:
        log(p.stdout.strip()[-2000:])
    return p.returncode, p.stdout or ""


def ensure_flathub(exe: str) -> None:
    """The user-level Flathub source the installs use (SteamOS only sets up the system-wide one)."""
    _run([exe, "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB])


def grant_folders(exe: str, app_id: str) -> None:
    """Let the app see your ROM, BIOS and save folders (a Flatpak can't, unless told)."""
    dirs = [d for d in os.environ.get("ARCADIA_GRANT_DIRS", "").split(":") if d and Path(d).is_dir()]
    if dirs:
        _run([exe, "override", "--user", *[f"--filesystem={d}" for d in dirs], app_id])


def _open(url: str):
    p = urlparse(url)
    local = TEST_MODE and p.hostname in ("127.0.0.1", "localhost")
    if not local and (p.scheme != "https" or p.hostname not in CORE_HOSTS):
        raise InstallError(f"refusing to download from {url}")
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "arcadia-emulators"}),
                                      timeout=60)
    except OSError as exc:
        raise InstallError(f"couldn't reach {p.hostname} ({exc})") from exc


def core_index() -> dict[str, str]:
    """core → the CRC-32 the build server publishes for its library (from .index-extended)."""
    with _open(f"{CORES_URL}/.index-extended") as r:
        text = r.read(4 << 20).decode("utf-8", "replace")
    index = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].endswith("_libretro.so.zip") and re.fullmatch(r"[0-9a-f]{8}", parts[1]):
            index[parts[2][:-len("_libretro.so.zip")]] = parts[1]
    if not index:
        raise InstallError("the core list from libretro was empty")
    return index


def _crc(path: Path) -> str:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xFFFFFFFF:08x}"


def install_core(core: str, index: dict[str, str]) -> None:
    """Download one core, check it against the published checksum, and put it where RetroArch (and Arcadia) look."""
    expected = index.get(core)
    if not expected:
        raise InstallError(f"libretro doesn't offer {core} for this kind of PC")
    CORES_DIR.mkdir(parents=True, exist_ok=True)
    lib = f"{core}_libretro.so"
    with tempfile.TemporaryDirectory(dir=CORES_DIR.parent) as tmp:
        archive = Path(tmp) / f"{lib}.zip"
        with _open(f"{CORES_URL}/{lib}.zip") as r, open(archive, "wb") as out:
            shutil.copyfileobj(r, out, 1 << 20)
        try:
            with zipfile.ZipFile(archive) as z:
                if lib not in z.namelist():
                    raise InstallError(f"the download for {core} doesn't hold {lib}")
                z.extract(lib, tmp)  # (checks the archive's own CRC as it goes)
        except (zipfile.BadZipFile, OSError) as exc:
            raise InstallError(f"the download for {core} is damaged ({exc})") from exc
        got = _crc(Path(tmp) / lib)
        if got != expected:
            raise InstallError(f"{core} doesn't match the checksum libretro publishes, so it wasn't installed")
        os.replace(Path(tmp) / lib, CORES_DIR / lib)
    log(f"core {core} installed (crc32 {expected})")


def install(plan: Plan, ids: list[str]) -> int:
    """Install those apps (skipping ones already there) and every core the games need from them. Prints progress."""
    exe = flatpak()
    if not exe:
        say("Flatpak isn't installed, so emulators can't be installed from here.")
        return 1
    chosen = [e for e in plan.emulators if e.id in ids]
    apps = [e for e in chosen if not e.installed]
    if not apps and not any(e.missing_cores() for e in chosen if e.installed):
        say("Everything is already installed.")
        return 0
    failed: list[str] = []
    # Arcadia draws a progress bar from "@progress done/total" lines (they aren't shown).
    total = len(apps) + len({c for e in chosen for c in e.cores if not core_installed(c)})
    step = [0]

    def progress() -> None:
        print(f"@progress {step[0]}/{total}", flush=True)
        step[0] += 1

    progress()
    if apps:
        ensure_flathub(exe)
    for k, e in enumerate(apps, 1):
        say(f"Installing {e.name} ({k} of {len(apps)}) from Flathub… this can take a few minutes.")
        start = time.time()
        rc, out = _run([exe, "install", "--user", "-y", "--noninteractive", "flathub", e.id])
        if rc == 0:
            e.installed = True
            grant_folders(exe, e.id)
            say(f"  ✓ {e.name} is ready ({int(time.time() - start) // 60 or '<1'} min)")
        else:
            reason = (out.strip().splitlines() or ["no reason given"])[-1][:160]
            say(f"  ✗ {e.name} didn't install: {reason}")
            failed.append(e.name)
        progress()
    wanted = [(c, e) for e in chosen if e.installed for c in e.missing_cores()]
    if wanted:
        say(f"Adding {len(wanted)} RetroArch core{'s' * (len(wanted) != 1)} (the part that plays each console)…")
        try:
            index = core_index()
        except InstallError as exc:
            say(f"  ✗ couldn't get the list of cores: {exc}")
            failed.append("RetroArch cores")
            index = None
        if index is not None:
            for core, e in wanted:
                try:
                    install_core(core, index)
                    say(f"  ✓ {e.cores[core]}")
                except (InstallError, OSError) as exc:
                    say(f"  ✗ {e.cores[core]}: {exc}")
                    failed.append(core)
                progress()
    say("")
    if failed:
        say(f"Not everything installed ({', '.join(failed)}). Try again; details are in {ESDE / 'logs/deck.log'}.")
        return 1
    left = [e.name for e in plan.needed() if not e.ready]
    say("All done. Your games are ready to play." if not left else
        f"All done. Your games still need {', '.join(left)}: press X on the Emulators screen to add {'it' if len(left) == 1 else 'them'}.")
    return 0


def remove(plan: Plan, app_id: str) -> int:
    exe = flatpak()
    e = next((x for x in plan.emulators if x.id == app_id), None)
    if not exe or e is None or not e.installed:
        say("That emulator isn't installed.")
        return 1
    say(f"Removing {e.name}… (your games, saves and settings stay)")
    rc, _ = _run([exe, "uninstall", "--user", "-y", "--noninteractive", app_id])
    if rc != 0:
        say(f"{e.name} couldn't be removed here. If it came with SteamOS or Discover installed it for everyone, "
            "remove it in Discover.")
        return 1
    say(f"✓ {e.name} removed.")
    return 0


def update(plan: Plan) -> int:
    exe = flatpak()
    if not exe:
        say("Flatpak isn't installed.")
        return 1
    ids = [e.id for e in plan.emulators if e.installed]
    if not ids:
        say("No emulators are installed yet.")
        return 0
    say(f"Checking {len(ids)} emulator{'s' * (len(ids) != 1)} for updates…")
    rc, _ = _run([exe, "update", "--user", "-y", "--noninteractive", *ids])
    say("  ✓ emulators are up to date" if rc == 0 else "  ✗ an update didn't finish (details in the log)")
    have = sorted(p.name[:-len("_libretro.so")] for p in CORES_DIR.glob("*_libretro.so")) if CORES_DIR.is_dir() else []
    if have:
        try:
            index = core_index()
            changed = [c for c in have if c in index and _crc(CORES_DIR / f"{c}_libretro.so") != index[c]]
            for c in changed:
                install_core(c, index)
            say(f"  ✓ {len(changed)} RetroArch core{'s' * (len(changed) != 1)} updated" if changed
                else "  ✓ RetroArch cores are up to date")
        except (InstallError, OSError) as exc:
            say(f"  ✗ couldn't check the RetroArch cores: {exc}")
            rc = rc or 1
    return 0 if rc == 0 else 1


def resolve(plan: Plan, names: list[str]) -> list[str]:
    """Flatpak ids or names (any case) → ids."""
    out = []
    for n in names:
        e = next((x for x in plan.emulators if n.lower() in (x.id.lower(), x.name.lower())), None)
        if e is not None:
            out.append(e.id)
    return out


def main(argv: list[str]) -> int:
    roms = Path(os.environ.get("ARCADIA_ROMS") or HOME / "ROMs")
    cmd, args = (argv[0] if argv else "plan"), argv[1:]
    plan = plan_from_disk(roms)
    if cmd == "plan":
        print("\n".join(plan_lines(plan)))
        return 0
    if cmd == "status":
        print(status_line(plan))
        return 0
    if cmd == "install":
        if args == ["--needed"]:
            ids = [e.id for e in plan.needed()]
            if not ids:
                say("Your games don't need anything yet: add some games first, or pick an emulator to install.")
                return 0
        else:
            ids = resolve(plan, args)
            if not ids:
                say("Nothing to install: those names weren't recognised.")
                return 1
        return install(plan, ids)
    if cmd == "remove" and len(args) == 1:
        return remove(plan, args[0])
    if cmd == "update":
        return update(plan)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
