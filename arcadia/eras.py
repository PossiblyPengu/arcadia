"""Which hardware generation ("bit era") each console belongs to.

The label is shown under the console's name, and tools/make_console_art.py draws each console's picture in the
pixel style of its era: how many pixels wide, how many colours, hard pixel edges or the soft filtering of a 3D chip.
"""

from __future__ import annotations

ERA_OF = {
    # 8-bit
    "nes": "8-bit", "gb": "8-bit", "gbc": "8-bit", "sms": "8-bit", "gamegear": "8-bit",
    "atari2600": "8-bit", "atari7800": "8-bit", "msx": "8-bit",
    # 16-bit
    "snes": "16-bit", "genesis": "16-bit", "segacd": "16-bit", "pcengine": "16-bit", "neogeo": "16-bit",
    "lynx": "16-bit", "wonderswan": "16-bit", "ngp": "16-bit", "amiga": "16-bit", "arcade": "16-bit",
    # 32-bit
    "psx": "32-bit", "saturn": "32-bit", "gba": "32-bit", "virtualboy": "32-bit", "nds": "32-bit", "psp": "32-bit",
    # 64-bit
    "n64": "64-bit",
    # 128-bit
    "dreamcast": "128-bit", "gc": "128-bit", "ps2": "128-bit", "xbox": "128-bit",
    # the HD era and later
    "wii": "HD", "wiiu": "HD", "ps3": "HD", "switch": "HD", "n3ds": "HD",
}
LABELS = ("8-bit", "16-bit", "32-bit", "64-bit", "128-bit", "HD")


def era_of(view_id: str) -> str:
    """The era label for a console, or "" for the collections and for consoles added by hand."""
    return ERA_OF.get(view_id, "")
