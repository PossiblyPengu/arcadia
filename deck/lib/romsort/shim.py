"""The little bit of configuration the sorter needs: where the ROM folders are and what each system's folder is called.

The sorter's own system ids (from the earlier Arcadia app) are used inside it; the ROM folders are named after ES-DE's systems,
which call two of them differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# sorter system id -> ROM folder name (everything not listed uses the same name)
FOLDER_NAMES = {"sms": "mastersystem", "lynx": "atarilynx"}

# Systems ES-DE knows under more than one folder name, for the same hardware. Whichever one you already have is used, so a
# library is never split in two; with neither (or both), the first name that has the most games wins, the first listed
# on a tie. Only pairs that mean exactly the same system are here.
ALIASES = {
    "genesis": ("genesis", "megadrive"),
    "segacd": ("segacd", "megacd"),
    "pcengine": ("pcengine", "tg16"),
}

SYSTEM_IDS = (
    "nes", "snes", "n64", "gc", "wii", "wiiu", "switch", "gb", "gbc", "gba", "nds", "n3ds", "genesis", "sms", "gamegear",
    "segacd", "saturn", "dreamcast", "psx", "ps2", "ps3", "psp", "xbox", "pcengine", "neogeo", "arcade", "atari2600",
    "atari7800", "lynx", "wonderswan", "ngp", "virtualboy", "msx", "amiga",
)


@dataclass(frozen=True)
class SystemRef:
    id: str
    folder: str


class Config:
    def __init__(self, rom_root: Path):
        self.rom_root_path = Path(rom_root)
        self.systems = [SystemRef(i, FOLDER_NAMES.get(i, i)) for i in SYSTEM_IDS]

    def _folder_for(self, ref: SystemRef) -> str:
        """The ROM folder to use for this system: one you already have, among its equivalent names."""
        names = ALIASES.get(ref.id)
        if not names:
            return ref.folder
        present = [n for n in names if (self.rom_root_path / n).is_dir()]
        if not present:
            return ref.folder

        def games(name: str) -> int:
            try:
                return sum(1 for p in (self.rom_root_path / name).iterdir() if not p.name.startswith("."))
            except OSError:
                return 0
        return max(present, key=lambda n: (games(n), -names.index(n)))

    def system(self, system_id: str) -> SystemRef:
        for s in self.systems:
            if s.id == system_id:
                return SystemRef(s.id, self._folder_for(s))
        raise KeyError(system_id)
