#!/usr/bin/env python3
"""Write arcadia/assets/consoles/ATTRIBUTION.md from tools/console_sources.json."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sources = json.loads((HERE / "console_sources.json").read_text())
lines = [
    "# Console pictures: sources and credits",
    "",
    "The pictures in this folder are pixel art made from photographs on Wikimedia Commons, using",
    "`tools/make_console_art.py` (cut out, cropped, scaled down, limited to a small palette, outlined).",
    "Each source photograph and its licence, as shown on its Commons page, is listed below. Pictures made from",
    "photographs under CC BY-SA 3.0 are shared here under the same licence (CC BY-SA 3.0,",
    "https://creativecommons.org/licenses/by-sa/3.0/). The others are public domain or CC0.",
    "",
    "Console names and designs belong to their makers; these pictures are only there to show which console is which.",
    "",
    "| Picture | Source photograph (Wikimedia Commons) | Author | Licence |",
    "|---|---|---|---|",
]
for cid, v in sorted(sources.items()):
    lines.append(f"| `{cid}` | [{v['file']}](https://commons.wikimedia.org/wiki/File:{v['file'].replace(' ', '_')}) | {v['author']} | {v['license']} |")
ORIGINAL = {
    "arcade": "the arcade cabinet",
    "__recent__": "the Recently played tile (an alarm clock)",
    "__favorites__": "the Favorites tile (a heart)",
    "__all__": "the All games tile (a stack of cartridges)",
    "cartridge": "the generic cartridge shown for a console you add yourself",
}
lines += ["", "## Drawn for Arcadia", "", "These have no photograph. They are original to this project: small 3D models drawn by", "`tools/make_extra_art.py` and cut down to pixel art the same way.", ""]
lines += [f"- `{cid}`: {what}" for cid, what in ORIGINAL.items()]
lines.append("")
(HERE.parent / "arcadia" / "assets" / "consoles" / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")
print(len(sources), "credited")
