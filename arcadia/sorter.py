"""Sort ROMs from an inbox (usually the Downloads folder) into the library.

For each file the sorter decides which system it belongs to, using three kinds of
evidence, strongest first:

1. The file's own header (iNES, GBA/GB logo, N64 magic, Sega header, SNES checksum,
   PSP/PlayStation disc markers, PBP contents). Zip files are opened and the ROM
   inside is checked the same way.
2. The file extension.
3. The file name ("... (GBC)", "Super Nintendo", ...), which is only a hint.

Each result has a confidence:

* CERTAIN: the header confirms the extension. Safe to move without asking.
* LIKELY:  the extension points to one system but the header couldn't confirm it.
* UNSURE:  the evidence is ambiguous or contradictory. The user must confirm.

Nothing here deletes or overwrites a file. Moves are journaled so an import can be undone.
"""

from __future__ import annotations

import errno
import json
import os
import re
import shlex
import shutil
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from arcadia.bundles import (
    SWITCH_EXTS,
    DiscInfo,
    merge_m3u_lines,
    parse_disc,
    parse_switch,
    write_m3u,
)
from arcadia.config import Config
from arcadia.discs import DiscGuess, sniff_chd, sniff_disc_image
from arcadia.folders import FOLDER_RULES, find_game_folder


class Confidence(Enum):
    CERTAIN = "certain"
    LIKELY = "likely"
    UNSURE = "unsure"


_RANK = {Confidence.CERTAIN: 0, Confidence.LIKELY: 1, Confidence.UNSURE: 2}

SYSTEM_LABELS = {
    "nes": "NES",
    "snes": "Super Nintendo",
    "n64": "Nintendo 64",
    "gc": "GameCube",
    "wii": "Wii",
    "wiiu": "Wii U",
    "switch": "Nintendo Switch",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "nds": "Nintendo DS",
    "n3ds": "Nintendo 3DS",
    "genesis": "Sega Genesis",
    "sms": "Master System",
    "gamegear": "Game Gear",
    "segacd": "Sega CD",
    "saturn": "Sega Saturn",
    "dreamcast": "Dreamcast",
    "psx": "PlayStation",
    "ps2": "PlayStation 2",
    "ps3": "PlayStation 3",
    "psp": "PSP",
    "xbox": "Xbox",
    "pcengine": "PC Engine",
    "neogeo": "Neo Geo",
    "arcade": "Arcade",
    "atari2600": "Atari 2600",
    "atari7800": "Atari 7800",
    "lynx": "Atari Lynx",
    "wonderswan": "WonderSwan",
    "ngp": "Neo Geo Pocket",
    "virtualboy": "Virtual Boy",
    "msx": "MSX",
    "amiga": "Amiga",
}

# Extensions that identify a system (or, for discs and generic formats, a short list of candidates).
EXT_SYSTEMS: dict[str, list[str]] = {
    ".nes": ["nes"],
    ".sfc": ["snes"],
    ".smc": ["snes"],
    ".gb": ["gb"],
    ".gbc": ["gbc"],
    ".gba": ["gba"],
    ".z64": ["n64"],
    ".n64": ["n64"],
    ".v64": ["n64"],
    ".md": ["genesis"],
    ".gen": ["genesis"],
    ".sms": ["sms"],
    ".gg": ["gamegear"],
    ".nds": ["nds"],
    ".dsi": ["nds"],
    ".3ds": ["n3ds"],
    ".cci": ["n3ds"],
    ".cxi": ["n3ds"],
    ".cia": ["n3ds"],
    ".3dsx": ["n3ds"],
    ".wux": ["wiiu"],
    ".wud": ["wiiu"],
    ".wua": ["wiiu"],
    ".rpx": ["wiiu"],
    ".gcm": ["gc"],
    ".wbfs": ["wii"],
    ".rvz": ["gc", "wii"],
    ".wia": ["gc", "wii"],
    ".gcz": ["gc", "wii"],
    ".ciso": ["gc", "wii"],
    ".pce": ["pcengine"],
    ".sgx": ["pcengine"],
    ".neo": ["neogeo"],
    ".a26": ["atari2600"],
    ".a78": ["atari7800"],
    ".lnx": ["lynx"],
    ".ws": ["wonderswan"],
    ".wsc": ["wonderswan"],
    ".ngp": ["ngp"],
    ".ngc": ["ngp"],
    ".vb": ["virtualboy"],
    ".mx1": ["msx"],
    ".mx2": ["msx"],
    ".rom": ["msx"],
    ".dsk": ["msx"],
    ".cas": ["msx"],
    ".adf": ["amiga"],
    ".ipf": ["amiga"],
    ".dms": ["amiga"],
    ".hdf": ["amiga"],
    ".lha": ["amiga"],
    ".zso": ["ps2"],
    ".xiso": ["xbox"],
    ".cso": ["psp", "ps2"],
    ".iso": ["ps2", "psx", "psp", "gc", "wii", "xbox", "ps3", "saturn", "segacd"],
    ".pbp": ["psp", "psx"],
    ".chd": ["psx", "ps2", "saturn", "segacd", "dreamcast", "pcengine", "psp", "arcade"],
    ".cue": ["psx", "ps2", "saturn", "segacd", "pcengine"],
    ".gdi": ["dreamcast"],
    ".cdi": ["dreamcast"],
    ".bin": ["genesis", "psx", "ps2", "saturn", "segacd", "atari2600"],
    ".nsp": ["switch"],
    ".xci": ["switch"],
    ".nsz": ["switch"],
    ".xcz": ["switch"],
}
# Cartridge-style files whose header can be checked.
CART_EXTS = {
    ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".z64", ".n64", ".v64", ".md", ".gen", ".sms", ".gg", ".bin",
    ".nds", ".dsi", ".3ds", ".cci", ".cxi", ".cia", ".3dsx", ".wux", ".wud", ".a78", ".lnx", ".ngp", ".ngc",
}
# Disc images, analysed by discs.py.
DISC_EXTS = {
    ".iso", ".cso", ".pbp", ".chd", ".bin", ".gcm", ".rvz", ".gcz", ".ciso", ".wia", ".wbfs", ".xiso", ".zso",
}
# Formats shared by too many things to trust on the extension alone: they need the name to say so.
WEAK_EXTS = {".bin", ".rom", ".dsk", ".cas"}
# Systems whose emulators open an .m3u playlist, so multi-disc games can be joined with one.
M3U_SYSTEMS = {"psx", "saturn", "segacd"}
PARTIAL_EXTS = {".part", ".crdownload", ".tmp", ".download", ".opdownload", ".filepart", ".aria2", ".!ut"}
UNREADABLE_ARCHIVES = {".7z", ".rar"}

