"""Sweeping the downloads folder: finding it, and looking inside subfolders."""

import os
import time
from pathlib import Path

import pytest

import isoutil
from arcadia.config import Config
from arcadia.consolidate import config_for_home, default_downloads_dir
from arcadia.sorter import Confidence, default_selection, sweep


def put(path: Path, data=b"x", age=3600.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def nes():
    return b"NES\x1a" + bytes(0x4000)


def gb():
    data = bytearray(0x200)
    data[0x104:0x10C] = bytes.fromhex("CEED6666CC0D000B")
    return bytes(data)


@pytest.fixture
def config(tmp_path):
    return Config.new_install(tmp_path / "Arcadia")


# ======================= finding the downloads folder =======================

def test_the_downloads_folder_defaults_to_downloads_in_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert default_downloads_dir(tmp_path) == tmp_path / "Downloads"  # e.g. /home/deck/Downloads on a Steam Deck


@pytest.mark.parametrize(
    "line, expected",
    [
        ('XDG_DOWNLOAD_DIR="$HOME/Downloads"', "Downloads"),
        ('XDG_DOWNLOAD_DIR="$HOME/Téléchargements"', "Téléchargements"),  # a translated desktop
        ('XDG_DOWNLOAD_DIR="$HOME/stuff/incoming"', "stuff/incoming"),
        ("XDG_DOWNLOAD_DIR=$HOME/Plain", "Plain"),
    ],
)
def test_the_real_downloads_folder_is_read_from_the_user_dirs_file(tmp_path, monkeypatch, line, expected):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text(f'# comment\nXDG_DESKTOP_DIR="$HOME/Desktop"\n{line}\nXDG_MUSIC_DIR="$HOME/Music"\n')
    assert default_downloads_dir(tmp_path) == tmp_path / expected


def test_an_absolute_downloads_folder_is_used_as_is(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="/run/media/deck/sdcard/Downloads"\n')
    assert default_downloads_dir(tmp_path) == Path("/run/media/deck/sdcard/Downloads")


def test_xdg_config_home_is_respected(tmp_path, monkeypatch):
    elsewhere = tmp_path / "cfg"
    elsewhere.mkdir()
    (elsewhere / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Incoming"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(elsewhere))
    assert default_downloads_dir(tmp_path) == tmp_path / "Incoming"


@pytest.mark.parametrize("content", ["", "garbage", 'XDG_DOWNLOAD_DIR="$HOME"', 'XDG_DOWNLOAD_DIR="relative/path"', 'XDG_DOWNLOAD_DIR=""'])
def test_a_missing_or_useless_setting_falls_back_to_the_usual_folder(tmp_path, monkeypatch, content):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text(content)
    assert default_downloads_dir(tmp_path) == tmp_path / "Downloads"  # "$HOME" means the user turned the folder off


# ======================= the destination config =======================

def test_the_destination_config_puts_roms_in_the_arcadia_folder_and_keeps_the_systems(tmp_path):
    legacy = Config(rom_root="/old/ROMs", data_dir="/old/data")
    legacy.system("psx").folder = "ps1"  # a name the user chose
    target = config_for_home(legacy, tmp_path / "Arcadia")
    assert target.rom_root_path == tmp_path / "Arcadia" / "roms" and target.system("psx").folder == "ps1"
    assert legacy.rom_root_path == Path("/old/ROMs")  # the original is not changed


# ======================= sweeping =======================

def test_roms_at_the_top_level_and_in_subfolders_are_found(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / "Contra.nes", nes())
    put(dl / "Pokemon pack" / "Tetris.gb", gb())
    put(dl / "Pokemon pack" / "extras" / "Mario.nes", nes())
    put(dl / "holiday.jpg", b"jpg")
    put(dl / "docs" / "report.pdf", b"pdf")
    plan = sweep(dl, config)
    assert sorted(i.source.name for i in plan.items) == ["Contra.nes", "Mario.nes", "Tetris.gb"]
    by_name = {i.source.name: i for i in plan.items}
    assert by_name["Tetris.gb"].system_id == "gb" and by_name["Tetris.gb"].destination == tmp_path / "Arcadia" / "roms" / "gb" / "Tetris.gb"
    assert len(plan.ignored) == 2  # the photo and the pdf are counted, never listed as ROMs


def test_the_search_stops_at_the_depth_limit(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / "a" / "b" / "two.nes", nes())  # two levels down: found
    put(dl / "a" / "b" / "c" / "three.nes", nes())  # three levels down: not looked at
    assert [i.source.name for i in sweep(dl, config, depth=2).items] == ["two.nes"]
    assert sorted(i.source.name for i in sweep(dl, config, depth=3).items) == ["three.nes", "two.nes"]
    assert [i.source.name for i in sweep(dl, config, depth=0).items] == []  # depth 0 is the top level only


def test_hidden_folders_are_never_searched(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / ".cache" / "hidden.nes", nes())
    put(dl / "visible" / "shown.nes", nes())
    assert [i.source.name for i in sweep(dl, config).items] == ["shown.nes"]


def test_excluded_folders_and_their_parents_are_skipped(tmp_path, config):
    dl = tmp_path / "Downloads"
    library = dl / "MyLibrary"  # say the downloads folder holds the library being migrated
    put(library / "nes" / "InLibrary.nes", nes())
    put(dl / "other" / "Loose.nes", nes())
    plan = sweep(dl, config, exclude=[library])
    assert [i.source.name for i in plan.items] == ["Loose.nes"]
    # excluding something *inside* a folder also keeps that folder from being searched
    plan = sweep(dl, config, exclude=[library / "nes"])
    assert "InLibrary.nes" not in [i.source.name for i in plan.items]


def test_a_game_folder_is_taken_whole_and_not_searched(tmp_path, config):
    dl = tmp_path / "Downloads"
    game = dl / "BLUS30443"
    put(game / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", b"\x7fSELF")
    put(game / "PS3_GAME" / "USRDIR" / "stray.nes", nes())  # inside a game: not a separate ROM
    for dirpath, _d, files in os.walk(game):
        for name in files + _d:
            os.utime(os.path.join(dirpath, name), (time.time() - 3600,) * 2)
        os.utime(dirpath, (time.time() - 3600,) * 2)
    plan = sweep(dl, config)
    assert [(i.source.name, i.system_id) for i in plan.items] == [("BLUS30443", "ps3")]


def test_the_same_kinds_of_confidence_apply_in_subfolders(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / "stuff" / "Mislabelled.gbc", gb())  # a Game Boy header in a .gbc file: asks
    put(dl / "stuff" / "Fine.nes", nes())
    items = {i.source.name: i for i in sweep(dl, config).items}
    assert items["Fine.nes"].confidence is Confidence.CERTAIN and items["Mislabelled.gbc"].confidence is Confidence.UNSURE
    chosen = default_selection(list(items.values()))
    assert [i.source.name for i in chosen] == ["Fine.nes"]  # the uncertain one is never moved without being asked


def test_default_selection_leaves_out_collisions(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / "Contra.nes", nes())
    put(config.rom_root_path / "nes" / "Contra.nes", b"already here")
    (item,) = sweep(dl, config).items
    assert item.exists and default_selection([item]) == []


def test_files_still_downloading_in_subfolders_are_reported_as_waiting(tmp_path, config):
    dl = tmp_path / "Downloads"
    put(dl / "sub" / "Fresh.nes", nes(), age=0)
    plan = sweep(dl, config)
    assert plan.items == [] and [p.name for p in plan.waiting] == ["Fresh.nes"]


def test_a_huge_tree_is_cut_off_rather_than_walked_forever(tmp_path, config):
    dl = tmp_path / "Downloads"
    for i in range(30):
        put(dl / f"d{i:02}" / f"g{i}.nes", nes())
    assert len(sweep(dl, config, max_dirs=10).items) == 10
    assert len(sweep(dl, config, max_dirs=1000).items) == 30


def test_a_missing_folder_gives_an_empty_plan(tmp_path, config):
    plan = sweep(tmp_path / "nope", config)
    assert plan.items == [] and plan.ignored == [] and plan.waiting == []
