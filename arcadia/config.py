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
DEFAULT_HOME = Path.home() / "Arcadia"

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
    # An emulator Arcadia installed into its own folder (File > Emulators). When it's installed,
    # this system launches it; otherwise `command` is used. Empty = always use `command`.
    emulator: str = ""


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
                emulator=preset.emulator if preset else "",
            )
        )
    return systems


@dataclass
class Config:
    # The one folder everything can live in: roms/, emulators/, bios/, media/, states/ and data/.
    # Empty means the older layout, where each of the folders below is set (or defaulted) on its own.
    home_dir: str = ""
    # Each of these, if set, overrides where that one thing lives. Blank = inside the home folder.
    rom_root: str = str(Path.home() / "ROMs")
    data_dir: str = str(DATA_HOME)
    media_dir: str = ""
    savestate_dir: str = ""
    show_empty_systems: bool = False  # hide systems with no games unless every system is empty
    sort: str = "title"  # title | recent | played | favorites
    inbox_dir: str = ""  # folder ROMs are downloaded into (e.g. ~/Downloads); empty = sorting off
    auto_import: bool = True  # move ROMs whose header confirms their system without asking
    systems: list[SystemConfig] = field(default_factory=default_systems)

    @classmethod
    def new_install(cls, home: Path | None = None) -> "Config":
        """A fresh setup: everything lives under one folder (~/Arcadia unless told otherwise)."""
        return cls(home_dir=str(home or DEFAULT_HOME), rom_root="", data_dir="")

    # ----- where things live -----

    @property
    def home_path(self) -> Path | None:
        return Path(self.home_dir).expanduser() if self.home_dir.strip() else None

    @staticmethod
    def _explicit(value: str) -> Path | None:
        return Path(value).expanduser() if value.strip() else None

    @property
    def rom_root_path(self) -> Path:
        explicit = self._explicit(self.rom_root)
        if explicit is not None:
            return explicit
        return self.home_path / "roms" if self.home_path else Path.home() / "ROMs"

    @property
    def data_path(self) -> Path:
        explicit = self._explicit(self.data_dir)
        if explicit is not None:
            return explicit
        return self.home_path / "data" if self.home_path else DATA_HOME

    @property
    def db_path(self) -> Path:
        return self.data_path / "library.db"

    @property
    def media_path(self) -> Path:
        explicit = self._explicit(self.media_dir)
        if explicit is not None:
            return explicit
        return self.home_path / "media" if self.home_path else self.data_path / "media"

    @property
    def savestate_path(self) -> Path:
        explicit = self._explicit(self.savestate_dir)
        if explicit is not None:
            return explicit
        return self.home_path / "states" if self.home_path else self.data_path / "savestates"

    @property
    def emulators_path(self) -> Path:
        """Installed emulators live here, one folder each."""
        return self.home_path / "emulators" if self.home_path else self.data_path / "emulators"

    @property
    def bios_path(self) -> Path:
        return self.home_path / "bios" if self.home_path else self.data_path / "bios"

    @property
    def inbox_path(self) -> Path | None:
        return Path(self.inbox_dir).expanduser() if self.inbox_dir.strip() else None

    @property
    def journal_path(self) -> Path:
        return self.data_path / "imports.json"

    def ensure_layout(self) -> list[Path]:
        """Create the folders under the home folder. Returns the ones that were missing.
        A ROM folder per system is only made when the ROM root is inside the home folder, so
        nothing is created in a ROM folder you pointed somewhere else."""
        wanted = [self.rom_root_path, self.data_path, self.media_path, self.savestate_path, self.emulators_path, self.bios_path]
        if not self.rom_root.strip():
            wanted += [self.rom_root_path / s.folder for s in self.systems]
        made = []
        for path in wanted:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                made.append(path)
        return made

    def system(self, system_id: str) -> SystemConfig:
        for s in self.systems:
            if s.id == system_id:
                return s
        raise KeyError(system_id)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH, home: Path | None = None) -> "Config":
        """Read the config. `home` (portable mode) makes that folder the home folder even if the
        file doesn't say so, so a copy of the folder works wherever it's moved."""
        if not path.exists():
            return cls.new_install(home)
        raw = json.loads(path.read_text(encoding="utf-8"))
        systems_raw = raw.pop("systems", [])
        known = {f.name for f in fields(cls)} - {"systems"}
        kwargs = {k: v for k, v in raw.items() if k in known}
        if home is not None:
            kwargs["home_dir"] = str(home)
        systems = []
        for raw_system in systems_raw:
            system = SystemConfig(**raw_system)
            preset = PRESETS.get(system.id)
            # A system saved before managed emulators existed, still using its stock command, can
            # use one. (A command you edited is left alone, and so is an emulator you cleared.)
            if "emulator" not in raw_system and preset is not None and system.command == preset.command:
                system.emulator = preset.emulator
            systems.append(system)
        systems = systems or default_systems()
        # Add systems that were added to the defaults after this config was saved.
        existing = {s.id for s in systems}
        systems += [s for s in default_systems() if s.id not in existing]
        return cls(systems=systems, **kwargs)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
