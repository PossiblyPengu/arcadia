"""Backing up and restoring saves, settings and the library."""

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

import arcadia.backup as backup
from arcadia.backup import BackupError, create_backup, inspect_backup, restore_backup
from arcadia.config import Config
from arcadia.library import Library
from arcadia.scanner import Game


def make_setup(tmp_path, name="Arcadia"):
    """A home folder with a library, save states, an emulator's data, and an emulator program."""
    config = Config.new_install(tmp_path / name)
    config.ensure_layout()
    config_path = tmp_path / name / "config.json"
    config.save(config_path)

    library = Library(config.db_path)
    rom = config.rom_root_path / "psx" / "Game.cue"
    rom.write_text("x")
    library.sync("psx", [Game("psx", rom, "Game")])
    library.set_favorite(str(rom), True)
    library.record_session(str(rom), 1000.0, 600)
    library.close()
    config.journal_path.write_text('[{"time": 1, "moves": []}]')

    (config.savestate_path / "abc123").mkdir()
    (config.savestate_path / "abc123" / "Game.srm").write_text("my save")
    (config.media_path / "psx").mkdir()
    (config.media_path / "psx" / "Game.png").write_bytes(b"png" * 100)

    pcsx2 = config.emulators_path / "pcsx2"
    for sub, name_, text in (("config", "PCSX2.ini", "settings"), ("data", "memcards/Mcd001.ps2", "memory card"), ("state", "s.dat", "state"),
                             ("cache", "shaders.bin", "cache that is rebuilt"), ("app", "pcsx2.AppImage", "THE PROGRAM")):
        target = pcsx2 / sub / name_
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (pcsx2 / "install.json").write_text("{}")
    return config, config_path


NOW = datetime(2026, 3, 4, 12, 30, 15)


