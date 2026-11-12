"""The little bit of configuration the sorter needs: where the ROM folders are and what each system's folder is called.

The sorter's own system ids (from the earlier Arcadia app) are used inside it; the ROM folders are named after ES-DE's systems,
which call two of them differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# sorter system id -> ROM folder name (everything not listed uses the same name)
FOLDER_NAMES = {"sms": "mastersystem", "lynx": "atarilynx"}

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

    def system(self, system_id: str) -> SystemRef:
        for s in self.systems:
            if s.id == system_id:
                return s
        raise KeyError(system_id)
