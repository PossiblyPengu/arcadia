"""Is each system ready to play? Only checkable things are reported."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from arcadia.config import Config
from arcadia.emulators import Installer
from arcadia.presets import PRESETS
from arcadia.setup_status import (
    NONE,
    OK,
    PROBLEM,
    check_launcher,
    core_path,
    flatpak_app,
    flatpak_installed,
    folder_sizes,
    status_rows,
    tree_size,
)


def home_config(tmp_path):
    return Config.new_install(tmp_path / "Arcadia")


def install_fake(config, emu_id, version="v1"):
    installer = Installer(config.emulators_path)
    app = installer.app_dir(emu_id)
    app.mkdir(parents=True)
    (app / "emu").write_text("#!/bin/sh\n")
    record = {"id": emu_id, "version": version, "asset": "emu", "sha256": "0" * 64, "verified": True, "exe": "emu"}
    (installer.folder(emu_id) / "install.json").write_text(json.dumps(record))
    return installer


yes = lambda app: True
no = lambda app: False
unavailable = lambda app: None
found = lambda program: "/usr/bin/" + program
missing = lambda program: None


# ---------- reading commands ----------

@pytest.mark.parametrize(
    "command, app",
    [
        ("flatpak run net.pcsx2.PCSX2 -batch -- {rom}", "net.pcsx2.PCSX2"),
        ("flatpak run --filesystem=host org.ppsspp.PPSSPP {rom}", "org.ppsspp.PPSSPP"),
        ("  flatpak run org.libretro.RetroArch -L ~/core.so {rom}", "org.libretro.RetroArch"),
        ("retroarch -L core.so {rom}", None),
        ("flatpak list", None),
        ("", None),
    ],
)
def test_the_flatpak_app_is_read_from_the_command(command, app):
    assert flatpak_app(command) == app


def test_the_retroarch_core_is_read_from_the_command():
    command = PRESETS["nes"].command
    assert core_path(command) == Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/cores/nestopia_libretro.so"
    assert core_path("flatpak run io.mgba.mGBA {rom}") is None


def test_flatpak_installed_asks_flatpak_and_survives_its_absence():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if cmd[-1] == "net.pcsx2.PCSX2" else 1)

    assert flatpak_installed("net.pcsx2.PCSX2", run, lambda p: "/usr/bin/flatpak") is True
    assert flatpak_installed("org.other.App", run, lambda p: "/usr/bin/flatpak") is False
    assert calls[0] == ["flatpak", "info", "net.pcsx2.PCSX2"]
    assert flatpak_installed("x", run, lambda p: None) is None  # flatpak isn't installed at all

    def broken(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 10)

    assert flatpak_installed("x", broken, lambda p: "/usr/bin/flatpak") is None
    assert flatpak_installed("x", lambda c, **k: (_ for _ in ()).throw(OSError()), lambda p: "/usr/bin/flatpak") is None


# ---------- one system ----------

def test_an_emulator_installed_in_the_arcadia_folder_is_ready(tmp_path):
    config = home_config(tmp_path)
    installer = install_fake(config, "pcsx2", "v2.2.0")
    status = check_launcher(config.system("ps2"), config, installer, unavailable, missing)
    assert (status.state, status.summary) == (OK, "PCSX2 v2.2.0")  # it doesn't even need Flatpak


def test_an_installed_flatpak_is_ready(tmp_path):
    config = home_config(tmp_path)
    status = check_launcher(config.system("ps2"), config, None, yes, missing)
    assert (status.state, status.summary) == (OK, "net.pcsx2.PCSX2 (Flatpak)")


def test_a_missing_flatpak_says_how_to_fix_it_and_offers_the_local_install(tmp_path):
    config = home_config(tmp_path)
    status = check_launcher(config.system("ps2"), config, None, no, missing)
    assert status.state == PROBLEM and status.summary == "net.pcsx2.PCSX2 not installed"
    assert "flatpak install flathub net.pcsx2.PCSX2" in status.detail and "File → Emulators" in status.detail
    # an emulator Arcadia can't install itself only gets the Flatpak advice
    snes = check_launcher(config.system("snes"), config, None, no, missing)
    assert "flatpak install flathub com.snes9x.Snes9x" in snes.detail and "File → Emulators" not in snes.detail


def test_flatpak_not_being_available_at_all_is_its_own_message(tmp_path):
    config = home_config(tmp_path)
    status = check_launcher(config.system("ps2"), config, None, unavailable, missing)
    assert status.state == PROBLEM and status.summary == "Flatpak isn't available"


def test_a_retroarch_core_that_hasnt_been_downloaded_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = home_config(tmp_path)
    nes = config.system("nes")
    nes.command = f"flatpak run org.libretro.RetroArch -L {tmp_path}/cores/nestopia_libretro.so {{rom}}"
    status = check_launcher(nes, config, None, yes, missing)
    assert status.state == PROBLEM and status.summary == "Core missing: nestopia_libretro.so"
    assert "Core Downloader" in status.detail
    (tmp_path / "cores").mkdir()
    (tmp_path / "cores" / "nestopia_libretro.so").write_text("core")
    assert check_launcher(nes, config, None, yes, missing).state == OK


def test_a_plain_command_is_checked_with_the_path(tmp_path):
    config = home_config(tmp_path)
    system = config.system("snes")
    system.command = "my-emu --fast {rom}"
    assert check_launcher(system, config, None, yes, found).state == OK
    status = check_launcher(system, config, None, yes, missing)
    assert status.state == PROBLEM and status.summary == "my-emu not found"
    exe = tmp_path / "bin" / "emu"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    system.command = f"{exe} {{rom}}"
    assert check_launcher(system, config, None, yes, missing).state == OK  # an absolute path needs no lookup


def test_systems_with_nothing_to_launch(tmp_path):
    config = home_config(tmp_path)
    ps2 = config.system("ps2")
    ps2.command = ""
    status = check_launcher(ps2, config, None, yes, missing)
    assert status.state == PROBLEM and "Install PCSX2" in status.detail
    snes = config.system("snes")
    snes.command = ""
    assert check_launcher(snes, config, None, yes, missing).state == NONE
    snes.command = 'broken "quote'
    assert check_launcher(snes, config, None, yes, missing).state == PROBLEM


# ---------- the table ----------

def test_only_systems_with_games_or_an_installed_emulator_are_listed(tmp_path):
    config = home_config(tmp_path)
    install_fake(config, "mgba")
    rows = status_rows(config, {"ps2": 12, "snes": 3}, flatpak_check=yes, which=found)
    ids = [r.system.id for r in rows]
    assert set(ids) == {"snes", "gb", "gbc", "gba", "ps2"}
    by_id = {r.system.id: r for r in rows}
    assert by_id["ps2"].games == 12 and by_id["gba"].games == 0  # installed here, no games yet
    assert by_id["gba"].launcher.summary.startswith("mGBA")
    everything = status_rows(config, {}, flatpak_check=yes, which=found, only_with_games=False)
    assert len(everything) == len(config.systems)


def test_each_flatpak_is_asked_about_only_once(tmp_path):
    config = home_config(tmp_path)
    asked = []

    def check(app):
        asked.append(app)
        return True

    status_rows(config, {"gb": 1, "gbc": 1, "gba": 1}, flatpak_check=check, which=found)
    assert asked.count("io.mgba.mGBA") == 1  # three systems share it


# ---------- sizes ----------

def test_tree_size_counts_files_and_ignores_links(tmp_path):
    root = tmp_path / "r"
    (root / "a" / "b").mkdir(parents=True)
    (root / "x.bin").write_bytes(b"x" * 100)
    (root / "a" / "y.bin").write_bytes(b"y" * 250)
    (root / "a" / "b" / "z.bin").write_bytes(b"z" * 50)
    os.symlink(root / "x.bin", root / "link.bin")
    os.symlink(root / "a", root / "linkdir")
    assert tree_size(root) == 400
    assert tree_size(tmp_path / "nope") == 0
    assert tree_size(root / "x.bin") == 0  # not a folder


def test_folder_sizes_cover_each_part_of_the_setup(tmp_path):
    config = home_config(tmp_path)
    config.ensure_layout()
    (config.rom_root_path / "ps2" / "g.iso").write_bytes(b"1" * 1000)
    (config.savestate_path / "s").write_bytes(b"2" * 20)
    sizes = folder_sizes(config)
    assert sizes["ROMs"] == 1000 and sizes["Save states"] == 20 and sizes["Emulators"] == 0
    assert set(sizes) == {"ROMs", "Emulators", "Save states", "Covers and metadata", "Backups"}
