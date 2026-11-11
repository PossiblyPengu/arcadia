#!/usr/bin/env python3
"""Draw every console (tools/console_models.py) and reduce each to the pixel style of its generation.

    python tools/make_console_art.py [id ...]       # writes arcadia/assets/consoles/<id>.png
    python tools/make_console_art.py --preview DIR  # also saves the large drawing next to each, to check it

Needs PySide6, Pillow and numpy. The pictures are original to Arcadia.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

sys.path.insert(0, str(HERE.parent))
from console_models import ERA, MODELS  # noqa: E402
from isoart import ERAS, OUT, Scene, pixelate, to_pil  # noqa: E402


def main(argv: list[str]) -> int:
    preview = None
    if "--preview" in argv:
        i = argv.index("--preview")
        preview = Path(argv[i + 1])
        preview.mkdir(parents=True, exist_ok=True)
        argv = argv[:i] + argv[i + 2:]
    OUT.mkdir(parents=True, exist_ok=True)
    for cid in argv or sorted(MODELS):
        build, era = MODELS[cid], ERA[cid]
        scene = Scene()
        build(scene)
        if preview:
            to_pil(scene.render()).save(preview / f"{cid}_big.png")
        e = ERAS[era]
        pixelate(scene.render(width=e.width, smooth=e.smooth), e).save(OUT / f"{cid}.png", optimize=True)
        print(f"{cid}: {era}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
