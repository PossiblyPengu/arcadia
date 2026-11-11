"""Which BIOS and key files each system wants, and whether they're in Arcadia's bios/ folder.

Arcadia never downloads or supplies these files: you bring your own dumps. It only looks for them
by file name (it does not check their contents), so "found" means a file with the right name is there.

The names below are the ones the emulators / libretro cores document. They are the common ones,
not an exhaustive list, and a system missing from here simply isn't checked. Files are looked for
in bios/ and in bios/<anything>/ up to two folders deep, ignoring upper/lower case.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from arcadia.config import Config


@dataclass(frozen=True)
class Need:
    """One requirement: any one of `names` (file names or *patterns*) satisfies it."""

    label: str
    names: tuple[str, ...]
    required: bool = True
    note: str = ""


NEEDS: dict[str, tuple[Need, ...]] = {
    "psx": (Need("PlayStation BIOS", ("scph5500.bin", "scph5501.bin", "scph5502.bin", "scph1001.bin", "scph7001.bin", "scph7502.bin"), note="any one; match your games' region"),),
    "ps2": (Need("PlayStation 2 BIOS", ("scph*.bin", "ps2-*.bin"), note="PCSX2 wants a BIOS dump in its bios folder"),),
    "saturn": (Need("Saturn BIOS", ("sega_101.bin", "mpr-17933.bin"), note="sega_101 = Japan, mpr-17933 = US/Europe"),),
    "segacd": (Need("Sega CD BIOS", ("bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin"), note="U = US, E = Europe, J = Japan"),),
    "dreamcast": (
        Need("Dreamcast BIOS", ("dc_boot.bin",)),
        Need("Dreamcast flash", ("dc_flash.bin",), required=False),
    ),
    "gba": (Need("GBA BIOS", ("gba_bios.bin",), required=False, note="optional: a built-in replacement is used without it"),),
    "nds": (
        Need("DS ARM7 BIOS", ("bios7.bin",), required=False),
        Need("DS ARM9 BIOS", ("bios9.bin",), required=False),
        Need("DS firmware", ("firmware.bin",), required=False, note="optional: melonDS has built-in replacements"),
    ),
    "lynx": (Need("Lynx boot ROM", ("lynxboot.img",)),),
    "pcengine": (Need("Super CD-ROM² System Card", ("syscard3.pce",), required=False, note="only for CD games"),),
    "atari7800": (Need("7800 BIOS", ("7800 BIOS (U).rom", "7800 BIOS (E).rom"), required=False),),
    "switch": (Need("Switch keys", ("prod.keys",), note="dumped from your own console"),),
    "xbox": (
        Need("Xbox MCPX boot ROM", ("mcpx_1.0.bin",)),
        Need("Xbox flash BIOS", ("Complex_4627v1.03.bin", "Complex_4627.bin"), note="any compatible flash image"),
    ),
}


@dataclass(frozen=True)
class NeedStatus:
    need: Need
    found: str | None  # the file that satisfied it, relative to bios/

    @property
    def ok(self) -> bool:
        return self.found is not None


@dataclass
class SystemBios:
    system_id: str
    name: str
    needs: list[NeedStatus] = field(default_factory=list)

    @property
    def missing_required(self) -> list[NeedStatus]:
        return [n for n in self.needs if not n.ok and n.need.required]

    @property
    def state(self) -> str:
        """"ok", "missing" (a required file is absent) or "optional" (only optional ones are absent)."""
        if self.missing_required:
            return "missing"
        return "ok" if all(n.ok for n in self.needs) else "optional"


def _listing(bios: Path, depth: int = 2) -> list[Path]:
    """Files under bios/, at most `depth` folders down (so a stray huge tree isn't walked)."""
    found: list[Path] = []
    stack = [(bios, 0)]
    while stack:
        folder, level = stack.pop()
        try:
            children = sorted(folder.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_file():
                found.append(child)
            elif child.is_dir() and not child.is_symlink() and level < depth:
                stack.append((child, level + 1))
    return found


def _match(need: Need, files: list[Path], bios: Path) -> str | None:
    for pattern in need.names:  # earlier names are preferred
        for f in files:
            if fnmatch.fnmatchcase(f.name.lower(), pattern.lower()):
                return f.relative_to(bios).as_posix()
    return None


def check_bios(config: Config) -> list[SystemBios]:
    """Status for every configured system that has known requirements."""
    bios = config.bios_path
    files = _listing(bios) if bios.is_dir() else []
    rows = []
    for system in config.systems:
        needs = NEEDS.get(system.id)
        if not needs:
            continue
        rows.append(SystemBios(system.id, system.name, [NeedStatus(n, _match(n, files, bios)) for n in needs]))
    return rows


def summarize(rows: list[SystemBios]) -> str:
    missing = [r for r in rows if r.state == "missing"]
    if not rows:
        return "No systems with known BIOS requirements."
    if not missing:
        return "All the BIOS files Arcadia knows about are in place."
    return f"{len(missing)} system{'s' if len(missing) != 1 else ''} still need{'s' if len(missing) == 1 else ''} a BIOS file."