CART_READ = 0x10200  # enough for every header except ExHiROM SNES
EXHIROM_READ = 0x410200
DISC_READ = 0x200000  # PSP discs list PSP_GAME near the start of the image

GBA_LOGO = bytes.fromhex("24FFAE51699AA221")
GB_LOGO = bytes.fromhex("CEED6666CC0D000B")
N64_MAGICS = {bytes.fromhex("80371240"), bytes.fromhex("37804012"), bytes.fromhex("40123780")}

# Name hints, longest phrases first so "game boy advance" wins over "game boy".
_HINT_PHRASES = [
    ("nintendo entertainment system", "nes"),
    ("nintendo switch", "switch"),
    ("playstation portable", "psp"),
    ("game boy advance", "gba"),
    ("gameboy advance", "gba"),
    ("game boy color", "gbc"),
    ("gameboy color", "gbc"),
    ("super nintendo", "snes"),
    ("super famicom", "snes"),
    ("neo geo pocket", "ngp"),
    ("nintendo gamecube", "gc"),
    ("sega dreamcast", "dreamcast"),
    ("virtual boy", "virtualboy"),
    ("nintendo 3ds", "n3ds"),
    ("nintendo 64", "n64"),
    ("nintendo ds", "nds"),
    ("sega saturn", "saturn"),
    ("master system", "sms"),
    ("playstation 1", "psx"),
    ("playstation 2", "ps2"),
    ("playstation 3", "ps3"),
    ("pc engine", "pcengine"),
    ("turbografx", "pcengine"),
    ("atari 2600", "atari2600"),
    ("atari 7800", "atari7800"),
    ("mega drive", "genesis"),
    ("megadrive", "genesis"),
    ("wonderswan", "wonderswan"),
    ("dreamcast", "dreamcast"),
    ("game cube", "gc"),
    ("gamecube", "gc"),
    ("playstation", "psx"),
    ("game gear", "gamegear"),
    ("gamegear", "gamegear"),
    ("sega cd", "segacd"),
    ("mega cd", "segacd"),
    ("neo geo", "neogeo"),
    ("neogeo", "neogeo"),
    ("game boy", "gb"),
    ("gameboy", "gb"),
    ("famicom", "nes"),
    ("genesis", "genesis"),
    ("saturn", "saturn"),
    ("arcade", "arcade"),
    ("wii u", "wiiu"),
    ("wiiu", "wiiu"),
    ("xbox", "xbox"),
    ("amiga", "amiga"),
    ("psone", "psx"),
    ("snes", "snes"),
    ("switch", "switch"),
    ("gbc", "gbc"),
    ("gba", "gba"),
    ("n64", "n64"),
    ("nds", "nds"),
    ("3ds", "n3ds"),
    ("sms", "sms"),
    ("psx", "psx"),
    ("ps1", "psx"),
    ("ps2", "ps2"),
    ("ps3", "ps3"),
    ("psp", "psp"),
    ("wii", "wii"),
    ("nes", "nes"),
    ("sfc", "snes"),
    ("nsw", "switch"),
    ("mame", "arcade"),
    ("msx", "msx"),
    ("lynx", "lynx"),
    ("gg", "gamegear"),
    ("gb", "gb"),
]


@dataclass
class Identification:
    system_id: str
    confidence: Confidence
    reason: str
    alternatives: list[str] = field(default_factory=list)  # other plausible systems, best first


# ----------------------------------------------------------------------------
# Name hints
# ----------------------------------------------------------------------------

def hint_systems(name: str, known: set[str]) -> list[str]:
    """Systems mentioned in a file name, e.g. 'Zelda (GBC).zip' -> ['gbc']."""
    text = " " + re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() + " "
    found: list[str] = []
    for phrase, system in _HINT_PHRASES:
        pattern = f" {phrase} "
        if pattern in text:
            text = text.replace(pattern, " ", 1)
            if system in known and system not in found:
                found.append(system)
    return found


# ----------------------------------------------------------------------------
# Header sniffing
# ----------------------------------------------------------------------------

def _read(path: Path, n: int, offset: int = 0) -> bytes:
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read(n)
    except OSError:
        return b""


