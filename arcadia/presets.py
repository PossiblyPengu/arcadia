"""Launch presets for the systems Arcadia knows about.

Standalone emulators run through Flatpak, as on SteamOS. Systems without a good
standalone option use RetroArch with a libretro core.

What was checked, and what wasn't:
* Every Flatpak app ID exists on Flathub, and every libretro core file exists on the
  libretro build server.
* The command-line options were read from each project's source for Dolphin (-b -e),
  PCSX2 (-batch --), Cemu (-g), Eden (-g), RPCS3 (a path argument), melonDS (a ROM argument), xemu
  (-dvd_path), RMG (a ROM argument) and MAME (-rompath). They were NOT confirmed for
  Azahar, Flycast, FS-UAE, openMSX, DuckStation, PPSSPP, mGBA or Snes9x, which
  are the usual "emulator <file>" forms; check them on your machine.
* Save folders are only set for RetroArch. Settings lets you change anything, and
  "Reset launch commands to presets" restores these values.
* RetroArch downloads cores on demand (Online Updater > Core Downloader), so a core must
  be installed once before its system can launch.

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
    # An emulator Arcadia can install into its own folder (see emulators.py). While it isn't
    # installed, `command` (usually a Flatpak) is used instead.
    emulator: str = ""


def _ra(label: str, core: str, accent: str) -> Preset:
    return Preset(f"RetroArch · {label}", _retroarch(core), RETROARCH_SAVES, accent)


PRESETS: dict[str, Preset] = {
    # --- Nintendo, consoles ---
    "nes": _ra("Nestopia", "nestopia_libretro.so", "#e60012"),
    "snes": Preset("Snes9x (Flatpak)", "flatpak run com.snes9x.Snes9x {rom}", "", "#7b4fd6"),
    "n64": Preset("RMG (Flatpak)", "flatpak run com.github.Rosalie241.RMG {rom}", "", "#f2c200", emulator="rmg"),
    "gc": Preset("Dolphin (Flatpak)", "flatpak run org.DolphinEmu.dolphin-emu -b -e {rom}", "", "#6a5acd"),
    "wii": Preset("Dolphin (Flatpak)", "flatpak run org.DolphinEmu.dolphin-emu -b -e {rom}", "", "#35b6e8"),
    "wiiu": Preset("Cemu (Flatpak)", "flatpak run info.cemu.Cemu -g {rom}", "", "#009ac7", emulator="cemu"),
    "switch": Preset("Eden (Flatpak)", "flatpak run dev.eden_emu.eden -g {rom}", "", "#00c3e3", emulator="eden"),
    # --- Nintendo, handhelds ---
    "gb": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#8bac0f", emulator="mgba"),
    "gbc": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#4fa6c9", emulator="mgba"),
    "gba": Preset("mGBA (Flatpak)", "flatpak run io.mgba.mGBA {rom}", "", "#5e3fa3", emulator="mgba"),
    "nds": Preset("melonDS (Flatpak)", "flatpak run net.kuribo64.melonDS {rom}", "", "#9aa5b1", emulator="melonds"),
    "n3ds": Preset("Azahar (Flatpak)", "flatpak run org.azahar_emu.Azahar {rom}", "", "#d6322c", emulator="azahar"),
    # --- Sega ---
    "genesis": _ra("Genesis Plus GX", "genesis_plus_gx_libretro.so", "#1e6fd9"),
    "sms": _ra("Genesis Plus GX", "genesis_plus_gx_libretro.so", "#d9342b"),
    "gamegear": _ra("Genesis Plus GX", "genesis_plus_gx_libretro.so", "#2bb3a3"),
    "segacd": _ra("Genesis Plus GX", "genesis_plus_gx_libretro.so", "#2a8fbd"),
    "saturn": _ra("Beetle Saturn", "mednafen_saturn_libretro.so", "#4b5fa8"),
    "dreamcast": Preset("Flycast (Flatpak)", "flatpak run org.flycast.Flycast {rom}", "", "#f28a1a", emulator="flycast"),
    # --- Sony ---
    "psx": Preset("DuckStation (Flatpak)", "flatpak run org.duckstation.DuckStation -batch -- {rom}", "", "#7a8aa6", emulator="duckstation"),
    "ps2": Preset("PCSX2 (Flatpak)", "flatpak run net.pcsx2.PCSX2 -batch -- {rom}", "", "#3a57c4", emulator="pcsx2"),
    "ps3": Preset("RPCS3 (Flatpak)", "flatpak run net.rpcs3.RPCS3 {rom}", "", "#2f3b52", emulator="rpcs3"),
    "psp": Preset("PPSSPP (Flatpak)", "flatpak run org.ppsspp.PPSSPP {rom}", "", "#3b6ea8"),
    # --- Microsoft ---
    "xbox": Preset("xemu (Flatpak)", "flatpak run app.xemu.xemu -dvd_path {rom}", "", "#6fb43a", emulator="xemu"),
    # --- Arcade and others (RetroArch cores) ---
    "pcengine": _ra("Beetle PCE Fast", "mednafen_pce_fast_libretro.so", "#e8a33d"),
    "neogeo": _ra("FinalBurn Neo", "fbneo_libretro.so", "#c0392b"),
    "arcade": Preset("MAME (Flatpak)", "flatpak run org.mamedev.MAME -rompath {dir} {stem}", "", "#e84393"),
    "atari2600": _ra("Stella", "stella_libretro.so", "#b5651d"),
    "atari7800": _ra("ProSystem", "prosystem_libretro.so", "#a0522d"),
    "lynx": _ra("Handy", "handy_libretro.so", "#d4a017"),
    "wonderswan": _ra("Beetle Cygne", "mednafen_wswan_libretro.so", "#8e6bbf"),
    "ngp": _ra("Beetle NeoPop", "mednafen_ngp_libretro.so", "#5c8d89"),
    "virtualboy": _ra("Beetle VB", "mednafen_vb_libretro.so", "#d1001c"),
    # --- Computers ---
    "msx": Preset("openMSX (Flatpak)", "flatpak run org.openmsx.openMSX {rom}", "", "#2e8b57"),
    "amiga": Preset("FS-UAE (Flatpak)", "flatpak run net.fsuae.FS-UAE --floppy_drive_0={rom}", "", "#e07b39"),
}

DEFAULT_ACCENT = "#3e89d6"


def accent_for(system_id: str) -> str:
    preset = PRESETS.get(system_id)
    return preset.accent if preset else DEFAULT_ACCENT
