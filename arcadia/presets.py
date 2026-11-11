"""Launch presets for the systems Arcadia knows about.

Standalone emulators run through Flatpak, as on SteamOS. Systems without a good
standalone option use RetroArch with a libretro core. The Flatpak app IDs were
checked on Flathub. The command-line options and save folders are the usual
defaults and should be checked on your machine. Settings lets you change them,
and "Reset launch commands to presets" restores these values.

Flatpak apps can only read folders they've been granted. For each app, run:
    flatpak override --user --filesystem=/path/to/ROMs <app-id>
"""

from __future__ import annotations

from dataclasses import dataclass

RETROARCH_FLATPAK = "flatpak run org.libretro.RetroArch"
RETROARCH_CORES = "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
RETROARCH_SAVES = "~/.var/app/org.libretro.RetroArch/config/retroarch/saves"


def _retroarch(core: str) -> str:
    return f"{RETROARCH_FLATPAK} -L {RETROARCH_CORES}/{core} {{rom}}"


@dataclass(frozen=True)
class Preset:
    label: str
    command: str
    save_dir: str = ""
    accent: str = "#3e89d6"


PRESETS: dict[str, Preset] = {
    "nes": Preset("RetroArch · Nestopia", _retroarch("nestopia_libretro.so"), RETROARCH_SAVES, "#e60012"),
    "snes": Preset("Snes9x (Flatpak)", "flatpak run com.snes9x.Snes9x {rom}", "", "#7b4fd6"),
    "gb": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#8bac0f"),
    "gbc": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#4fa6c9"),
    "gba": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#5e3fa3"),
    "n64": Preset("RetroArch · Mupen64Plus", _retroarch("mupen64plus_next_libretro.so"), RETROARCH_SAVES, "#f2c200"),
    "genesis": Preset("RetroArch · Genesis Plus GX", _retroarch("genesis_plus_gx_libretro.so"), RETROARCH_SAVES, "#1e6fd9"),
    "sms": Preset("RetroArch · Genesis Plus GX", _retroarch("genesis_plus_gx_libretro.so"), RETROARCH_SAVES, "#d9342b"),
    "gamegear": Preset("RetroArch · Genesis Plus GX", _retroarch("genesis_plus_gx_libretro.so"), RETROARCH_SAVES, "#2bb3a3"),
    "psx": Preset("DuckStation (Flatpak)", "flatpak run org.duckstation.DuckStation -batch -- {rom}", "", "#7a8aa6"),
    "psp": Preset("PPSSPP (Flatpak)", "flatpak run org.ppsspp.PPSSPP {rom}", "", "#3b6ea8"),
}

DEFAULT_ACCENT = "#3e89d6"


def accent_for(system_id: str) -> str:
    preset = PRESETS.get(system_id)
    return preset.accent if preset else DEFAULT_ACCENT
