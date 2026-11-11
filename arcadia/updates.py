"""Update every emulator in one go.

For emulators installed in Arcadia's folder: look up each one's latest release, find the *same
build* you installed before (so an Eden you chose the Steam Deck build of stays the Steam Deck
build), and install the new version with the same safe installer as a first install. If the same
build can't be identified unambiguously, nothing is guessed: the user picks.

For emulators still run through Flatpak: ask Flatpak which are installed and update them with
`flatpak update`, if the user wants.

One emulator failing never stops the others, and a failed update leaves that emulator's working
copy exactly as it was.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from arcadia.config import Config
from arcadia.emulators import (
    CATALOG,
    Asset,
    EmulatorError,
    EmulatorSpec,
    Installed,
    Installer,
    Release,
    candidate_assets,
)
from arcadia.setup_status import flatpak_app

CURRENT, READY, CHOOSE, NO_BUILD, ERROR = "current", "ready", "choose", "no-build", "error"


# ----------------------------------------------------------------------------
# Finding the same build in a newer release
# ----------------------------------------------------------------------------

def skeleton(name: str) -> str:
    """A file name with its version numbers and commit hashes blanked out, so that
    'Eden-Linux-v0.2.1-steamdeck-gcc-standard.AppImage' and '...-v0.2.2-...' look the same
    while '...-amd64-...' does not."""
    text = name.lower()
    text = re.sub(r"[0-9a-f]{7,}", "h", text)  # commit hashes (before digits, which they contain)
    text = re.sub(r"[0-9]+", "#", text)
    return text


def pick_same_build(installed_asset: str, candidates: Sequence[Asset]) -> Asset | None:
    """The candidate that is the same kind of build as the one installed, or None unless exactly one is."""
    wanted = skeleton(installed_asset)
    matches = [a for a in candidates if skeleton(a.name) == wanted]
    return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class UpdateRow:
    spec: EmulatorSpec
    installed: Installed
    release: Release | None
    status: str  # current | ready | choose | no-build | error
    asset: Asset | None = None  # what will be installed (status "ready")
    choices: tuple[Asset, ...] = ()  # what the user may pick from (status "choose")
    message: str = ""

    @property
    def newer(self) -> str:
        return self.release.tag if self.release else ""


def plan_updates(installer: Installer, specs: Sequence[EmulatorSpec] | None = None) -> list[UpdateRow]:
    """Look up the latest release of every installed emulator and decide what an update would be."""
    rows: list[UpdateRow] = []
    for spec in specs if specs is not None else CATALOG.values():
        installed = installer.get(spec.id)
        if installed is None:
            continue
        try:
            release = installer.latest_release(spec)
        except EmulatorError as exc:
            rows.append(UpdateRow(spec, installed, None, ERROR, message=str(exc)))
            continue
        if release.tag == installed.version:
            rows.append(UpdateRow(spec, installed, release, CURRENT))
            continue
        candidates = candidate_assets(spec, release).assets
        if not candidates:
            rows.append(UpdateRow(spec, installed, release, NO_BUILD, message="no Linux 64-bit download in the new release"))
            continue
        same = pick_same_build(installed.asset, candidates)
        if same is not None:
            rows.append(UpdateRow(spec, installed, release, READY, asset=same))
        else:
            rows.append(
                UpdateRow(
                    spec, installed, release, CHOOSE, choices=candidates,
                    message=f"couldn't tell which download is the same build as {installed.asset}",
                )
            )
    return rows


@dataclass
class UpdateOutcome:
    spec: EmulatorSpec
    ok: bool
    version: str = ""
    error: str = ""


def apply_updates(
    installer: Installer,
    chosen: Sequence[tuple[UpdateRow, Asset]],
    progress: Callable[[int, int], None] | None = None,
) -> list[UpdateOutcome]:
    """Install each chosen update in turn. progress(done, total) covers the whole batch (100 steps each)."""
    outcomes: list[UpdateOutcome] = []
    total = 100 * len(chosen)
    for i, (row, asset) in enumerate(chosen):
        def report(done: int, size: int, base=i * 100) -> None:
            if progress and size > 0:
                progress(base + min(99, int(done * 100 / size)), total)

        try:
            installed = installer.install(row.spec, row.release, asset, report)
            outcomes.append(UpdateOutcome(row.spec, True, version=installed.version))
        except (EmulatorError, OSError) as exc:
            outcomes.append(UpdateOutcome(row.spec, False, error=str(exc)))
        if progress:
            progress((i + 1) * 100, total)
    return outcomes


# ----------------------------------------------------------------------------
# Flatpak emulators
# ----------------------------------------------------------------------------

def installed_flatpaks(run: Callable = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> set[str] | None:
    """The Flatpak apps installed here, or None if flatpak isn't available."""
    if which("flatpak") is None:
        return None
    try:
        result = run(["flatpak", "list", "--app", "--columns=application"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def flatpaks_in_use(config: Config, installed: set[str], installer: Installer | None = None) -> list[str]:
    """Flatpak apps that systems still launch through, installed here, and not replaced by a local copy."""
    installer = installer or Installer(config.emulators_path)
    apps: list[str] = []
    for system in config.systems:
        spec = CATALOG.get(system.emulator) if system.emulator else None
        if spec is not None and installer.get(spec.id) is not None:
            continue  # this system launches the copy in Arcadia's folder
        app = flatpak_app(system.command)
        if app and app in installed and app not in apps:
            apps.append(app)
    return apps


@dataclass
class FlatpakResult:
    ok: bool
    output: str = ""
    apps: list[str] = field(default_factory=list)


def update_flatpaks(apps: Sequence[str], run: Callable = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> FlatpakResult:
    """Run `flatpak update` for just these apps (never for everything on the machine)."""
    apps = list(apps)
    if not apps:
        return FlatpakResult(True, "", [])
    if which("flatpak") is None:
        return FlatpakResult(False, "flatpak isn't available", apps)
    try:
        result = run(["flatpak", "update", "-y", "--noninteractive", *apps], capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as exc:
        return FlatpakResult(False, f"flatpak couldn't be run: {exc}", apps)
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    tail = "\n".join(text.splitlines()[-12:])
    return FlatpakResult(result.returncode == 0, tail, apps)
