"""Identify disc images from their contents.

The goal is to be right or to say "I can't tell", never to guess confidently. The key
case is PlayStation: PS1 and PS2 discs both carry a "PLAYSTATION" marker, so the only
reliable way to tell them apart is to read SYSTEM.CNF from the disc's ISO 9660 file system
(PS1 boots with "BOOT = ...", PS2 with "BOOT2 = ...").

Everything works on a prefix of the file (the first couple of megabytes) plus an optional
"read at offset" function, so it also works on images that are compressed or inside a zip.
"""

from __future__ import annotations

import re
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

SECTOR = 2048
# (bytes per sector on disk, offset of the 2048 data bytes inside it): plain ISO, MODE1/2352, MODE2/2352
LAYOUTS = ((2048, 0), (2352, 16), (2352, 24))

GC_MAGIC = bytes.fromhex("C2339F3D")  # at 0x1C of a GameCube disc
WII_MAGIC = bytes.fromhex("5D1C9EA3")  # at 0x18 of a Wii disc
XBOX_MAGIC = b"MICROSOFT*XBOX*MEDIA"  # at 0x10000 of an Xbox disc

SectorReader = Callable[[int], bytes]
ReadAt = Callable[[int, int], bytes]


@dataclass
class DiscGuess:
    system: str | None = None  # set only when the contents settle it
    candidates: list[str] = field(default_factory=list)  # plausible systems when they don't
    detail: str = ""  # what was seen, for the user


# ----------------------------------------------------------------------------
# Sector access
# ----------------------------------------------------------------------------

def buffer_reader(data: bytes, layout: tuple[int, int]) -> SectorReader:
    size, offset = layout

    def get(n: int) -> bytes:
        start = n * size + offset
        sector = data[start : start + SECTOR]
        return sector if len(sector) == SECTOR else b""

    return get


def cso_reader(read_at: ReadAt) -> SectorReader | None:
    """Sector access into a CISO (.cso) image, which PSP games are commonly stored as."""
    head = read_at(0, 24)
    if len(head) < 24 or head[:4] != b"CISO":
        return None
    header_size, total_bytes, block_size, _version, align = struct.unpack_from("<IQIBB", head, 4)
    if block_size != SECTOR or total_bytes <= 0 or header_size < 0x18:
        return None
    blocks = total_bytes // block_size

    def get(n: int) -> bytes:
        if n < 0 or n >= blocks:
            return b""
        entries = read_at(header_size + 4 * n, 8)
        if len(entries) < 8:
            return b""
        first, second = struct.unpack("<II", entries)
        start = (first & 0x7FFFFFFF) << align
        end = (second & 0x7FFFFFFF) << align
        if end <= start or end - start > 2 * SECTOR:
            return b""
        chunk = read_at(start, end - start)
        try:
            out = chunk[:SECTOR] if first & 0x80000000 else zlib.decompress(chunk, -15)
        except zlib.error:
            return b""
        return out if len(out) == SECTOR else b""

    return get


# ----------------------------------------------------------------------------
# ISO 9660
# ----------------------------------------------------------------------------