def _sniff_snes(data: bytes, size: int) -> bool:
    """SNES headers carry a checksum and its complement that XOR to 0xFFFF."""
    copier = 512 if size % 1024 == 512 else 0
    for base in (0x7FC0, 0xFFC0, 0x40FFC0):
        o = base + copier
        if o + 0x20 > len(data):
            continue
        complement = data[o + 0x1C] | data[o + 0x1D] << 8
        checksum = data[o + 0x1E] | data[o + 0x1F] << 8
        mode = data[o + 0x15]
        if complement ^ checksum == 0xFFFF and (mode & 0xE0) == 0x20 and (mode & 0x0F) in (0, 1, 2, 3, 5):
            return True
    return False


def sniff_cartridge(data: bytes, size: int, ext: str) -> tuple[str | None, str]:
    """Identify a cartridge ROM from its header. Returns (system_id, evidence) or (None, '')."""
    if data[:4] == b"NES\x1a":
        return "nes", "iNES header"
    if len(data) > 0xB3 and data[4:12] == GBA_LOGO and data[0xB2] == 0x96:
        return "gba", "Game Boy Advance header"
    if data[:4] in N64_MAGICS:
        return "n64", "Nintendo 64 header"
    if len(data) > 0x150 and data[0x104:0x10C] == GB_LOGO:
        flag = data[0x143]
        if flag == 0xC0 or (flag == 0x80 and ext == ".gbc"):
            return "gbc", "Game Boy Color header"
        return "gb", "Game Boy header"
    if data[0x100:0x110].startswith((b"SEGA MEGA DRIVE", b"SEGA GENESIS", b"SEGA_MEGA DRIVE")):
        return "genesis", "Sega Mega Drive / Genesis header"
    for offset in (0x7FF0, 0x3FF0, 0x1FF0):
        if data[offset : offset + 8] == b"TMR SEGA" and len(data) > offset + 0xF:
            region = data[offset + 0xF] >> 4
            if region in (3, 4):
                return "sms", "Master System header"
            if region in (5, 6, 7):
                return "gamegear", "Game Gear header"
    if len(data) > 0x160 and data[0x15C:0x15E] == b"\x56\xcf":  # the Nintendo logo checksum, always 0xCF56
        return "nds", "Nintendo DS header"
    if data[0x100:0x104] in (b"NCSD", b"NCCH") or data[:4] == b"3DSX":
        return "n3ds", "Nintendo 3DS header"
    if data[:8] == bytes.fromhex("2020000000000000"):  # a CIA starts with its 0x2020-byte header size
        return "n3ds", "Nintendo 3DS CIA header"
    if data[:4] == b"WUX0" or data[:4] == b"WUP-":
        return "wiiu", "Wii U disc image"
    if data[1:10] == b"ATARI7800":
        return "atari7800", "Atari 7800 header"
    if data[:4] == b"LYNX":
        return "lynx", "Atari Lynx header"
    if data[:28] == b"COPYRIGHT BY SNK CORPORATION" or data[:27] == b"LICENSED BY SNK CORPORATION":
        return "ngp", "Neo Geo Pocket header"
    if _sniff_snes(data, size):
        return "snes", "SNES header checksum"
    return None, ""


def sniff_switch(data: bytes) -> tuple[str | None, str]:
    """NSP/NSZ files are PFS0 containers; XCI/XCZ carry a HEAD marker at 0x100."""
    if data[:4] == b"PFS0":
        return "switch", "Switch NSP container"
    if data[0x100:0x104] == b"HEAD":
        return "switch", "Switch XCI cartridge image"
    return None, ""


# ----------------------------------------------------------------------------
# Identification
# ----------------------------------------------------------------------------

def _label(system_id: str) -> str:
    return SYSTEM_LABELS.get(system_id, system_id)


def _join(systems: list[str]) -> str:
    return " or ".join(_label(s) for s in systems)


def _identify_rom(
    name: str,
    ext: str,
    size: int,
    read: Callable[[int], bytes],
    read_at: Callable[[int, int], bytes] | None,
    known: set[str],
) -> Identification | None:
    cands = [s for s in EXT_SYSTEMS.get(ext, []) if s in known]
    if not cands:
        return None
    hints = hint_systems(Path(name).stem, known)  # not the extension: ".nes" must not hint "nes"

    sniffed: str | None = None
    detail = ""
    ambiguous: list[str] = []
    if ext in CART_EXTS:
        n = EXHIROM_READ if size > 0x400000 and ext in (".sfc", ".smc") else CART_READ
        sniffed, detail = sniff_cartridge(read(n), size, ext)
    if ext in SWITCH_EXTS:
        sniffed, detail = sniff_switch(read(0x200))
    if sniffed is None and ext in DISC_EXTS:
        guess = sniff_chd(read, read_at) if ext == ".chd" else sniff_disc_image(read(DISC_READ), ext, read_at)
        sniffed, detail, ambiguous = guess.system, guess.detail, guess.candidates

    if sniffed is not None:
        if sniffed not in known:
            return None  # the system was removed from the user's setup
        if sniffed in cands:
            return Identification(sniffed, Confidence.CERTAIN, detail)
        alts = [c for c in cands if c != sniffed]
        return Identification(
            sniffed,
            Confidence.UNSURE,
            f"{detail}, but the {ext} extension suggests {_join(cands)}",
            alts,
        )

    # The contents narrowed it down without settling it (a CHD that is a CD, a PlayStation disc that
    # could be PS1 or PS2, ...): keep only the systems the user has, hints first.
    if ambiguous:
        narrowed = [c for c in ambiguous if c in known and c in cands] or cands
        ordered = [c for c in narrowed if c in hints] + [c for c in narrowed if c not in hints]
        if len(ordered) == 1 and ordered[0] in cands:
            return Identification(ordered[0], Confidence.LIKELY, f"{detail}; the header doesn't confirm it")
        return Identification(ordered[0], Confidence.UNSURE, f"{detail} ({_join(ordered)})", ordered[1:])

    # Nothing verified: fall back to the extension and the name.
    if ext in WEAK_EXTS:
        if not hints:
            return None  # a stray .bin or .rom is not necessarily a game
        pick = [h for h in hints if h in cands]
        if not pick:
            return None
        return Identification(pick[0], Confidence.UNSURE, f"only the name suggests {_label(pick[0])}", pick[1:])
    if len(cands) == 1:
        if hints and cands[0] not in hints:
            return Identification(
                cands[0],
                Confidence.UNSURE,
                f"{ext} is normally {_label(cands[0])}, but the name mentions {_join(hints)}",
                [h for h in hints if h != cands[0]],
            )
        return Identification(
            cands[0], Confidence.LIKELY, f"{ext} is a {_label(cands[0])} extension; the header couldn't be verified"
        )
    ordered = [c for c in cands if c in hints] + [c for c in cands if c not in hints]
    return Identification(ordered[0], Confidence.UNSURE, f"{ext} files can be {_join(cands)}", ordered[1:])


