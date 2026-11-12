#!/usr/bin/env python3
"""Update this fork of Arcadia (the AppImage) and the deck extras from the project's GitHub releases.

  selfupdate.py            check, then update if there is a newer release
  selfupdate.py --check    only say whether there is one

The AppImage is replaced in place after the old one is kept next to it as <name>.previous, and the extras are
reinstalled with their own install.sh. Nothing in your ROMs, saves or Arcadia settings is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

API = os.environ.get("DECK_RELEASE_API", "https://api.github.com/repos/PossiblyPengu/arcadia/releases/latest")
HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
ESDE = Path(os.environ.get("ARCADIA_HOME", Path.home() / "Arcadia"))
VERSION_FILE = ESDE / "deck" / "version"
APPIMAGE_NAME = "Arcadia_x64_SteamDeck.AppImage"
EXTRAS_NAME = "arcadia-deck-extras.tar.gz"
TEST_MODE = "DECK_RELEASE_API" in os.environ  # a local test server may use http://127.0.0.1


class UpdateError(Exception):
    pass


def _open(url: str):
    p = urlparse(url)
    local = TEST_MODE and p.hostname in ("127.0.0.1", "localhost")
    if not local and (p.scheme != "https" or p.hostname not in HOSTS):
        raise UpdateError(f"refusing to use {url}")
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "arcadia-deck-update"}), timeout=60)
    except OSError as exc:
        raise UpdateError(f"couldn't reach {p.hostname}: {exc}") from exc


def latest() -> dict:
    with _open(API) as r:
        try:
            data = json.loads(r.read(4 * 1024 * 1024))
        except ValueError as exc:
            raise UpdateError("the release information couldn't be read") from exc
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise UpdateError("there is no release to update to yet")
    return data


def installed_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return ""


def appimage_path() -> Path:
    for candidate in (os.environ.get("DECK_APPIMAGE"), os.environ.get("APPIMAGE"), str(Path.home() / "Applications" / APPIMAGE_NAME)):
        if candidate:
            return Path(candidate)
    return Path.home() / "Applications" / APPIMAGE_NAME


def expected_sha256(asset: dict) -> str:
    """The SHA-256 GitHub lists for a release file ("sha256:<hex>"), or "" if it lists none."""
    kind, _, digest = str(asset.get("digest") or "").partition(":")
    digest = digest.lower()
    return digest if kind.lower() == "sha256" and re.fullmatch(r"[0-9a-f]{64}", digest) else ""


def download(url: str, dest: Path, size: int, sha256: str) -> None:
    """Download to `dest`, and keep it only if it is whole and is the file the release says it is."""
    done = 0
    digest = hashlib.sha256()
    try:
        with _open(url) as r, open(dest, "wb") as out:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
        if size and done != size:
            raise UpdateError(f"the download was cut short ({done} of {size} bytes), so nothing was changed")
        if digest.hexdigest() != sha256:
            raise UpdateError("the download doesn't match the checksum the release lists, so nothing was changed")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def checked_asset(assets: dict, name: str) -> tuple[dict, str]:
    """The release file and the checksum it must have. A release that lists no checksum for a file isn't used:
    one of these files is run after it is downloaded, so it is never taken on trust."""
    asset = assets[name]
    sha = expected_sha256(asset)
    if not sha:
        raise UpdateError(f"the release doesn't list a checksum for {name}, so nothing was changed")
    return asset, sha


def update(check_only: bool = False) -> str:
    release = latest()
    tag = release["tag_name"]
    if tag == installed_version():
        return f"Already up to date ({tag})."
    assets = {a.get("name"): a for a in release.get("assets", []) if isinstance(a, dict)}
    if check_only:
        return f"A newer release is available: {tag} (installed: {installed_version() or 'unknown'})."
    messages = []
    with tempfile.TemporaryDirectory(prefix="deck-update-") as tmp:
        tmp_dir = Path(tmp)
        extras_dir = None
        if EXTRAS_NAME in assets:
            a, sha = checked_asset(assets, EXTRAS_NAME)
            archive = tmp_dir / EXTRAS_NAME
            download(a["browser_download_url"], archive, int(a.get("size") or 0), sha)
            extras_dir = tmp_dir / "extras"
            with tarfile.open(archive) as tf:
                for m in tf.getmembers():  # never write outside the folder
                    if m.name.startswith(("/", "..")) or ".." in Path(m.name).parts or m.issym() or m.islnk():
                        raise UpdateError("the extras archive contained an unsafe path, so nothing was changed")
                tf.extractall(extras_dir)
        new_image = None
        if APPIMAGE_NAME in assets:
            a, sha = checked_asset(assets, APPIMAGE_NAME)
            target = appimage_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            new_image = target.with_name(target.name + ".new")
            download(a["browser_download_url"], new_image, int(a.get("size") or 0), sha)
            new_image.chmod(0o755)
        if new_image is not None:
            target = appimage_path()
            if target.exists():
                shutil.copy2(target, target.with_name(target.name + ".previous"))
            os.replace(new_image, target)
            messages.append(f"Arcadia updated ({target}); the old one is kept as {target.name}.previous.")
        if extras_dir is not None and (extras_dir / "deck" / "install.sh").is_file():
            done = subprocess.run(["bash", str(extras_dir / "deck" / "install.sh")], capture_output=True, text=True)
            messages.append("Deck extras reinstalled." if done.returncode == 0 else f"The deck extras couldn't be reinstalled: {done.stderr.strip()[:200]}")
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(tag + "\n")
    if not messages:
        messages.append("The release has nothing to install.")
    return f"Updated to {tag}. " + " ".join(messages) + " Restart Arcadia to use it."


def main(argv: list[str]) -> int:
    try:
        print(update("--check" in argv))
        return 0
    except UpdateError as exc:
        print(f"Not updated: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
