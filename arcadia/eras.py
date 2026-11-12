"""Which hardware generation ("bit era") each console belongs to.

The label is shown under the console's name, and logos.py draws each console's logo in the
pixel style of its era: how many pixels wide, how many colours, hard pixel edges or the soft filtering of a 3D chip.
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class EraStyle:
    label: str
    width: int  # the widest a picture is, in pixels
    colors: int  # the most colours it uses
    smooth: bool  # soft edges (a 3D chip's filtering) rather than hard pixels
    blur: float = 0.0  # extra softness, like a filtered texture


STYLES = {
    "8-bit": EraStyle("8-bit", 56, 12, False),
    "16-bit": EraStyle("16-bit", 80, 26, False),
    "32-bit": EraStyle("32-bit", 100, 44, False),
    "64-bit": EraStyle("64-bit", 116, 56, True, 0.6),
    "128-bit": EraStyle("128-bit", 132, 80, True),
    "HD": EraStyle("HD", 152, 120, True),
}