def _identify_zip(path: Path, known: set[str]) -> Identification | None:
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return None
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir() and not Path(i.filename).name.startswith(".")]
        roms = [i for i in entries if Path(i.filename).suffix.lower() in EXT_SYSTEMS]
        if any(Path(i.filename).suffix.lower() == ".cue" for i in roms):
            roms = [i for i in roms if Path(i.filename).suffix.lower() != ".bin"]  # tracks belong to the cue

        results: list[tuple[str, Identification]] = []
        for info in roms:
            def read(n: int, info=info) -> bytes:
                try:
                    with zf.open(info) as fh:
                        return fh.read(n)
                except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
                    return b""

            member = Path(info.filename)
            ident = _identify_rom(member.name, member.suffix.lower(), info.file_size, read, None, known)
            if ident is not None:
                results.append((member.name, ident))
        if not results:
            # Nothing inside is recognisable (arcade sets are just zips of unlabelled files), so the
            # name is all there is to go on.
            hints = hint_systems(path.stem, known)
            if not hints:
                return None
            return Identification(
                hints[0],
                Confidence.UNSURE,
                f"the zip's contents can't be recognised; the name suggests {_join(hints)}",
                hints[1:],
            )

    systems: list[str] = []
    for _name, ident in results:
        if ident.system_id not in systems:
            systems.append(ident.system_id)
    first_name, first = results[0]
    if len(systems) > 1:
        return Identification(systems[0], Confidence.UNSURE, "the zip contains ROMs for several systems", systems[1:])
    worst = max((i.confidence for _n, i in results), key=lambda c: _RANK[c])
    if len(results) > 1:
        return Identification(
            systems[0],
            Confidence.UNSURE,
            f"the zip holds {len(results)} ROMs and Arcadia would treat it as one game",
        )
    return Identification(systems[0], worst, f"inside the zip, {first_name}: {first.reason}", first.alternatives)


def _identify_unreadable_archive(path: Path, known: set[str]) -> Identification | None:
    hints = hint_systems(path.stem, known)
    if not hints:
        return None
    return Identification(
        hints[0],
        Confidence.UNSURE,
        f"{path.suffix.lower()} archives can't be inspected; the name suggests {_join(hints)}",
        hints[1:],
    )


def identify(path: Path, known: set[str]) -> Identification | None:
    """Decide which system a single file belongs to, or None if it isn't a ROM we recognise."""
    ext = path.suffix.lower()
    if ext in PARTIAL_EXTS:
        return None
    if ext == ".zip":
        return _identify_zip(path, known)
    if ext in UNREADABLE_ARCHIVES:
        return _identify_unreadable_archive(path, known)
    if ext not in EXT_SYSTEMS:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return _identify_rom(
        path.name,
        ext,
        size,
        lambda n: _read(path, n),
        lambda offset, n: _read(path, n, offset),
        known,
    )


_CUE_FILE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE | re.MULTILINE)


def cue_files(cue: Path) -> list[Path]:
    """Files a .cue sheet refers to (in the same folder), whether or not they exist."""
    try:
        text = cue.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [cue.parent / (m.group(1) or m.group(2)) for m in _CUE_FILE.finditer(text)]


def gdi_files(gdi: Path) -> list[Path]:
    """Track files a Dreamcast .gdi sheet lists (first line is the track count)."""
    try:
        lines = gdi.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    tracks = []
    for line in lines[1:]:
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        if len(fields) >= 6:  # number, start, type, sector size, file name, offset
            tracks.append(gdi.parent / fields[4])
    return tracks


def _sheet_tracks(sheet: Path) -> list[Path]:
    return cue_files(sheet) if sheet.suffix.lower() == ".cue" else gdi_files(sheet)