def iso_root(get: SectorReader) -> tuple[bytes, dict[str, tuple[int, int]]] | None:
    """The volume descriptor and the root directory's entries as {NAME: (first sector, size)}."""
    pvd = get(16)
    if pvd[:6] != b"\x01CD001":
        return None
    root = pvd[156:190]
    lba = int.from_bytes(root[2:6], "little")
    length = int.from_bytes(root[10:14], "little")
    entries: dict[str, tuple[int, int]] = {}
    for k in range(min((length + SECTOR - 1) // SECTOR, 32)):
        sector = get(lba + k)
        if not sector:
            break
        pos = 0
        while pos + 34 <= SECTOR:
            record_length = sector[pos]
            if record_length == 0:  # padding up to the next sector
                break
            name_length = sector[pos + 32]
            name = sector[pos + 33 : pos + 33 + name_length].decode("latin-1")
            entries[name.upper()] = (
                int.from_bytes(sector[pos + 2 : pos + 6], "little"),
                int.from_bytes(sector[pos + 10 : pos + 14], "little"),
            )
            pos += record_length
    return pvd, entries


def read_iso_file(get: SectorReader, lba: int, size: int, limit: int = SECTOR) -> bytes | None:
    """The first bytes of a file, or None if it lies outside what we have read."""
    want = min(size, limit)
    out = b""
    k = 0
    while len(out) < want:
        sector = get(lba + k)
        if not sector:
            return None
        out += sector
        k += 1
    return out[:want]


def classify_iso(get: SectorReader) -> DiscGuess | None:
    """Name the system an ISO 9660 disc is for, from what's in its root. None if it isn't ISO 9660."""
    parsed = iso_root(get)
    if parsed is None:
        return None
    pvd, entries = parsed
    if "PSP_GAME" in entries:
        return DiscGuess("psp", [], "PSP disc (PSP_GAME folder)")
    if "PS3_DISC.SFB" in entries or "PS3_GAME" in entries:
        return DiscGuess("ps3", [], "PlayStation 3 disc (PS3_GAME folder)")
    cnf = entries.get("SYSTEM.CNF;1")
    if cnf is not None:
        text = read_iso_file(get, *cnf)
        if text is not None:
            if re.search(rb"BOOT2\s*=", text):
                return DiscGuess("ps2", [], "PlayStation 2 disc (SYSTEM.CNF has BOOT2)")
            if re.search(rb"BOOT\s*=", text):
                return DiscGuess("psx", [], "PlayStation disc (SYSTEM.CNF has BOOT)")
    if pvd[8:40].strip().startswith(b"PLAYSTATION"):
        return DiscGuess(None, ["psx", "ps2"], "a PlayStation disc, but PS1 and PS2 couldn't be told apart")
    return DiscGuess()  # an ISO 9660 disc we don't recognise


# ----------------------------------------------------------------------------
# Nintendo discs
# ----------------------------------------------------------------------------

def nintendo_disc(head: bytes) -> str | None:
    """'gc' or 'wii' from a 0x20-byte disc header, else None."""
    if head[0x1C:0x20] == GC_MAGIC:
        return "gc"
    if head[0x18:0x1C] == WII_MAGIC:
        return "wii"
    return None


def _sniff_pbp(data: bytes, read_at: ReadAt | None) -> DiscGuess:
    if read_at is None or len(data) < 40:
        return DiscGuess(None, ["psp", "psx"], "a PBP file; PSP and PlayStation both use them")
    (psar,) = struct.unpack_from("<I", data, 36)
    marker = read_at(psar, 8) if psar else b""
    if marker == b"PSISOIMG":
        return DiscGuess("psx", [], "PBP containing a PlayStation disc")
    if marker == b"NPUMDIMG":
        return DiscGuess("psp", [], "PBP containing a PSP disc")
    return DiscGuess()


# ----------------------------------------------------------------------------
# The entry point
# ----------------------------------------------------------------------------

def sniff_disc_image(data: bytes, ext: str = "", read_at: ReadAt | None = None) -> DiscGuess:
    """Identify a disc image from its first bytes (and, if given, random access to the rest)."""
    magic = data[:4]

    # --- container formats ---
    if magic in (b"CISO", b"ZISO"):
        if ext == ".ciso":
            return DiscGuess(None, ["gc", "wii"], "a compressed Nintendo disc (CISO)")
        get = cso_reader(read_at) if (read_at is not None and magic == b"CISO") else None
        if get is not None:
            guess = classify_iso(get)
            if guess is not None and (guess.system or guess.candidates):
                return guess
        return DiscGuess(None, [], "a compressed disc image")
    if magic == b"\x00PBP":
        return _sniff_pbp(data, read_at)
    if magic == b"WBFS":
        return DiscGuess("wii", [], "Wii WBFS image")
    if magic in (b"RVZ\x01", b"WIA\x01"):
        system = nintendo_disc(data[0x58 : 0x58 + 0x20])  # the disc header is stored at 0x58
        if system:
            return DiscGuess(system, [], f"{'GameCube' if system == 'gc' else 'Wii'} disc (RVZ/WIA header)")
        return DiscGuess(None, ["gc", "wii"], "a Dolphin disc image, but GameCube and Wii couldn't be told apart")
    if magic == b"\x01\xc0\x0b\xb1":  # GCZ
        return DiscGuess(None, ["gc", "wii"], "a GCZ disc image, which doesn't say GameCube or Wii")

    # --- raw Nintendo / Xbox discs ---
    system = nintendo_disc(data[:0x20])
    if system:
        return DiscGuess(system, [], f"{'GameCube' if system == 'gc' else 'Wii'} disc header")
    if data[0x10000 : 0x10000 + len(XBOX_MAGIC)] == XBOX_MAGIC:
        return DiscGuess("xbox", [], "Xbox disc (XISO header)")

    # --- boot sectors of Sega CD-based systems ---
    for layout in LAYOUTS:
        sector0 = buffer_reader(data, layout)(0)
        if sector0.startswith(b"SEGA SEGASATURN"):
            return DiscGuess("saturn", [], "Sega Saturn disc")
        if sector0.startswith((b"SEGADISCSYSTEM", b"SEGABOOTDISC")):
            return DiscGuess("segacd", [], "Sega CD disc")
        if b"SEGA SEGAKATANA" in sector0[:64]:
            return DiscGuess("dreamcast", [], "Dreamcast disc (IP.BIN)")

    # --- ISO 9660 discs: PlayStation family ---
    for layout in LAYOUTS:
        guess = classify_iso(buffer_reader(data, layout))
        if guess is not None:
            return guess
    if b"PSP_GAME" in data:  # an image whose directory we couldn't walk, but which names the folder
        return DiscGuess("psp", [], "PSP disc (PSP_GAME folder)")
    return DiscGuess()


def sniff_chd(read: Callable[[int], bytes], read_at: ReadAt | None) -> DiscGuess:
    """A CHD says what kind of disc it holds (CD, DVD, GD-ROM) but not which system."""
    head = read(0x80)
    if head[:8] != b"MComprHD" or len(head) < 0x38:
        return DiscGuess()
    if int.from_bytes(head[12:16], "big") != 5 or read_at is None:
        return DiscGuess(None, [], "a CHD file")
    meta = int.from_bytes(head[0x30:0x38], "big")
    tag = read_at(meta, 4) if meta else b""
    if tag in (b"CHGD", b"CHGT"):
        return DiscGuess(None, ["dreamcast"], "a GD-ROM image (Dreamcast)")
    if tag in (b"CHT2", b"CHTR", b"CHCD"):
        return DiscGuess(None, ["psx", "ps2", "saturn", "segacd", "pcengine"], "a CD image")
    if tag == b"DVD ":
        return DiscGuess(None, ["ps2", "gc", "wii", "xbox", "psp"], "a DVD image")
    return DiscGuess(None, [], "a CHD file")
