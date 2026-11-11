#!/usr/bin/env python3
"""Download the source photographs listed in tools/console_sources.json from Wikimedia Commons.

    python tools/fetch_console_photos.py PHOTO_DIR

Then run tools/make_console_art.py on the same folder. Wikimedia rate-limits automated requests, so this
goes slowly (about 10 seconds per photo) and identifies itself; run it only when the art needs rebuilding.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_AGENT = "ArcadiaConsoleArt/1.0 (personal hobby project; rebuilds its console pictures)"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    folder = Path(argv[0])
    folder.mkdir(parents=True, exist_ok=True)
    sources = json.loads((HERE / "console_sources.json").read_text())
    for cid, info in sorted(sources.items()):
        suffix = Path(info["file"]).suffix.lower()
        target = folder / f"{cid}{suffix}"
        if target.exists() and target.stat().st_size > 8000:
            continue
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(info["file"]) + "?width=600"
        for attempt in range(4):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=40) as response:
                    target.write_bytes(response.read())
                print(f"{cid}: {info['file']}")
                break
            except Exception as exc:  # rate limits and timeouts: wait and try again
                print(f"{cid}: {exc}; retrying")
                time.sleep(20)
        time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
