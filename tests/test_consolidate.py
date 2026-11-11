"""Bringing an existing library into the Arcadia folder."""

import os
import sqlite3
from pathlib import Path

import pytest

import arcadia.consolidate as consolidate
from arcadia.config import Config
from arcadia.consolidate import (
    ConsolidateError,
    adopt_home,
    bring_in,
    match_system,
    migrate_data,
    scan_source,
)
from arcadia.library import Library
from arcadia.scanner import Game
from arcadia.sorter import Journal, SortError


def put(path: Path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def config(tmp_path):
    cfg = Config.new_install(tmp_path / "Arcadia")
    cfg.ensure_layout()
    return cfg


def chosen(folders, assignments=None):
    """Each scanned folder paired with its guessed system, unless overridden by name."""
    assignments = assignments or {}
    return [(f, assignments.get(f.path.name, f.system_id)) for f in folders]


# ======================= naming =======================

@pytest.mark.parametrize(
    "folder, system",
    [
        # our own names
        ("psx", "psx"), ("gamecube", "gc"), ("mastersystem", "sms"), ("3ds", "n3ds"), ("pcengine", "pcengine"),
        # RetroPie / Batocera / EmuDeck / ES-DE style names
        ("megadrive", "genesis"), ("MegaDrive", "genesis"), ("atarilynx", "lynx"), ("wswan", "wonderswan"),
        ("mame-libretro", "arcade"), ("fbneo", "arcade"), ("ngpc", "ngp"), ("msx1", "msx"), ("amiga1200", "amiga"),
        ("ps1", "psx"), ("PlayStation", "psx"), ("Game Boy Advance", "gba"), ("game_boy_color", "gbc"),
        ("Super Nintendo", "snes"), ("Sega Genesis", "genesis"), ("TurboGrafx-16", "pcengine"), ("Nintendo DS", "nds"),
        ("nsw", "switch"), ("dc", "dreamcast"), ("N64", "n64"), ("PSP", "psp"), ("PS2", "ps2"),
    ],
)
def test_folder_names_from_other_setups_are_matched(config, folder, system):
    assert match_system(folder, config) == system


@pytest.mark.parametrize("folder", ["Photos", "backup", "bios", "", "---", "roms2", "Saves"])
def test_names_that_are_not_systems_are_left_unmatched(config, folder):
    assert match_system(folder, config) is None


def test_every_alias_points_at_a_real_system_and_no_two_systems_share_one(config):
    ids = {s.id for s in config.systems}
    assert set(consolidate.ALIASES) <= ids
    seen: dict[str, str] = {}
    for system in config.systems:
        for name in {consolidate._norm(system.folder), consolidate._norm(system.id), consolidate._norm(system.name),
                     *consolidate.ALIASES.get(system.id, ())}:
            assert seen.setdefault(name, system.id) == system.id, f"{name!r} claimed by {seen[name]} and {system.id}"


# ======================= scanning =======================

def make_old_library(tmp_path):
    old = tmp_path / "OldROMs"
    put(old / "nes" / "Contra.nes", b"n" * 100)
    put(old / "nes" / "Zelda.nes", b"z" * 200)
    put(old / "PlayStation" / "Crash" / "Crash.cue", b"c" * 50)
    put(old / "PlayStation" / "Crash" / "Crash.bin", b"b" * 500)
    put(old / "Photos" / "holiday.jpg", b"j" * 30)
    put(old / "megadrive" / ".DS_Store", b"junk")
    put(old / "megadrive" / "Sonic.md", b"s" * 70)
    put(old / "loose.txt", b"ignored: not in a system folder")
    return old


def test_scan_lists_each_folder_with_its_guess_and_size(tmp_path, config):
    old = make_old_library(tmp_path)
    found = {f.path.name: f for f in scan_source(old, config, config.rom_root_path)}
    assert set(found) == {"nes", "PlayStation", "Photos", "megadrive"}
    assert (found["nes"].system_id, found["nes"].files, found["nes"].bytes, found["nes"].entries) == ("nes", 2, 300, 2)
    assert (found["PlayStation"].system_id, found["PlayStation"].files, found["PlayStation"].entries) == ("psx", 2, 1)
    assert found["megadrive"].system_id == "genesis" and found["megadrive"].entries == 1  # the .DS_Store isn't counted as a game
    assert found["Photos"].system_id is None


def test_the_new_rom_folder_is_never_offered_as_a_source(tmp_path, config):
    with pytest.raises(ConsolidateError, match="already the ROM folder"):
        scan_source(config.rom_root_path, config, config.rom_root_path)
    with pytest.raises(ConsolidateError, match="doesn't exist"):
        scan_source(tmp_path / "nope", config, config.rom_root_path)
    # a source that contains the Arcadia folder doesn't offer to move it into itself
    home = tmp_path / "Arcadia"
    found = scan_source(tmp_path, config, config.rom_root_path)
    assert home not in [f.path for f in found]


# ======================= moving and copying =======================

def test_move_puts_everything_in_the_right_system_folder_and_is_undoable(tmp_path, config):
    old = make_old_library(tmp_path)
    folders = scan_source(old, config, config.rom_root_path)
    journal = Journal(config.journal_path)
    result = bring_in(chosen(folders), config, config.rom_root_path, "move", journal)

    roms = config.rom_root_path
    assert (roms / "nes" / "Contra.nes").read_bytes() == b"n" * 100
    assert (roms / "psx" / "Crash" / "Crash.bin").read_bytes() == b"b" * 500  # a game folder moved whole
    assert (roms / "genesis" / "Sonic.md").exists()
    assert not (old / "nes" / "Contra.nes").exists() and (old / "Photos" / "holiday.jpg").exists()  # unmatched: untouched
    assert (old / "megadrive" / ".DS_Store").exists()  # hidden files are left where they were
    assert (result.moved, result.copied, result.skipped) == (4, 0, []) and result.bytes == 300 + 550 + 70

    restored, problems = journal.undo_last()
    assert (restored, problems) == (4, [])
    assert (old / "nes" / "Contra.nes").exists() and (old / "PlayStation" / "Crash" / "Crash.cue").exists()
    assert not (roms / "nes" / "Contra.nes").exists()


def test_copy_leaves_the_originals_alone(tmp_path, config):
    old = make_old_library(tmp_path)
    journal = Journal(config.journal_path)
    result = bring_in(chosen(scan_source(old, config, config.rom_root_path)), config, config.rom_root_path, "copy", journal)
    assert (old / "nes" / "Contra.nes").exists() and (config.rom_root_path / "nes" / "Contra.nes").exists()
    assert result.copied == 4 and result.moved == 0
    assert not journal.can_undo()  # nothing was moved, so there's nothing to put back
    assert not list(config.rom_root_path.rglob("*.arcadia-part"))


def test_the_user_can_assign_a_system_to_a_folder_the_names_missed(tmp_path, config):
    old = make_old_library(tmp_path)
    put(old / "My Saturn Games" / "Nights.cue")
    folders = scan_source(old, config, config.rom_root_path)
    assert next(f for f in folders if f.path.name == "My Saturn Games").system_id is None
    bring_in(chosen(folders, {"My Saturn Games": "saturn"}), config, config.rom_root_path, "move", Journal(config.journal_path))
    assert (config.rom_root_path / "saturn" / "Nights.cue").exists()


def test_nothing_in_the_destination_is_ever_overwritten(tmp_path, config):
    old = make_old_library(tmp_path)
    put(config.rom_root_path / "nes" / "Contra.nes", b"already here, precious")
    result = bring_in(chosen(scan_source(old, config, config.rom_root_path)), config, config.rom_root_path, "move",
                      Journal(config.journal_path))
    assert (config.rom_root_path / "nes" / "Contra.nes").read_bytes() == b"already here, precious"
    assert (old / "nes" / "Contra.nes").exists()  # and the one that couldn't move stays put
    assert [(p.name, why) for p, why in result.skipped] == [("Contra.nes", "already exists in the Arcadia folder")]
    assert result.moved == 3  # the rest still went


def test_a_failure_on_one_item_does_not_stop_the_others(tmp_path, config, monkeypatch):
    old = make_old_library(tmp_path)
    real = consolidate.safe_move

    def flaky(src, dst):
        if src.name == "Zelda.nes":
            raise SortError("disk full")
        real(src, dst)

    monkeypatch.setattr(consolidate, "safe_move", flaky)
    result = bring_in(chosen(scan_source(old, config, config.rom_root_path)), config, config.rom_root_path, "move",
                      Journal(config.journal_path))
    assert [(p.name, why) for p, why in result.skipped] == [("Zelda.nes", "disk full")]
    assert (old / "nes" / "Zelda.nes").exists() and (config.rom_root_path / "nes" / "Contra.nes").exists()
    assert result.moved == 3


def test_progress_reports_each_item(tmp_path, config):
    old = make_old_library(tmp_path)
    seen = []
    bring_in(chosen(scan_source(old, config, config.rom_root_path)), config, config.rom_root_path, "copy",
             Journal(config.journal_path), progress=lambda done, total, name: seen.append((done, total, name)))
    assert [s[0] for s in seen] == [1, 2, 3, 4] and all(s[1] == 4 for s in seen)
    assert {s[2] for s in seen} == {"Contra.nes", "Zelda.nes", "Crash", "Sonic.md"}


def test_an_incomplete_copy_is_discarded_and_the_original_kept(tmp_path, config, monkeypatch):
    old = make_old_library(tmp_path)
    real = consolidate.shutil.copytree

    def lossy(src, dst, symlinks=False):
        os.makedirs(dst)
        Path(dst, "only.txt").write_bytes(b"1")  # most of the game is missing

    monkeypatch.setattr(consolidate.shutil, "copytree", lossy)
    result = bring_in(chosen(scan_source(old, config, config.rom_root_path)), config, config.rom_root_path, "copy",
                      Journal(config.journal_path))
    monkeypatch.setattr(consolidate.shutil, "copytree", real)
    assert [(p.name, "incomplete" in why) for p, why in result.skipped] == [("Crash", True)]
    assert not (config.rom_root_path / "psx" / "Crash").exists()
    assert not list(config.rom_root_path.rglob("*.arcadia-part"))
    assert (old / "PlayStation" / "Crash" / "Crash.bin").exists()


def test_a_folder_that_contains_the_destination_is_never_moved_into_itself(tmp_path):
    config = Config.new_install(tmp_path / "Everything")
    config.ensure_layout()
    # the ROM folder holds a subfolder named like a system that actually contains the destination
    nested = Config(rom_root=str(tmp_path / "Everything" / "roms" / "nes"), systems=config.systems)
    folder = consolidate.SourceFolder(tmp_path / "Everything", "nes", 0, 0, 1)
    result = bring_in([(folder, "nes")], nested, tmp_path / "Everything" / "roms", "move", Journal(tmp_path / "j.json"))
    assert result.moved == 0 and result.copied == 0
    assert [(p.name, "contains, or is inside" in why) for p, why in result.skipped] == [("Everything", True)]
    for name in ("data", "media", "states", "emulators", "bios", "backups"):
        assert (tmp_path / "Everything" / name).is_dir()  # the Arcadia folder's own folders were not touched
    assert not (tmp_path / "Everything" / "roms" / "nes" / "data").exists()


def test_the_mode_must_be_move_or_copy(tmp_path, config):
    with pytest.raises(ConsolidateError):
        bring_in([], config, config.rom_root_path, "delete", Journal(config.journal_path))


# ======================= library data =======================

def make_legacy(tmp_path):
    """An older setup: everything scattered, with a library, covers and snapshots."""
    legacy = Config(rom_root=str(tmp_path / "OldROMs"), data_dir=str(tmp_path / "olddata"))
    (tmp_path / "olddata").mkdir()
    rom = put(tmp_path / "OldROMs" / "nes" / "Contra.nes")
    library = Library(legacy.db_path)
    library.sync("nes", [Game("nes", rom, "Contra")])
    library.set_favorite(str(rom), True)
    library.record_session(str(rom), 1000.0, 900)
    library.close()
    put(legacy.journal_path, b"[]")
    put(legacy.media_path / "nes" / "Contra.png", b"cover")
    put(legacy.savestate_path / "abc" / "Contra.srm", b"save")
    return legacy


def test_library_covers_and_snapshots_are_copied_not_moved(tmp_path):
    legacy = make_legacy(tmp_path)
    home = tmp_path / "Arcadia"
    notes = migrate_data(legacy, home)
    new = Config.new_install(home)

    row = sqlite3.connect(new.db_path).execute("SELECT favorite, total_seconds FROM games").fetchone()
    assert row == (1, 900)
    assert (new.media_path / "nes" / "Contra.png").read_bytes() == b"cover"
    assert (new.savestate_path / "abc" / "Contra.srm").read_bytes() == b"save"
    assert new.journal_path.exists()
    assert legacy.db_path.exists() and (legacy.media_path / "nes" / "Contra.png").exists()  # the old setup still works
    assert any("library" in n for n in notes) and any("covers" in n for n in notes) and any("save-state" in n for n in notes)


def test_existing_data_in_the_arcadia_folder_is_never_overwritten(tmp_path):
    legacy = make_legacy(tmp_path)
    home = tmp_path / "Arcadia"
    new = Config.new_install(home)
    new.ensure_layout()
    sqlite3.connect(new.db_path).executescript("CREATE TABLE marker(x); INSERT INTO marker VALUES (1);")
    put(new.media_path / "keep.png", b"mine")
    notes = migrate_data(legacy, home)
    assert sqlite3.connect(new.db_path).execute("SELECT x FROM marker").fetchone() == (1,)
    assert (new.media_path / "keep.png").read_bytes() == b"mine" and not (new.media_path / "nes").exists()
    assert any("already has" in n for n in notes)
    assert (new.savestate_path / "abc" / "Contra.srm").exists()  # the empty snapshots folder was filled


def test_migrating_when_the_data_is_already_in_place_does_nothing(tmp_path, config):
    assert migrate_data(config, tmp_path / "Arcadia") == []


def test_the_database_is_copied_consistently_while_it_is_open(tmp_path):
    legacy = make_legacy(tmp_path)
    open_library = Library(legacy.db_path)
    try:
        migrate_data(legacy, tmp_path / "Arcadia")
    finally:
        open_library.close()
    assert sqlite3.connect(Config.new_install(tmp_path / "Arcadia").db_path).execute("SELECT COUNT(*) FROM games").fetchone() == (1,)


def test_adopting_the_home_folder_only_repoints_what_was_brought_in(tmp_path):
    legacy = make_legacy(tmp_path)
    legacy.media_dir = str(tmp_path / "covers")
    home = tmp_path / "Arcadia"

    adopt_home(legacy, home, roms=True, data=False)
    assert legacy.home_dir == str(home) and legacy.rom_root == ""  # ROMs now live in the Arcadia folder
    assert legacy.data_dir == str(tmp_path / "olddata") and legacy.media_dir == str(tmp_path / "covers")  # data stays put

    adopt_home(legacy, home, roms=False, data=True)
    assert legacy.data_dir == "" and legacy.media_dir == "" and legacy.savestate_dir == ""
    assert legacy.data_path == home / "data" and legacy.rom_root_path == home / "roms"


def test_folders_are_listed_in_a_natural_order_ignoring_case(tmp_path, config):
    old = tmp_path / "Library"
    for name in ("snes", "Photos", "megadrive", "Game Boy Advance", "nes"):
        put(old / name / "f.rom")
    names = [f.path.name for f in scan_source(old, config, config.rom_root_path)]
    assert names == ["Game Boy Advance", "megadrive", "nes", "Photos", "snes"]