def _identify_sheet(sheet: Path, tracks: list[Path], known: set[str]) -> Identification | None:
    """A .cue or .gdi sheet: identify the disc from its track files."""
    ext = sheet.suffix.lower()
    cands = [s for s in EXT_SYSTEMS[ext] if s in known]
    if not cands:
        return None
    hints = hint_systems(sheet.stem, known)
    missing = [t.name for t in tracks if not t.exists()]
    if not tracks or missing:
        return Identification(
            cands[0],
            Confidence.UNSURE,
            f"the {ext[1:]} sheet refers to files that aren't in this folder: " + ", ".join(missing or ["none listed"]),
            cands[1:],
        )

    guess = DiscGuess()
    # A cue's first track is the data track. A gdi mixes audio and data, so look at them all (briefly).
    probes = tracks[:1] if ext == ".cue" else tracks
    size = DISC_READ if ext == ".cue" else 0x10000
    for track in probes:
        found = sniff_disc_image(_read(track, size), ".bin", None)
        if found.system or found.candidates:
            guess = found
            break

    if guess.system:
        if guess.system not in known:
            return None
        if guess.system in cands:
            return Identification(guess.system, Confidence.CERTAIN, guess.detail)
        return Identification(
            guess.system, Confidence.UNSURE, f"{guess.detail}, but a {ext} sheet is normally {_join(cands)}", cands
        )
    if guess.candidates:
        narrowed = [c for c in guess.candidates if c in known and c in cands] or cands
        ordered = [c for c in narrowed if c in hints] + [c for c in narrowed if c not in hints]
        if len(ordered) == 1:
            return Identification(ordered[0], Confidence.LIKELY, f"{guess.detail}; the data doesn't confirm it")
        return Identification(ordered[0], Confidence.UNSURE, f"{guess.detail} ({_join(ordered)})", ordered[1:])
    if ext == ".gdi":
        return Identification("dreamcast", Confidence.LIKELY, "a .gdi sheet is a Dreamcast format; its data track couldn't be verified")
    ordered = [c for c in cands if c in hints] + [c for c in cands if c not in hints]
    return Identification(
        ordered[0], Confidence.UNSURE, f"disc image not recognised (could be {_join(cands)})", ordered[1:]
    )


# ----------------------------------------------------------------------------
# Plans
# ----------------------------------------------------------------------------

@dataclass
class PlanItem:
    source: Path
    system_id: str
    confidence: Confidence
    reason: str
    alternatives: list[str]
    companions: list[Path] = field(default_factory=list)  # files that must travel with source (cue tracks)
    destination: Path = field(default_factory=Path)
    exists: bool = False  # something already sits at the destination
    manual: bool = False  # the user chose or confirmed the system
    kind: str = "single"  # single | disc_set (discs joined by a playlist) | bundle (game + updates/DLC)
    title: str = ""  # disc sets: the game title, used for the folder and playlist names
    discs: list[Path] = field(default_factory=list)  # disc sets: the main disc files, in play order
    merge: bool = False  # disc sets: a playlist for this game already exists, so discs are added to it
    detail: str = ""  # short extra info for the UI: "3 discs", "+1 update, 2 DLC"

    @property
    def sources(self) -> list[Path]:
        return [self.source, *self.companions]

    @property
    def label(self) -> str:
        return self.title if self.kind == "disc_set" else self.source.name

    def dest_label(self) -> str:
        """Where this goes, relative to the ROM root: 'psx/Game Title/' or 'nes/'."""
        if self.kind == "disc_set":
            return f"{self.destination.parent.name}/{self.title}/"
        return self.destination.parent.name + "/"

    def retarget(self, config: Config, system_id: str) -> None:
        """Point this item at a system (e.g. the user picked a different one)."""
        self.system_id = system_id
        folder = config.rom_root_path / config.system(system_id).folder
        if self.kind == "disc_set":
            self.destination = folder / f"{self.title}.m3u"
            disc_dir = folder / self.title
            self.exists = any((disc_dir / p.name).exists() for p in self.sources)
            self.merge = self.destination.exists()
        else:
            self.destination = folder / self.source.name
            self.exists = any((folder / p.name).exists() for p in self.sources)


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    waiting: list[Path] = field(default_factory=list)  # still being written, look again later
    ignored: list[Path] = field(default_factory=list)  # not recognisable as ROMs


def destination_for(config: Config, system_id: str, source: Path) -> Path:
    system = config.system(system_id)
    return config.rom_root_path / system.folder / source.name


