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
lines += ["", "The drawn 3D renders used for the few consoles without a photograph (the arcade cabinet, and the Recent, Favorites and All games tiles) are original to Arcadia.", ""]
(HERE.parent / "arcadia" / "assets" / "consoles" / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")
print(len(sources), "credited")