def names(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(zf.namelist())


# ======================= making a backup =======================

def test_a_backup_holds_saves_settings_and_library_but_not_programs_or_caches(tmp_path):
    config, config_path = make_setup(tmp_path)
    result = create_backup(config, config_path, now=NOW)
    assert result.path.parent == config.backups_path and result.path.suffix == ".zip"
    assert result.emulators == ["pcsx2"]
    assert names(result.path) == sorted([
        "manifest.json", "config.json", "data/library.db", "data/imports.json",
        "states/abc123/Game.srm",
        "emulators/pcsx2/config/PCSX2.ini", "emulators/pcsx2/data/memcards/Mcd001.ps2", "emulators/pcsx2/state/s.dat",
    ])  # no app/, no cache/, no ROMs, no covers
    assert result.files == 7 and not list(config.backups_path.glob("*.part"))


def test_covers_are_only_included_when_asked(tmp_path):
    config, config_path = make_setup(tmp_path)
    plain = create_backup(config, config_path, now=NOW)
    with_media = create_backup(config, config_path, include_media=True, now=NOW)
    assert not any(n.startswith("media/") for n in names(plain.path))
    assert "media/psx/Game.png" in names(with_media.path)
    assert inspect_backup(with_media.path).includes_media is True and inspect_backup(plain.path).includes_media is False


def test_the_library_is_backed_up_consistently_while_it_is_open(tmp_path):
    config, config_path = make_setup(tmp_path)
    library = Library(config.db_path)  # Arcadia has it open while the backup runs
    try:
        result = create_backup(config, config_path, now=NOW)
    finally:
        library.close()
    out = tmp_path / "out"
    with zipfile.ZipFile(result.path) as zf:
        zf.extract("data/library.db", out)
    row = sqlite3.connect(out / "data" / "library.db").execute("SELECT favorite, total_seconds FROM games").fetchone()
    assert row == (1, 600)


def test_backups_never_overwrite_each_other(tmp_path):
    config, config_path = make_setup(tmp_path)
    first = create_backup(config, config_path, now=NOW)
    second = create_backup(config, config_path, now=NOW)
    assert first.path != second.path and first.path.exists() and second.path.exists()
    assert second.path.name.endswith("-2.zip")


def test_progress_is_reported(tmp_path):
    config, config_path = make_setup(tmp_path)
    seen = []
    create_backup(config, config_path, progress=lambda done, total: seen.append((done, total)), now=NOW)
    assert seen[0][0] == 1 and seen[-1] == (7, 7)


def test_a_backup_can_go_somewhere_else(tmp_path):
    config, config_path = make_setup(tmp_path)
    result = create_backup(config, config_path, dest_dir=tmp_path / "usb" / "backups", now=NOW)
    assert result.path.parent == tmp_path / "usb" / "backups"


def test_there_has_to_be_something_to_back_up(tmp_path):
    config = Config.new_install(tmp_path / "Empty")
    config.ensure_layout()
    with pytest.raises(BackupError, match="nothing to back up"):
        create_backup(config, tmp_path / "Empty" / "config.json")  # no config file, no data, no saves


# ======================= looking inside a backup =======================

def test_inspecting_a_backup_summarises_it(tmp_path):
    config, config_path = make_setup(tmp_path)
    info = inspect_backup(create_backup(config, config_path, now=NOW).path)
    assert info.files == 7 and info.emulators == ["pcsx2"]
    assert info.areas == {"settings": 1, "library": 2, "save states": 1, "saves": 0, "covers": 0, "emulators": 3}
    assert info.created.startswith("2026-03-04")


def test_things_that_are_not_backups_are_refused(tmp_path):
    (tmp_path / "text.zip").write_text("not a zip")
    with pytest.raises(BackupError, match="isn't a backup file"):
        inspect_backup(tmp_path / "text.zip")
    with zipfile.ZipFile(tmp_path / "plain.zip", "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(BackupError, match="no manifest"):
        inspect_backup(tmp_path / "plain.zip")
    with zipfile.ZipFile(tmp_path / "future.zip", "w") as zf:
        zf.writestr("manifest.json", json.dumps({"arcadia_backup": 99}))
    with pytest.raises(BackupError, match="can't read"):
        inspect_backup(tmp_path / "future.zip")


def _hostile(tmp_path, *members):
    path = tmp_path / "hostile.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"arcadia_backup": backup.FORMAT}))
        for name in members:
            zf.writestr(name, "pwned")
    return path


@pytest.mark.parametrize(
    "name",
    [
        "emulators/pcsx2/app/pcsx2.AppImage",  # a program: never restored
        "emulators/pcsx2/cache/x",
        "emulators/pcsx2/config",  # too shallow to be a file
        "emulators/../evil",
        "emulators/pcsx2/config/../../../evil",
        "../evil.txt",
        "/etc/evil",
        "states/../../evil",
        "data/other.db",
        "data/sub/library.db",
        "config.json/extra",
        "somewhere/else.txt",
        "emulators/-bad id/config/x",
    ],
)
def test_a_backup_can_only_hold_saves_and_settings(tmp_path, name):
    with pytest.raises(BackupError):
        inspect_backup(_hostile(tmp_path, name))


def test_a_hostile_backup_restores_nothing_and_writes_nowhere(tmp_path):
    config, config_path = make_setup(tmp_path)
    before = (config.emulators_path / "pcsx2" / "app" / "pcsx2.AppImage").read_text()
    evil = _hostile(tmp_path, "states/ok.txt", "emulators/pcsx2/app/pcsx2.AppImage")
    with pytest.raises(BackupError):
        restore_backup(config, config_path, evil, now=NOW)
    assert (config.emulators_path / "pcsx2" / "app" / "pcsx2.AppImage").read_text() == before
    assert not (config.savestate_path / "ok.txt").exists()  # nothing was applied, not even the harmless part


# ======================= restoring =======================

def test_restore_brings_back_saves_settings_and_the_library(tmp_path):
    config, config_path = make_setup(tmp_path)
    archive = create_backup(config, config_path, now=NOW).path

    # ...then things go wrong
    (config.savestate_path / "abc123" / "Game.srm").write_text("corrupted")
    (config.emulators_path / "pcsx2" / "config" / "PCSX2.ini").unlink()
    shutil.rmtree(config.emulators_path / "pcsx2" / "data")
    config.db_path.unlink()

    result = restore_backup(config, config_path, archive, now=NOW)
    assert (config.savestate_path / "abc123" / "Game.srm").read_text() == "my save"
    assert (config.emulators_path / "pcsx2" / "config" / "PCSX2.ini").read_text() == "settings"
    assert (config.emulators_path / "pcsx2" / "data" / "memcards" / "Mcd001.ps2").read_text() == "memory card"
    assert sqlite3.connect(config.db_path).execute("SELECT favorite FROM games").fetchone() == (1,)
    assert set(result.areas) == {"settings", "library", "save states", "emulators"}
    assert not list(config.backups_path.glob(".restore-*"))  # the staging folder is gone


def test_what_a_restore_replaces_is_put_aside_not_deleted(tmp_path):
    config, config_path = make_setup(tmp_path)
    archive = create_backup(config, config_path, now=NOW).path
    (config.savestate_path / "abc123" / "Game.srm").write_text("newer progress")
    (config.savestate_path / "extra").mkdir()
    (config.savestate_path / "extra" / "new.srm").write_text("only in the live folder")

    result = restore_backup(config, config_path, archive, now=NOW)
    aside = result.replaced_to
    assert aside == config.backups_path / "before-restore-20260304-123015"
    assert (aside / "states" / "abc123" / "Game.srm").read_text() == "newer progress"
    assert (aside / "states" / "extra" / "new.srm").read_text() == "only in the live folder"
    assert not (config.savestate_path / "extra").exists()  # the states folder is the backup's, as it was


def test_the_emulators_program_and_cache_are_untouched_by_a_restore(tmp_path):
    config, config_path = make_setup(tmp_path)
    archive = create_backup(config, config_path, now=NOW).path
    restore_backup(config, config_path, archive, now=NOW)
    pcsx2 = config.emulators_path / "pcsx2"
    assert (pcsx2 / "app" / "pcsx2.AppImage").read_text() == "THE PROGRAM"
    assert (pcsx2 / "cache" / "shaders.bin").read_text() == "cache that is rebuilt"


def test_a_backup_restores_onto_a_different_machine_by_logical_names(tmp_path):
    config, config_path = make_setup(tmp_path, "Old")
    archive = create_backup(config, config_path, now=NOW).path
    new_config = Config.new_install(tmp_path / "New" / "Elsewhere")
    new_path = tmp_path / "New" / "Elsewhere" / "config.json"
    result = restore_backup(new_config, new_path, archive, now=NOW)
    assert (new_config.savestate_path / "abc123" / "Game.srm").read_text() == "my save"
    assert (new_config.emulators_path / "pcsx2" / "config" / "PCSX2.ini").exists()
    assert new_path.exists() and result.replaced_to is None  # nothing was there to replace


def test_a_damaged_backup_restores_nothing(tmp_path):
    config, config_path = make_setup(tmp_path)
    archive = create_backup(config, config_path, now=NOW).path
    with zipfile.ZipFile(archive) as zf:
        info = zf.getinfo("states/abc123/Game.srm")
    raw = bytearray(archive.read_bytes())
    raw[info.header_offset + 30 + len(info.filename.encode()) + 2] ^= 0xFF  # corrupt the saved data itself
    archive.write_bytes(bytes(raw))
    (config.savestate_path / "abc123" / "Game.srm").write_text("live")
    with pytest.raises(BackupError, match="damaged, so nothing was restored"):
        restore_backup(config, config_path, archive, now=NOW)
    assert (config.savestate_path / "abc123" / "Game.srm").read_text() == "live"


def test_a_failure_part_way_puts_everything_back(tmp_path, monkeypatch):
    config, config_path = make_setup(tmp_path)
    archive = create_backup(config, config_path, now=NOW).path
    (config.savestate_path / "abc123" / "Game.srm").write_text("live save")
    (config.emulators_path / "pcsx2" / "config" / "PCSX2.ini").write_text("live settings")

    real_move, calls = shutil.move, {"n": 0}

    def flaky(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] == 5:  # a few pieces are already swapped when this one fails
            raise OSError(28, "No space left on device")
        return real_move(src, dst, *a, **k)

    monkeypatch.setattr(backup.shutil, "move", flaky)
    with pytest.raises(BackupError, match="undone"):
        restore_backup(config, config_path, archive, now=NOW)
    monkeypatch.setattr(backup.shutil, "move", real_move)

    assert (config.savestate_path / "abc123" / "Game.srm").read_text() == "live save"
    assert (config.emulators_path / "pcsx2" / "config" / "PCSX2.ini").read_text() == "live settings"
    assert not list(config.backups_path.glob(".restore-*"))
