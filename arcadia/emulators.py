"""Install emulators into Arcadia's own folder instead of scattering them over the system.

Each emulator gets one self-contained folder under <home>/emulators/:

    emulators/pcsx2/
        app/           the program (an AppImage, or an extracted archive)
        config/        } where the emulator keeps its settings, saves, shader caches and so on:
        data/          } Arcadia launches it with XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME
        cache/         } and XDG_STATE_HOME pointing here, so none of it lands in ~/.config,
        state/         } ~/.local/share or ~/.var/app. This works for emulators that follow the
                       } XDG convention, which most Qt and SDL programs do.
        install.json   what was installed, from where, and whether its checksum was verified

Safety rules for downloads: only https from a short list of GitHub hosts (every redirect is
re-checked), the SHA-256 is verified whenever GitHub publishes one, files are extracted into a
staging folder that cannot be escaped, and the old copy is replaced only after the new one is in
place. Nothing downloaded is ever run by the installer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

GITHUB_HOSTS = frozenset(
    {"github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
)
MAX_DOWNLOAD = 4 * 1024**3  # 4 GB
MAX_UNPACKED = 12 * 1024**3  # 12 GB


class EmulatorError(Exception):
    """Something went wrong installing or finding an emulator. The message is meant for the user."""


# ----------------------------------------------------------------------------
# The catalog
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class EmulatorSpec:
    id: str
    name: str
    systems: tuple[str, ...]  # system ids this emulator runs
    repo: str  # "owner/name" on GitHub, where its releases are
    prefer: tuple[str, ...]  # regexes for the build to preselect, best first (matched against file names)
    args: str  # launch arguments after the program, in launch-command syntax: {rom}, {dir}, {stem}, ...
    flatpak: str = ""  # the Flatpak it replaces, used while no local copy is installed
    exe: str = ""  # regex for the program inside an extracted archive (default: guess)
    notes: str = ""


# Only emulators that publish portable Linux builds on GitHub are listed. Dolphin, PPSSPP, Snes9x,
# MAME, openMSX and FS-UAE don't, and RetroArch's portable build is a .7z, so those stay on Flatpak.
CATALOG: dict[str, EmulatorSpec] = {
    spec.id: spec
    for spec in [
        EmulatorSpec("pcsx2", "PCSX2", ("ps2",), "PCSX2/pcsx2", (r"appimage.*qt", r"\.appimage$"), "-batch -- {rom}", "net.pcsx2.PCSX2"),
        EmulatorSpec("rpcs3", "RPCS3", ("ps3",), "RPCS3/rpcs3-binaries-linux", (r"linux64.*\.appimage$", r"\.appimage$"), "{rom}", "net.rpcs3.RPCS3"),
        EmulatorSpec("cemu", "Cemu", ("wiiu",), "cemu-project/Cemu", (r"x86_64.*\.appimage$", r"\.appimage$"), "-g {rom}", "info.cemu.Cemu"),
        EmulatorSpec("duckstation", "DuckStation", ("psx",), "stenzek/duckstation", (r"x64.*\.appimage$", r"\.appimage$"), "-batch -- {rom}", "org.duckstation.DuckStation"),
        EmulatorSpec("flycast", "Flycast", ("dreamcast",), "flyinghead/flycast", (r"x86_64.*\.appimage$", r"\.appimage$"), "{rom}", "org.flycast.Flycast"),
        EmulatorSpec("melonds", "melonDS", ("nds",), "melonDS-emu/melonDS", (r"appimage.*x86_64", r"x86_64.*appimage", r"linux.*x86_64"), "{rom}", "net.kuribo64.melonDS"),
        EmulatorSpec("azahar", "Azahar", ("n3ds",), "azahar-emu/azahar", (r"appimage", r"linux"), "{rom}", "org.azahar_emu.Azahar"),
        EmulatorSpec("rmg", "RMG", ("n64",), "Rosalie241/RMG", (r"linux64.*\.appimage$", r"portable.*linux64", r"linux64"), "{rom}", "com.github.Rosalie241.RMG"),
        EmulatorSpec("mgba", "mGBA", ("gb", "gbc", "gba"), "mgba-emu/mgba", (r"appimage-x64\.appimage$", r"appimage"), "{rom}", "io.mgba.mGBA"),
        EmulatorSpec("xemu", "xemu", ("xbox",), "xemu-project/xemu", (r"x86_64.*\.appimage$", r"\.appimage$"), "-dvd_path {rom}", "app.xemu.xemu"),
    ]
}


# ----------------------------------------------------------------------------
# Releases
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0
    digest: str = ""  # lower-case hex SHA-256 if the release publishes one


@dataclass(frozen=True)
class Release:
    tag: str
    assets: tuple[Asset, ...]
    page: str = ""


# Files that can't be a Linux x86-64 build we can unpack.
_NOT_FOR_US = re.compile(
    r"aarch64|arm64|armv|armhf|riscv|windows|win32|win64|\bwin\b|macos|osx|darwin|android|\bios\b|"
    r"\.exe$|\.msi$|\.dmg$|\.apk$|\.deb$|\.rpm$|\.flatpak$|\.snap$|\.7z$|\.rar$|"
    r"\.sig$|\.sha\d*$|\.sha256sum$|\.md5$|\.asc$|\.txt$|\.zsync$|\.json$|\.yml$|\.yaml$|"
    r"symbols|debug|source|\bsrc\b|\.pdb$",
    re.IGNORECASE,
)
_UNPACKABLE = re.compile(r"\.(appimage|zip|tar\.gz|tgz|tar\.xz|txz|tar\.bz2|tbz2|tar)$", re.IGNORECASE)


def parse_release(data: dict, repo: str = "") -> Release:
    """Read a GitHub 'latest release' response."""
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        raise EmulatorError("the release information didn't include a version")
    assets = []
    for raw in data.get("assets") or []:
        name, url = raw.get("name"), raw.get("browser_download_url")
        if not name or not url:
            continue
        digest = str(raw.get("digest") or "")
        digest = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
        assets.append(Asset(str(name), str(url), int(raw.get("size") or 0), digest))
    page = f"https://github.com/{repo}/releases/tag/{tag}" if repo else ""
    return Release(tag, tuple(assets), page)


@dataclass(frozen=True)
class Candidates:
    assets: tuple[Asset, ...]  # Linux x86-64 builds we can unpack, best guess first
    preselected: Asset | None  # set only when one of the spec's patterns matched


def candidate_assets(spec: EmulatorSpec, release: Release) -> Candidates:
    """The downloads in a release that could be this emulator for Linux. A best guess is
    preselected only if it matches what's known about the project's file names; otherwise the
    user chooses, so a wrong guess can't install the wrong thing."""
    usable = [
        a for a in release.assets
        if _UNPACKABLE.search(a.name) and not _NOT_FOR_US.search(a.name)
        and (re.search(r"linux|appimage|x86[_-]?64|x64|amd64", a.name, re.IGNORECASE))
    ]

    def rank(asset: Asset) -> tuple[int, str]:
        for i, pattern in enumerate(spec.prefer):
            if re.search(pattern, asset.name, re.IGNORECASE):
                return (i, asset.name.lower())
        return (len(spec.prefer), asset.name.lower())

    usable.sort(key=rank)
    best = usable[0] if usable and rank(usable[0])[0] < len(spec.prefer) else None
    return Candidates(tuple(usable), best)


