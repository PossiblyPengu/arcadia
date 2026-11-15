#!/usr/bin/env python3
"""Get rclone (for cloud saves) from rclone.org, checked against the SHA-256 its release publishes.

    get_rclone.py DEST_DIR      → DEST_DIR/rclone (SteamOS doesn't ship it)

ARCADIA_RCLONE_URL replaces https://downloads.rclone.org (tests serve a fake release from 127.0.0.1).
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = os.environ.get("ARCADIA_RCLONE_URL", "https://downloads.rclone.org").rstrip("/")


class GetError(Exception):
    pass


def _fetch(url: str, limit: int = 128 << 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "arcadia-deck"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read(limit)


def arch() -> str:
    return "arm64" if platform.machine().lower() in ("aarch64", "arm64") else "amd64"


def get(dest: Path) -> str:
    """Download, check and unpack the latest rclone into dest. Returns its version."""
    m = re.search(r"v\d+\.\d+\.\d+", _fetch(f"{BASE}/version.txt").decode(errors="replace"))
    if not m:
        raise GetError("rclone.org didn't say which version is the latest")
    version = m.group(0)
    name = f"rclone-{version}-linux-{arch()}.zip"
    sums = _fetch(f"{BASE}/{version}/SHA256SUMS").decode(errors="replace")
    want = next((line.split()[0].lower() for line in sums.splitlines()
                 if line.strip().endswith(name) and re.fullmatch(r"[0-9a-fA-F]{64}", line.split()[0])), "")
    if not want:
        raise GetError(f"rclone's checksum list has no entry for {name}")
    data = _fetch(f"{BASE}/{version}/{name}")
    if hashlib.sha256(data).hexdigest() != want:
        raise GetError("the rclone download didn't match its checksum, so it wasn't used")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next((n for n in z.namelist() if n.endswith("/rclone")), None)
        if member is None:
            raise GetError("the rclone download had no rclone program in it")
        body = z.read(member)
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / ".rclone.new"
    tmp.write_bytes(body)
    tmp.chmod(0o755)
    tmp.replace(dest / "rclone")
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    try:
        version = get(Path(argv[0]))
    except (GetError, OSError, zipfile.BadZipFile) as e:
        print(f"✗ Couldn't get rclone: {e}")
        return 1
    print(f"✓ rclone {version.lstrip('v')} is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
