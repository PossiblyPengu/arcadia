"""User configuration: ROM location, per-system launch commands and save folders."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from arcadia.presets import PRESETS

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "arcadia"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "arcadia"
CONFIG_PATH = CONFIG_HOME / "config.json"

# (id, display name, ROM folder under rom_root, accepted extensions)
_DEFAULT_SYSTEM_ROWS = [
    # Nintendo, consoles
    ("nes", "Nintendo Entertainment System", "nes", [".nes", ".zip", ".7z"]),
    ("snes", "Super Nintendo", "snes", [".sfc", ".smc", ".zip", ".7z"]),
    ("n64", "Nintendo 64", "n64", [".z64", ".n64", ".v64", ".zip"]),
    ("gc", "Nintendo GameCube", "gamecube", [".iso", ".gcm", ".rvz", ".gcz", ".ciso", ".wia"]),
    ("wii", "Nintendo Wii", "wii", [".iso", ".wbfs", ".rvz", ".gcz", ".ciso", ".wia"]),
    ("wiiu", "Nintendo Wii U", "wiiu", [".wua", ".wud", ".wux", ".rpx"]),
    ("switch", "Nintendo Switch", "switch", [".nsp", ".xci", ".nsz", ".xcz"]),
    # Nintendo, handhelds
    ("gb", "Game Boy", "gb", [".gb", ".zip"]),
    ("gbc", "Game Boy Color", "gbc", [".gbc", ".zip"]),
    ("gba", "Game Boy Advance", "gba", [".gba", ".zip"]),
    ("nds", "Nintendo DS", "nds", [".nds", ".dsi", ".zip", ".7z"]),
    ("n3ds", "Nintendo 3DS", "3ds", [".3ds", ".cci", ".cxi", ".cia", ".3dsx"]),
    # Sega
    ("genesis", "Sega Genesis", "genesis", [".md", ".gen", ".bin", ".zip"]),
    ("sms", "Sega Master System", "mastersystem", [".sms", ".zip"]),
    ("gamegear", "Sega Game Gear", "gamegear", [".gg", ".zip"]),
    ("segacd", "Sega CD", "segacd", [".cue", ".chd", ".iso", ".m3u"]),
    ("saturn", "Sega Saturn", "saturn", [".cue", ".chd", ".iso", ".m3u"]),
    ("dreamcast", "Sega Dreamcast", "dreamcast", [".gdi", ".cdi", ".chd"]),
    # Sony
    ("psx", "PlayStation", "psx", [".cue", ".chd", ".pbp", ".iso", ".m3u"]),
    ("ps2", "PlayStation 2", "ps2", [".iso", ".chd", ".cso", ".zso"]),
    ("ps3", "PlayStation 3", "ps3", [".iso"]),
    ("psp", "PlayStation Portable", "psp", [".iso", ".cso", ".pbp"]),
    # Microsoft
    ("xbox", "Xbox", "xbox", [".iso", ".xiso"]),
    # Arcade and others
    ("pcengine", "PC Engine / TurboGrafx-16", "pcengine", [".pce", ".sgx", ".cue", ".chd"]),
    ("neogeo", "Neo Geo", "neogeo", [".zip", ".7z", ".neo"]),
    ("arcade", "Arcade (MAME)", "arcade", [".zip", ".7z", ".chd"]),
    ("atari2600", "Atari 2600", "atari2600", [".a26", ".bin", ".zip"]),
    ("atari7800", "Atari 7800", "atari7800", [".a78", ".zip"]),
    ("lynx", "Atari Lynx", "lynx", [".lnx", ".zip"]),
    ("wonderswan", "WonderSwan", "wonderswan", [".ws", ".wsc", ".zip"]),
    ("ngp", "Neo Geo Pocket", "ngp", [".ngp", ".ngc", ".zip"]),
    ("virtualboy", "Virtual Boy", "virtualboy", [".vb", ".zip"]),
    # Computers
    ("msx", "MSX", "msx", [".rom", ".mx1", ".mx2", ".dsk", ".cas", ".zip"]),
    ("amiga", "Amiga", "amiga", [".adf", ".ipf", ".dms", ".hdf", ".lha"]),
]


@dataclass
class SystemConfig:
    id: str
    name: str
    folder: str
    extensions: list[str]
    # Launch template. {rom} is replaced with the quoted ROM path.
    command: str = ""
    # Folder where the emulator writes saves and save states for this system.
    save_dir: str = ""


def default_systems() -> list[SystemConfig]:
    systems = []
    for system_id, name, folder, extensions in _DEFAULT_SYSTEM_ROWS:
        preset = PRESETS.get(system_id)
        systems.append(
            SystemConfig(
                id=system_id,
                name=name,
                folder=folder,
                extensions=list(extensions),
                command=preset.command if preset else "",
                save_dir=preset.save_dir if preset else "",
            )
        )
    return systems


@dataclass
class Config:
    rom_root: str = str(Path.home() / "ROMs")
    data_dir: str = str(DATA_HOME)
    media_dir: str = ""  # empty = <data_dir>/media
    savestate_dir: str = ""  # empty = <data_dir>/savestates
    show_empty_systems: bool = False  # hide systems with no games unless every system is empty
    sort: str = "title"  # title | recent | played | favorites
    inbox_dir: str = ""  # folder ROMs are downloaded into (e.g. ~/Downloads); empty = sorting off
    auto_import: bool = True  # move ROMs whose header confirms their system without asking
    systems: list[SystemConfig] = field(default_factory=default_systems)

    @property
    def rom_root_path(self) -> Path:
        return Path(self.rom_root).expanduser()

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_path / "library.db"

    @property
    def media_path(self) -> Path:
        return Path(self.media_dir).expanduser() if self.media_dir else self.data_path / "media"

    @property
    def inbox_path(self) -> Path | None:
        return Path(self.inbox_dir).expanduser() if self.inbox_dir.strip() else None

    @property
    def journal_path(self) -> Path:
        return self.data_path / "imports.json"

    @property
    def savestate_path(self) -> Path:
        return Path(self.savestate_dir).expanduser() if self.savestate_dir else self.data_path / "savestates"

    def system(self, system_id: str) -> SystemConfig:
        for s in self.systems:
            if s.id == system_id:
                return s
        raise KeyError(system_id)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        systems_raw = raw.pop("systems", [])
        known = {f.name for f in fields(cls)} - {"systems"}
        kwargs = {k: v for k, v in raw.items() if k in known}
        systems = [SystemConfig(**s) for s in systems_raw] or default_systems()
        # Add systems that were added to the defaults after this config was saved.
        existing = {s.id for s in systems}
        systems += [s for s in default_systems() if s.id not in existing]
        return cls(systems=systems, **kwargs)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