# ----------------------------------------------------------------------------
# Network
# ----------------------------------------------------------------------------

class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, fetcher: "Fetcher"):
        self.fetcher = fetcher

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.fetcher.check_url(newurl)  # a redirect must not lead anywhere we wouldn't go directly
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(
        self,
        api_base: str = "https://api.github.com",
        hosts: frozenset[str] = GITHUB_HOSTS,
        allow_http: bool = False,
        timeout: float = 30.0,
    ):
        self.api_base = api_base.rstrip("/")
        self.allow_http = allow_http
        self.timeout = timeout
        self.hosts = frozenset(hosts) | {urlparse(self.api_base).hostname or ""}

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (self.allow_http and parsed.scheme == "http"):
            raise EmulatorError(f"refusing to use a non-https address: {url}")
        if (parsed.hostname or "") not in self.hosts:
            raise EmulatorError(f"refusing to download from {parsed.hostname or 'an unknown host'}")

    def _open(self, url: str):
        self.check_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": "Arcadia", "Accept": "application/vnd.github+json, */*"})
        opener = urllib.request.build_opener(_CheckedRedirects(self))
        try:
            return opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) and exc.headers.get("x-ratelimit-remaining") == "0":
                raise EmulatorError("GitHub is limiting requests from this connection; try again in a little while") from exc
            if exc.code == 404:
                raise EmulatorError("that release or file wasn't found") from exc
            raise EmulatorError(f"the download server answered {exc.code} {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmulatorError(f"couldn't reach {urlparse(url).hostname}: {getattr(exc, 'reason', exc)}") from exc

    def get_json(self, url: str) -> dict:
        with self._open(url) as response:
            body = response.read(8 * 1024 * 1024)
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise EmulatorError("the release information couldn't be read") from exc
        if not isinstance(data, dict):
            raise EmulatorError("the release information wasn't in the expected form")
        return data

    def download(self, url: str, dest: Path, progress: Callable[[int, int], None] | None = None) -> str:
        """Download to dest and return the SHA-256 of what was written."""
        digest = hashlib.sha256()
        done = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._open(url) as response, open(dest, "wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                if total > MAX_DOWNLOAD:
                    raise EmulatorError("the download is larger than Arcadia will accept")
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_DOWNLOAD:
                        raise EmulatorError("the download is larger than Arcadia will accept")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress:
                        progress(done, total)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        return digest.hexdigest()


# ----------------------------------------------------------------------------
# Unpacking
# ----------------------------------------------------------------------------

def _safe_target(dest: Path, name: str) -> Path:
    """Where an archive member would land, refusing anything that escapes dest."""
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or ".." in Path(normalised).parts:
        raise EmulatorError(f"the download contains an unsafe path ({name})")
    root = dest.resolve()
    target = (dest / normalised).resolve()
    if target != root and root not in target.parents:
        raise EmulatorError(f"the download contains an unsafe path ({name})")
    return target


def _write_member(src, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as out:
        shutil.copyfileobj(src, out)
    os.chmod(target, (mode & 0o777 | 0o600) if mode & 0o777 else 0o644)


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise EmulatorError("the download unpacks to more than Arcadia will accept")
        for info in infos:
            unix_mode = info.external_attr >> 16
            target = _safe_target(dest, info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISLNK(unix_mode):
                continue  # links are skipped: they are a classic way to write outside the folder
            else:
                with zf.open(info) as src:
                    _write_member(src, target, unix_mode)


def _extract_tar(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        if sum(m.size for m in members) > MAX_UNPACKED:
            raise EmulatorError("the download unpacks to more than Arcadia will accept")
        for member in members:
            target = _safe_target(dest, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                src = tf.extractfile(member)
                if src is not None:
                    with src:
                        _write_member(src, target, member.mode)
            # links, devices and anything else are skipped


def _find_program(dest: Path, spec: EmulatorSpec) -> Path:
    files = [p for p in dest.rglob("*") if p.is_file()]

    def rel(p: Path) -> str:
        return p.relative_to(dest).as_posix()

    if spec.exe:
        matches = [p for p in files if re.search(spec.exe, rel(p), re.IGNORECASE)]
    else:
        matches = [p for p in files if p.name.lower().endswith(".appimage")]
        if not matches:
            names = {spec.id.lower(), spec.name.lower().replace(" ", "")}
            matches = [p for p in files if not p.suffix and p.name.lower() in names]
        if not matches:
            matches = [p for p in files if not p.suffix and os.access(p, os.X_OK)]
    if not matches:
        raise EmulatorError("couldn't find the program inside the download")
    matches.sort(key=lambda p: (len(p.relative_to(dest).parts), len(rel(p))))
    if len(matches) > 1 and len(matches[0].relative_to(dest).parts) == len(matches[1].relative_to(dest).parts):
        raise EmulatorError(
            "couldn't tell which file in the download is the program: " + ", ".join(rel(p) for p in matches[:3])
        )
    return matches[0]


def unpack(spec: EmulatorSpec, archive: Path, dest: Path) -> str:
    """Put the download into dest and return the program's path relative to dest."""
    name = archive.name.lower()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if name.endswith(".appimage"):
            shutil.copy2(archive, dest / archive.name)
        elif name.endswith(".zip"):
            _extract_zip(archive, dest)
        elif re.search(r"\.(tar\.gz|tgz|tar\.xz|txz|tar\.bz2|tbz2|tar)$", name):
            _extract_tar(archive, dest)
        else:
            raise EmulatorError(f"don't know how to unpack {archive.name}")
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as exc:
        raise EmulatorError(f"the download couldn't be unpacked: {exc}") from exc
    program = _find_program(dest, spec)
    program.chmod(program.stat().st_mode | 0o755)
    return program.relative_to(dest).as_posix()


# ----------------------------------------------------------------------------
# The installer
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Installed:
    id: str
    version: str
    asset: str
    sha256: str
    verified: bool  # the download matched a checksum GitHub published
    exe: str  # path of the program, relative to the app/ folder
    source: str = ""
    installed_at: str = ""


class Installer:
    DATA_DIRS = ("config", "data", "cache", "state")

    def __init__(self, emulators_dir: Path, fetcher: Fetcher | None = None):
        self.root = emulators_dir
        self.fetcher = fetcher or Fetcher()

    # ----- where things are -----

    def folder(self, emu_id: str) -> Path:
        return self.root / emu_id

    def app_dir(self, emu_id: str) -> Path:
        return self.folder(emu_id) / "app"

    def get(self, emu_id: str) -> Installed | None:
        """The installed copy, or None if there isn't a working one."""
        try:
            data = json.loads((self.folder(emu_id) / "install.json").read_text(encoding="utf-8"))
            installed = Installed(**{k: data[k] for k in Installed.__dataclass_fields__ if k in data})
        except (OSError, ValueError, TypeError, KeyError):
            return None
        return installed if self.exe_path(installed).is_file() else None

    def exe_path(self, installed: Installed) -> Path:
        return self.app_dir(installed.id) / installed.exe

    def installed(self) -> dict[str, Installed]:
        found = {}
        for emu_id in CATALOG:
            inst = self.get(emu_id)
            if inst is not None:
                found[emu_id] = inst
        return found

    # ----- running -----

    def launch_env(self, emu_id: str) -> dict[str, str]:
        """Environment that keeps an emulator's settings, saves and caches inside its own folder."""
        base = self.folder(emu_id)
        env = {}
        for name, var in zip(self.DATA_DIRS, ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")):
            (base / name).mkdir(parents=True, exist_ok=True)
            env[var] = str(base / name)
        return env

    # ----- installing -----

    def latest_release(self, spec: EmulatorSpec) -> Release:
        data = self.fetcher.get_json(f"{self.fetcher.api_base}/repos/{spec.repo}/releases/latest")
        return parse_release(data, spec.repo)

    def update_available(self, spec: EmulatorSpec, release: Release) -> bool:
        current = self.get(spec.id)
        return current is not None and current.version != release.tag

    def install(
        self,
        spec: EmulatorSpec,
        release: Release,
        asset: Asset,
        progress: Callable[[int, int], None] | None = None,
    ) -> Installed:
        """Download and install one build. The previous copy is kept until the new one is in place,
        and the emulator's own settings and saves are never touched."""
        folder = self.folder(spec.id)
        folder.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".install-", dir=folder))
        try:
            filename = Path(asset.name.replace("\\", "/")).name
            archive = staging / "download" / filename
            sha = self.fetcher.download(asset.url, archive, progress)
            if asset.digest and sha != asset.digest:
                raise EmulatorError(
                    f"the download doesn't match the checksum GitHub published for it, so it was thrown away\n"
                    f"expected {asset.digest}\ngot      {sha}"
                )
            new_app = staging / "app"
            exe = unpack(spec, archive, new_app)
            installed = Installed(
                id=spec.id,
                version=release.tag,
                asset=asset.name,
                sha256=sha,
                verified=bool(asset.digest),
                exe=exe,
                source=asset.url,
                installed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

            current, backup = folder / "app", folder / ".app.previous"
            shutil.rmtree(backup, ignore_errors=True)
            if current.exists():
                current.rename(backup)
            try:
                new_app.rename(current)
                self._write_record(folder, installed)
            except OSError as exc:
                if backup.exists():
                    shutil.rmtree(current, ignore_errors=True)
                    backup.rename(current)  # put the old copy back
                raise EmulatorError(f"couldn't put the new copy in place: {exc.strerror or exc}") from exc
            shutil.rmtree(backup, ignore_errors=True)
            return installed
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _write_record(folder: Path, installed: Installed) -> None:
        tmp = folder / "install.json.tmp"
        tmp.write_text(json.dumps(asdict(installed), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, folder / "install.json")

    def remove(self, emu_id: str, delete_data: bool = False) -> None:
        """Remove the program. Its settings and saves stay unless delete_data is set."""
        folder = self.folder(emu_id)
        if delete_data:
            shutil.rmtree(folder, ignore_errors=True)
            return
        shutil.rmtree(folder / "app", ignore_errors=True)
        (folder / "install.json").unlink(missing_ok=True)