def build_plan(inbox: Path, config: Config, now: float | None = None, min_age: float = 5.0) -> Plan:
    """Look at the files directly inside inbox and work out where each ROM belongs.

    Files modified within min_age seconds are treated as still downloading.
    """
    plan = Plan()
    if not inbox.is_dir():
        return plan
    now = time.time() if now is None else now
    known = {s.id for s in config.systems}
    files = sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith("."))

    def young(paths: list[Path]) -> bool:
        for p in paths:
            try:
                if now - p.stat().st_mtime < min_age:
                    return True
            except OSError:
                return True
        return False

    track_files: set[Path] = set()
    sheet_tracks: dict[Path, list[Path]] = {}
    for p in files:
        if p.suffix.lower() in (".cue", ".gdi"):
            tracks = [t for t in _sheet_tracks(p) if t.parent == p.parent]
            sheet_tracks[p] = tracks
            track_files.update(tracks)

    for p in files:
        if p in track_files or p.suffix.lower() in PARTIAL_EXTS:
            continue
        companions: list[Path] = []
        if p in sheet_tracks:
            companions = [t for t in sheet_tracks[p] if t.exists()]
            if young([p, *companions]):
                plan.waiting.append(p)
                continue
            ident = _identify_sheet(p, sheet_tracks[p], known)
        else:
            if young([p]):
                plan.waiting.append(p)
                continue
            ident = identify(p, known)
        if ident is None:
            plan.ignored.append(p)
            continue
        item = PlanItem(
            source=p,
            system_id=ident.system_id,
            confidence=ident.confidence,
            reason=ident.reason,
            alternatives=ident.alternatives,
            companions=companions,
        )
        item.retarget(config, ident.system_id)
        plan.items.append(item)

    # Games that are whole folders (PS3 and Wii U dumps) are moved as a unit.
    for folder in sorted(p for p in inbox.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for system_id in FOLDER_RULES:
            if system_id not in known:
                continue
            hit = find_game_folder(folder, system_id)
            if hit is None:
                continue
            if now - _newest_mtime(folder, now) < min_age:
                plan.waiting.append(folder)
                break
            marker = hit[0].relative_to(folder).as_posix()
            item = PlanItem(
                source=folder,
                system_id=system_id,
                confidence=Confidence.CERTAIN,
                reason=f"a {_label(system_id)} game folder ({marker} found)",
                alternatives=[],
                detail="game folder",
            )
            item.retarget(config, system_id)
            plan.items.append(item)
            break

    plan.items = _group_switch(_group_discs(plan.items, config), config)
    return plan


def _newest_mtime(folder: Path, now: float, limit: int = 20_000) -> float:
    """Most recent modification time inside a folder (stops looking after `limit` files).
    A folder that can't be read counts as just modified, so it's left alone."""
    newest = 0.0
    seen = 0
    for dirpath, _dirnames, filenames in os.walk(folder):
        try:
            newest = max(newest, os.stat(dirpath).st_mtime)
            for name in filenames:
                seen += 1
                if seen > limit:
                    return newest
                newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
        except OSError:
            return now
    return newest


# ----------------------------------------------------------------------------
# Games made of several files
# ----------------------------------------------------------------------------

_SET_DISC_EXTS = {".cue", ".chd", ".iso", ".pbp", ".cso"}


def _worst(items: list[PlanItem]) -> Confidence:
    return max((i.confidence for i in items), key=lambda c: _RANK[c])


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _make_disc_set(members: list[PlanItem], infos: list[DiscInfo], config: Config) -> PlanItem:
    order = sorted(range(len(members)), key=lambda i: infos[i].number)
    members = [members[i] for i in order]
    infos = [infos[i] for i in order]
    numbers = [i.number for i in infos]
    total = max((i.total for i in infos if i.total), default=None)
    missing = [n for n in range(1, (total or max(numbers)) + 1) if n not in numbers]
    title = infos[0].base
    confidence = _worst(members)
    reason = f"{_plural(len(members), 'disc')} of {title}: {members[0].reason}"
    if missing:
        confidence = Confidence.UNSURE
        reason = (
            f"found {_plural(len(members), 'disc')} of {title} but not disc "
            + ", ".join(str(n) for n in missing)
            + "; the playlist would be incomplete"
        )
    combined = PlanItem(
        source=members[0].source,
        system_id=members[0].system_id,
        confidence=confidence,
        reason=reason,
        alternatives=members[0].alternatives,
        companions=[m.source for m in members[1:]] + [c for m in members for c in m.companions],
        kind="disc_set",
        title=title,
        discs=[m.source for m in members],
        detail=_plural(len(members), "disc"),
    )
    combined.retarget(config, combined.system_id)
    return combined


def _lone_disc(item: PlanItem, info: DiscInfo, config: Config) -> PlanItem:
    """One disc of a set arrived by itself. If the library already has that game's playlist,
    add the disc to it; otherwise move it as an ordinary game but say what it looks like."""
    folder = config.rom_root_path / config.system(item.system_id).folder
    if (folder / f"{info.base}.m3u").exists():
        combined = PlanItem(
            source=item.source,
            system_id=item.system_id,
            confidence=item.confidence,
            reason=f"disc {info.number} of {info.base}, added to its existing playlist",
            alternatives=item.alternatives,
            companions=item.companions,
            kind="disc_set",
            title=info.base,
            discs=[item.source],
            detail=f"adds disc {info.number}",
        )
        combined.retarget(config, item.system_id)
        return combined
    if item.confidence is Confidence.CERTAIN:
        item.confidence = Confidence.LIKELY
    item.reason += f"; this looks like disc {info.number} of a multi-disc game and the other discs aren't in this folder"
    return item


def _group_discs(items: list[PlanItem], config: Config) -> list[PlanItem]:
    parsed: dict[int, DiscInfo] = {}
    groups: dict[tuple[str, str], list[PlanItem]] = {}
    for it in items:
        if it.kind != "single" or it.system_id not in M3U_SYSTEMS or it.source.suffix.lower() not in _SET_DISC_EXTS:
            continue
        info = parse_disc(it.source.stem)
        if info is not None:
            parsed[id(it)] = info
            groups.setdefault((it.system_id, info.base.lower()), []).append(it)

    replacement: dict[int, PlanItem | None] = {}
    for members in groups.values():
        infos = [parsed[id(m)] for m in members]
        numbers = [i.number for i in infos]
        if len(members) >= 2 and len(set(numbers)) == len(numbers):
            replacement[id(members[0])] = _make_disc_set(members, infos, config)
            for other in members[1:]:
                replacement[id(other)] = None
        elif len(members) == 1:
            replacement[id(members[0])] = _lone_disc(members[0], infos[0], config)
        # two files claiming the same disc number are left as they are, for the user to look at

    out: list[PlanItem] = []
    for it in items:
        if id(it) not in replacement:
            out.append(it)
        elif replacement[id(it)] is not None:
            out.append(replacement[id(it)])
    return out


def _library_has_switch_base(config: Config, group: int) -> bool:
    try:
        folder = config.rom_root_path / config.system("switch").folder
    except KeyError:
        return False
    if not folder.is_dir():
        return False
    for path in folder.rglob("*"):
        if path.suffix.lower() in SWITCH_EXTS:
            info = parse_switch(path.name)
            if info is not None and info.role == "base" and info.group == group:
                return True
    return False


def _group_switch(items: list[PlanItem], config: Config) -> list[PlanItem]:
    """Bundle a Switch game with the updates and DLC that arrived with it, and warn about
    updates or DLC that have no base game yet."""
    infos = {}
    groups: dict[int, list[PlanItem]] = {}
    for it in items:
        if it.kind != "single" or it.system_id != "switch" or it.source.suffix.lower() not in SWITCH_EXTS:
            continue
        info = parse_switch(it.source.name)
        if info is not None:
            infos[id(it)] = info
            groups.setdefault(info.group, []).append(it)

    replacement: dict[int, PlanItem | None] = {}
    for group, members in groups.items():
        bases = [m for m in members if infos[id(m)].role == "base"]
        updates = [m for m in members if infos[id(m)].role == "update"]
        dlcs = [m for m in members if infos[id(m)].role == "dlc"]
        has_base = bool(bases) or _library_has_switch_base(config, group)
        note = "" if has_base else "; its base game isn't in your library yet"

        if len(members) == 1:
            only = members[0]
            if infos[id(only)].role != "base":
                if not has_base and only.confidence is Confidence.CERTAIN:
                    only.confidence = Confidence.LIKELY
                kind = "an update" if infos[id(only)].role == "update" else "DLC"
                only.reason += f"; this is {kind}" + (note if note else " for a game already in your library")
            continue

        lead = (bases or members)[0]
        rest = [m for m in members if m is not lead]
        parts = []
        if updates:
            parts.append(f"+{_plural(len(updates), 'update')}")
        if dlcs:
            parts.append(f"{len(dlcs)} DLC")
        if len(bases) > 1:
            parts.append(f"{len(bases)} base files")
        confidence = _worst(members)
        if not has_base and confidence is Confidence.CERTAIN:
            confidence = Confidence.LIKELY
        combined = PlanItem(
            source=lead.source,
            system_id=lead.system_id,
            confidence=confidence,
            reason=f"{lead.reason}; bundled with its {' and '.join(p.lstrip('+') for p in parts)}{note}",
            alternatives=lead.alternatives,
            companions=[*lead.companions, *[m.source for m in rest], *[c for m in rest for c in m.companions]],
            kind="bundle",
            detail=", ".join(parts),
        )
        combined.retarget(config, lead.system_id)
        replacement[id(members[0])] = combined
        for other in members[1:]:
            replacement[id(other)] = None

    out: list[PlanItem] = []
    for it in items:
        if id(it) not in replacement:
            out.append(it)
        elif replacement[id(it)] is not None:
            out.append(replacement[id(it)])
    return out


# ----------------------------------------------------------------------------
# Moving files safely, with an undo journal
# ----------------------------------------------------------------------------

class SortError(Exception):
    pass


@dataclass(frozen=True)
class Move:
    src: str
    dst: str


def unique_destination(path: Path) -> Path:
    """'Game.nes' -> 'Game (2).nes' (first name that doesn't exist)."""
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _tree_stats(path: Path) -> tuple[int, int]:
    """(number of files, total bytes) in a folder."""
    count = size = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            count += 1
            size += os.path.getsize(os.path.join(dirpath, name))
    return count, size


def _copy_folder_verified(src: Path, dst: Path) -> None:
    """Copy a folder to another drive, check the copy, then (and only then) remove the original."""
    partial = dst.with_name(dst.name + ".arcadia-part")
    try:
        shutil.copytree(src, partial, symlinks=True)
        if _tree_stats(partial) != _tree_stats(src):
            raise SortError(f"copy of {src.name} was incomplete")
        os.replace(partial, dst)
    except (OSError, shutil.Error) as exc:
        shutil.rmtree(partial, ignore_errors=True)
        raise SortError(f"could not copy {src.name}: {getattr(exc, 'strerror', None) or exc}") from exc
    except SortError:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    try:
        shutil.rmtree(src)
    except OSError as exc:
        raise SortError(f"{src.name} was copied but the original could not be removed: {exc.strerror or exc}") from exc


def safe_move(src: Path, dst: Path) -> None:
    """Move a file or folder without ever overwriting. Across filesystems the copy is verified
    before the original is removed."""
    if dst.exists():
        raise SortError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise SortError(f"could not move {src.name}: {exc.strerror or exc}") from exc
    if src.is_dir():
        _copy_folder_verified(src, dst)
        return
    partial = dst.with_name(dst.name + ".arcadia-part")
    try:
        shutil.copy2(src, partial)
        if partial.stat().st_size != src.stat().st_size:
            raise SortError(f"copy of {src.name} was incomplete")
        os.replace(partial, dst)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise SortError(f"could not copy {src.name}: {exc.strerror or exc}") from exc
    except SortError:
        partial.unlink(missing_ok=True)
        raise
    src.unlink()


class Journal:
    """Record of moves, so the last import can be undone."""

    MAX_BATCHES = 50

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, batches: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(batches[-self.MAX_BATCHES :], indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def record(self, moves: list[Move], created: list[str] | None = None, restore: dict[str, str] | None = None) -> None:
        """created: files/folders this import made (a new playlist and its folder).
        restore: playlists it edited, mapped to their previous text."""
        if not moves:
            return
        batches = self._load()
        batches.append(
            {
                "time": time.time(),
                "moves": [{"src": m.src, "dst": m.dst} for m in moves],
                "created": list(created or []),
                "restore": dict(restore or {}),
            }
        )
        self._save(batches)

    def can_undo(self) -> bool:
        return bool(self._load())

    def last_count(self) -> int:
        batches = self._load()
        return len(batches[-1]["moves"]) if batches else 0

    def undo_last(self) -> tuple[int, list[str]]:
        """Move the last batch back. Returns (files restored, problems)."""
        batches = self._load()
        if not batches:
            return 0, []
        batch = batches.pop()
        restored = 0
        problems: list[str] = []
        for m in reversed(batch["moves"]):
            src, dst = Path(m["src"]), Path(m["dst"])
            if not dst.exists():
                problems.append(f"{dst.name} is no longer in the library")
            elif src.exists():
                problems.append(f"{src.name} already exists in the downloads folder")
            else:
                try:
                    safe_move(dst, src)
                    restored += 1
                except SortError as exc:
                    problems.append(str(exc))
        for path, text in batch.get("restore", {}).items():  # playlists we added discs to
            try:
                Path(path).write_text(text, encoding="utf-8")
            except OSError as exc:
                problems.append(f"could not restore {Path(path).name}: {exc.strerror or exc}")
        for path in batch.get("created", []):  # playlists and folders we made (folders last)
            p = Path(path)
            try:
                if p.is_file():
                    p.unlink()
            except OSError as exc:
                problems.append(f"could not remove {p.name}: {exc.strerror or exc}")
        for path in reversed(batch.get("created", [])):
            p = Path(path)
            if p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    problems.append(f"{p.name} was left in place because it isn't empty")
        self._save(batches)
        return restored, problems


@dataclass
class ApplyResult:
    moved: list[PlanItem] = field(default_factory=list)
    skipped: list[tuple[PlanItem, str]] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    restore: dict[str, str] = field(default_factory=dict)


def _apply_disc_set(item: PlanItem, result: ApplyResult) -> None:
    """Move a set's discs into '<system folder>/<title>/' and write (or extend) '<title>.m3u'."""
    playlist = item.destination
    disc_dir = playlist.parent / item.title
    pairs = []
    for src in item.sources:
        dst = disc_dir / src.name
        if dst.exists():
            result.skipped.append((item, f"{src.name} already exists in the library"))
            return
        pairs.append((src, dst))

    made_dir = not disc_dir.exists()
    done: list[Move] = []

    def roll_back() -> None:
        for m in reversed(done):  # put everything back, including half a set
            try:
                safe_move(Path(m.dst), Path(m.src))
            except SortError:
                pass
        if made_dir:
            try:
                disc_dir.rmdir()
            except OSError:
                pass

    try:
        for src, dst in pairs:
            safe_move(src, dst)
            done.append(Move(str(src), str(dst)))
        previous = None
        existing: list[str] = []
        if playlist.exists():
            previous = playlist.read_text(encoding="utf-8", errors="replace")
            existing = [ln.strip() for ln in previous.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        write_m3u(playlist, merge_m3u_lines(existing, [f"{item.title}/{d.name}" for d in item.discs]))
    except (SortError, OSError) as exc:
        roll_back()
        result.skipped.append((item, str(exc)))
        return

    if previous is None:
        result.created.append(str(playlist))
    else:
        result.restore[str(playlist)] = previous
    if made_dir:
        result.created.append(str(disc_dir))
    result.moved.append(item)
    result.moves.extend(done)


def apply_plan(items: list[PlanItem], journal: Journal, keep_both: bool = False) -> ApplyResult:
    """Move the given items. Existing files are never overwritten: they are skipped, or
    (with keep_both, single files only) the incoming file is renamed 'Name (2).ext'."""
    result = ApplyResult()
    for item in items:
        if item.kind == "disc_set":
            _apply_disc_set(item, result)
            continue
        pairs: list[tuple[Path, Path]] = []
        dest_dir = item.destination.parent
        for src in item.sources:
            dst = dest_dir / src.name
            if dst.exists():
                if keep_both and not item.companions:
                    dst = unique_destination(dst)
                else:
                    pairs = []
                    result.skipped.append((item, f"{src.name} already exists in the library"))
                    break
            pairs.append((src, dst))
        if not pairs:
            continue
        done: list[Move] = []
        try:
            for src, dst in pairs:
                safe_move(src, dst)
                done.append(Move(str(src), str(dst)))
        except SortError as exc:
            for m in reversed(done):  # don't leave half a disc image behind
                try:
                    safe_move(Path(m.dst), Path(m.src))
                except SortError:
                    pass
            result.skipped.append((item, str(exc)))
            continue
        result.moved.append(item)
        result.moves.extend(done)
    journal.record(result.moves, result.created, result.restore)
    return result
