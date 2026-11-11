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
import shutil
import struct
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from arcadia.config import Config


class Confidence(Enum):
    CERTAIN = "certain"
    LIKELY = "likely"
    UNSURE = "unsure"


_RANK = {Confidence.CERTAIN: 0, Confidence.LIKELY: 1, Confidence.UNSURE: 2}

SYSTEM_LABELS = {
    "nes": "NES",
    "snes": "Super Nintendo",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "n64": "Nintendo 64",
    "genesis": "Sega Genesis",
    "sms": "Master System",
    "gamegear": "Game Gear",
    "psx": "PlayStation",
    "psp": "PSP",
}

# Extensions that identify a system (or, for discs, a short list of candidates).
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
    ".cso": ["psp"],
    ".iso": ["psp", "psx"],
    ".pbp": ["psp", "psx"],
    ".chd": ["psx", "psp"],
    ".cue": ["psx"],
    ".bin": ["genesis", "psx"],
}
CART_EXTS = {".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".z64", ".n64", ".v64", ".md", ".gen", ".sms", ".gg", ".bin"}
DISC_EXTS = {".iso", ".cso", ".pbp", ".chd", ".cue", ".bin"}
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
    ("playstation portable", "psp"),
    ("game boy advance", "gba"),
    ("gameboy advance", "gba"),
    ("game boy color", "gbc"),
    ("gameboy color", "gbc"),
    ("super nintendo", "snes"),
    ("super famicom", "snes"),
    ("nintendo 64", "n64"),
    ("master system", "sms"),
    ("playstation 1", "psx"),
    ("mega drive", "genesis"),
    ("megadrive", "genesis"),
    ("playstation", "psx"),
    ("game gear", "gamegear"),
    ("gamegear", "gamegear"),
    ("game boy", "gb"),
    ("gameboy", "gb"),
    ("famicom", "nes"),
    ("genesis", "genesis"),
    ("psone", "psx"),
    ("snes", "snes"),
    ("gbc", "gbc"),
    ("gba", "gba"),
    ("n64", "n64"),
    ("sms", "sms"),
    ("psx", "psx"),
    ("ps1", "psx"),
    ("psp", "psp"),
    ("nes", "nes"),
    ("sfc", "snes"),
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
    if _sniff_snes(data, size):
        return "snes", "SNES header checksum"
    return None, ""


def sniff_disc(data: bytes, read_at: Callable[[int, int], bytes] | None) -> tuple[str | None, str]:
    """Identify a disc image or PBP. Returns (system_id, evidence) or (None, '')."""
    if data[:4] in (b"CISO", b"ZISO"):
        return "psp", "compressed PSP disc (CISO)"
    if data[:4] == b"\x00PBP" and read_at is not None and len(data) >= 40:
        (psar,) = struct.unpack_from("<I", data, 36)
        marker = read_at(psar, 8) if psar else b""
        if marker == b"PSISOIMG":
            return "psx", "PBP containing a PlayStation disc"
        if marker == b"NPUMDIMG":
            return "psp", "PBP containing a PSP disc"
        return None, ""
    if b"PSP_GAME" in data:
        return "psp", "PSP disc (PSP_GAME folder)"
    head = data[:0x10000]
    if b"CD001" in head and b"PLAYSTATION" in head:
        return "psx", "PlayStation disc"
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
    if ext in CART_EXTS:
        n = EXHIROM_READ if size > 0x400000 and ext in (".sfc", ".smc") else CART_READ
        sniffed, detail = sniff_cartridge(read(n), size, ext)
    if sniffed is None and ext in DISC_EXTS and ext != ".cue":
        sniffed, detail = sniff_disc(read(DISC_READ), read_at)

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

    # Nothing verified: fall back to the extension and the name.
    if ext == ".bin":
        if not hints:
            return None  # a stray .bin is not necessarily a ROM
        pick = [h for h in hints if h in cands]
        if not pick:
            return None
        return Identification(pick[0], Confidence.UNSURE, f"only the name suggests {_label(pick[0])}", pick[1:])
    if ext == ".cue":
        return Identification(
            cands[0], Confidence.UNSURE, "disc images can't be verified without their data files", cands[1:]
        )
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
            return None

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


def _identify_cue(cue: Path, tracks: list[Path], known: set[str]) -> Identification | None:
    if "psx" not in known:
        return None
    missing = [t.name for t in tracks if not t.exists()]
    if not tracks or missing:
        return Identification(
            "psx", Confidence.UNSURE, "the cue sheet refers to files that aren't in this folder: " + ", ".join(missing or ["none listed"])
        )
    sniffed, detail = sniff_disc(_read(tracks[0], DISC_READ), None)
    if sniffed == "psx":
        return Identification("psx", Confidence.CERTAIN, detail)
    if sniffed == "psp":
        return Identification("psp", Confidence.UNSURE, detail + ", but cue/bin images are normally PlayStation", ["psx"])
    return Identification("psx", Confidence.UNSURE, "disc image not recognised (could be another disc-based system)")


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

    @property
    def sources(self) -> list[Path]:
        return [self.source, *self.companions]

    def retarget(self, config: Config, system_id: str) -> None:
        """Point this item at a system (e.g. the user picked a different one)."""
        self.system_id = system_id
        self.destination = destination_for(config, system_id, self.source)
        self.exists = any(
            (self.destination.parent / p.name).exists() for p in self.sources
        )


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
    cue_tracks: dict[Path, list[Path]] = {}
    for p in files:
        if p.suffix.lower() == ".cue":
            tracks = [t for t in cue_files(p) if t.parent == p.parent]
            cue_tracks[p] = tracks
            track_files.update(tracks)

    for p in files:
        if p in track_files or p.suffix.lower() in PARTIAL_EXTS:
            continue
        companions: list[Path] = []
        if p in cue_tracks:
            companions = [t for t in cue_tracks[p] if t.exists()]
            if young([p, *companions]):
                plan.waiting.append(p)
                continue
            ident = _identify_cue(p, cue_tracks[p], known)
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
    return plan


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


def safe_move(src: Path, dst: Path) -> None:
    """Move a file without ever overwriting. Across filesystems the copy is verified
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

    def record(self, moves: list[Move]) -> None:
        if not moves:
            return
        batches = self._load()
        batches.append({"time": time.time(), "moves": [{"src": m.src, "dst": m.dst} for m in moves]})
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
        self._save(batches)
        return restored, problems


@dataclass
class ApplyResult:
    moved: list[PlanItem] = field(default_factory=list)
    skipped: list[tuple[PlanItem, str]] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)


def apply_plan(items: list[PlanItem], journal: Journal, keep_both: bool = False) -> ApplyResult:
    """Move the given items. Existing files are never overwritten: they are skipped, or
    (with keep_both, single files only) the incoming file is renamed 'Name (2).ext'."""
    result = ApplyResult()
    for item in items:
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
    journal.record(result.moves)
    return result
