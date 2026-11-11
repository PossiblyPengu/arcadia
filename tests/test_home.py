"""The single Arcadia folder: where everything lives, and portable mode."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from arcadia.config import DATA_HOME, DEFAULT_HOME, Config, SystemConfig, default_systems
from arcadia.presets import PRESETS

ROOT = Path(__file__).resolve().parent.parent


# ---------- where things live ----------

def test_a_legacy_config_keeps_every_old_location():
    cfg = Config(rom_root="/games", data_dir="/data")
    assert cfg.home_path is None
    assert cfg.rom_root_path == Path("/games") and cfg.data_path == Path("/data")
    assert cfg.media_path == Path("/data/media") and cfg.savestate_path == Path("/data/savestates")
    assert cfg.emulators_path == Path("/data/emulators") and cfg.bios_path == Path("/data/bios")


def test_the_home_folder_holds_everything(tmp_path):
    cfg = Config.new_install(tmp_path / "Arcadia")
    home = tmp_path / "Arcadia"
    assert cfg.home_path == home
    assert [cfg.rom_root_path, cfg.data_path, cfg.media_path, cfg.savestate_path, cfg.emulators_path, cfg.bios_path] == [
        home / "roms", home / "data", home / "media", home / "states", home / "emulators", home / "bios"
    ]
    assert cfg.db_path == home / "data" / "library.db" and cfg.journal_path == home / "data" / "imports.json"


def test_a_fresh_install_defaults_to_arcadia_in_the_home_directory():
    cfg = Config.new_install()
    assert cfg.home_path == DEFAULT_HOME == Path.home() / "Arcadia"
    assert cfg.rom_root == "" and cfg.data_dir == ""  # derived, not frozen to today's paths


def test_any_one_folder_can_still_live_elsewhere(tmp_path):
    cfg = Config.new_install(tmp_path / "Arcadia")
    cfg.rom_root = str(tmp_path / "bigdisk" / "ROMs")
    cfg.media_dir = str(tmp_path / "covers")
    assert cfg.rom_root_path == tmp_path / "bigdisk" / "ROMs" and cfg.media_path == tmp_path / "covers"
    assert cfg.emulators_path == tmp_path / "Arcadia" / "emulators"  # the rest stay put


def test_the_old_default_data_folder_is_unchanged_without_a_home():
    assert Config().data_path == Path(Config().data_dir)
    assert Config(data_dir="").data_path == DATA_HOME


# ---------- creating the folders ----------

def test_ensure_layout_creates_the_folders_and_one_rom_folder_per_system(tmp_path):
    cfg = Config.new_install(tmp_path / "Arcadia")
    made = cfg.ensure_layout()
    home = tmp_path / "Arcadia"
    for name in ("roms", "data", "media", "states", "emulators", "bios", "backups"):
        assert (home / name).is_dir()
    assert all((home / "roms" / s.folder).is_dir() for s in cfg.systems)
    assert len(made) == 7 + len(cfg.systems)
    assert cfg.ensure_layout() == []  # nothing left to make the second time


def test_no_system_folders_are_made_in_a_rom_folder_you_chose_yourself(tmp_path):
    cfg = Config.new_install(tmp_path / "Arcadia")
    cfg.rom_root = str(tmp_path / "mine")
    cfg.ensure_layout()
    assert (tmp_path / "mine").is_dir() and list((tmp_path / "mine").iterdir()) == []


# ---------- loading and saving ----------

def test_loading_with_no_file_starts_a_fresh_install_in_the_given_home(tmp_path):
    cfg = Config.load(tmp_path / "nope.json", home=tmp_path / "Stick")
    assert cfg.home_path == tmp_path / "Stick" and cfg.rom_root == ""
    assert Config.load(tmp_path / "nope.json").home_path == DEFAULT_HOME


def test_portable_mode_overrides_the_home_folder_a_saved_config_names(tmp_path):
    path = tmp_path / "config.json"
    Config.new_install(Path("/old/place")).save(path)
    cfg = Config.load(path, home=tmp_path / "moved")  # the folder was copied somewhere else
    assert cfg.home_path == tmp_path / "moved" and cfg.emulators_path == tmp_path / "moved" / "emulators"


def test_a_config_saved_before_homes_existed_loads_as_the_old_layout(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"rom_root": "/games", "data_dir": "/data", "systems": []}))
    cfg = Config.load(path)
    assert cfg.home_path is None and cfg.rom_root_path == Path("/games")


def test_the_new_settings_survive_a_save_and_load(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config.new_install(tmp_path / "Arcadia")
    cfg.system("ps2").emulator = ""
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.home_dir == str(tmp_path / "Arcadia") and loaded.rom_root == ""
    assert loaded.system("ps2").emulator == "" and loaded.system("psx").emulator == "duckstation"


# ---------- systems and managed emulators ----------

def test_default_systems_name_the_emulator_their_preset_can_install():
    by_id = {s.id: s for s in default_systems()}
    assert by_id["ps2"].emulator == "pcsx2" and by_id["gba"].emulator == "mgba" and by_id["wiiu"].emulator == "cemu"
    assert by_id["snes"].emulator == "" and by_id["gc"].emulator == ""  # their emulators stay on Flatpak
    assert all(PRESETS[s.id].emulator == s.emulator for s in by_id.values())


def _old_systems_json(**overrides):
    ps2 = {"id": "ps2", "name": "PS2", "folder": "ps2", "extensions": [".iso"], "command": PRESETS["ps2"].command, "save_dir": ""}
    ps2.update(overrides)
    return json.dumps({"systems": [ps2]})


def test_an_old_system_with_its_stock_command_gains_the_emulator(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(_old_systems_json())
    assert Config.load(path).system("ps2").emulator == "pcsx2"


def test_an_edited_command_is_left_alone(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(_old_systems_json(command="my-own-launcher {rom}"))
    cfg = Config.load(path)
    assert cfg.system("ps2").emulator == "" and cfg.system("ps2").command == "my-own-launcher {rom}"


def test_an_emulator_the_user_cleared_stays_cleared(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(_old_systems_json(emulator=""))  # the key is present: a deliberate choice
    assert Config.load(path).system("ps2").emulator == ""


# ---------- first run and portable mode, for real ----------

def _run_arcadia(args, env_extra, workdir, wait_for: Path):
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(ROOT), **env_extra}
    proc = subprocess.Popen([sys.executable, "-m", "arcadia", *args], cwd=workdir, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not wait_for.exists():
            time.sleep(0.1)
        time.sleep(1.5)  # let it finish starting
        still_running = proc.poll() is None  # a crash during startup would have ended it already
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    return still_running


def test_the_first_run_with_a_home_folder_sets_everything_up_inside_it(tmp_path):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    home = tmp_path / "Stick"
    running = _run_arcadia(["--home", str(home)], {"XDG_CONFIG_HOME": str(tmp_path / "xdg-config")}, tmp_path, home / "config.json")
    assert running, "Arcadia exited during startup"
    assert (home / "config.json").is_file()
    for name in ("roms", "emulators", "bios", "media", "states", "data"):
        assert (home / name).is_dir()
    assert (home / "roms" / "ps2").is_dir() and (home / "data" / "library.db").is_file()
    assert not (tmp_path / "xdg-config").exists()  # nothing was written to the usual places


def test_the_environment_variable_works_like_the_flag(tmp_path):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    home = tmp_path / "FromEnv"
    running = _run_arcadia([], {"ARCADIA_HOME": str(home), "XDG_CONFIG_HOME": str(tmp_path / "xc")}, tmp_path, home / "config.json")
    assert running, "Arcadia exited during startup"
    assert (home / "config.json").is_file() and (home / "emulators").is_dir()


def test_a_switch_setup_that_still_uses_ryujinx_is_not_switched_to_eden(tmp_path):
    path = tmp_path / "c.json"
    ryujinx = "flatpak run io.github.ryubing.Ryujinx {rom}"
    path.write_text(json.dumps({"systems": [{"id": "switch", "name": "Switch", "folder": "switch", "extensions": [".nsp"], "command": ryujinx, "save_dir": ""}]}))
    switch = Config.load(path).system("switch")
    assert switch.command == ryujinx and switch.emulator == ""  # the user's choice of emulator stands


def test_a_fresh_install_defaults_the_switch_to_eden():
    switch = Config.new_install().system("switch")
    assert switch.emulator == "eden" and switch.command == "flatpak run dev.eden_emu.eden -g {rom}"
