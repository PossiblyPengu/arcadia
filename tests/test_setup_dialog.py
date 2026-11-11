"""The Setup window: overview, bringing a library in, backing up and restoring."""

import json
import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

import arcadia.consolidate as consolidate  # noqa: E402
import arcadia.setup_dialog as setup_dialog  # noqa: E402
from arcadia.backup import create_backup  # noqa: E402
from arcadia.config import Config  # noqa: E402
from arcadia.emulators import Installer  # noqa: E402
from arcadia.library import Library  # noqa: E402
from arcadia.scanner import Game  # noqa: E402
from arcadia.setup_dialog import BackupDialog, BringInDialog, SetupDialog  # noqa: E402
from arcadia.sorter import Journal, SortError  # noqa: E402
from qtutil import SyncTask  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def synchronous(monkeypatch):
    monkeypatch.setattr(setup_dialog, "TaskClass", SyncTask)


@pytest.fixture
def boxes(monkeypatch):
    """Answer every question 'yes' and record every message shown."""
    shown = {"info": [], "warn": [], "ask": []}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: shown["ask"].append(a[2]) or QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown["info"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown["warn"].append(a[2]))
    return shown


def put(path: Path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def cells(table, row):
    return [table.item(row, c).text() if table.item(row, c) else "" for c in range(table.columnCount())]


def install_fake(config, emu_id, version="v2.2.0"):
    installer = Installer(config.emulators_path)
    app = installer.app_dir(emu_id)
    app.mkdir(parents=True)
    (app / "emu").write_text("#!/bin/sh\n")
    record = {"id": emu_id, "version": version, "asset": "emu", "sha256": "0" * 64, "verified": True, "exe": "emu"}
    (installer.folder(emu_id) / "install.json").write_text(json.dumps(record))
    return installer


# ======================= the overview =======================

def make_hub(tmp_path, counts=None, config=None, flatpak=None):
    config = config or Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    installer = install_fake(config, "pcsx2")
    return SetupDialog(
        config, tmp_path / "Arcadia" / "config.json", Journal(config.journal_path),
        counts if counts is not None else {"ps2": 5, "snes": 2, "nes": 4},
        installer=installer, flatpak_check=flatpak or (lambda app: app != "com.snes9x.Snes9x"),
    )


def test_the_overview_says_what_is_ready_and_what_to_do_about_the_rest(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # so RetroArch's core folder is somewhere we control
    hub = make_hub(tmp_path)

    def rows():
        return {cells(hub.table, r)[0]: cells(hub.table, r) for r in range(hub.table.rowCount())}

    now = rows()
    assert set(now) == {"Nintendo Entertainment System", "Super Nintendo", "PlayStation 2"}
    assert now["PlayStation 2"][1:4] == ["5", "PCSX2 v2.2.0", "✓ Ready"]  # installed in the Arcadia folder
    snes = now["Super Nintendo"]  # its Flatpak isn't installed
    assert snes[3] == "⚠ Needs attention" and "flatpak install flathub com.snes9x.Snes9x" in snes[4]
    nes = now["Nintendo Entertainment System"]  # the Flatpak is there but the RetroArch core hasn't been downloaded
    assert nes[3] == "⚠ Needs attention" and "Core missing: nestopia_libretro.so" in nes[2] and "Core Downloader" in nes[4]
    assert "1 of 3 systems ready" in hub.status.text()

    core = tmp_path / "home" / ".var/app/org.libretro.RetroArch/config/retroarch/cores/nestopia_libretro.so"
    core.parent.mkdir(parents=True)
    core.write_text("core")
    hub.refresh()  # "Check again" after downloading it
    assert rows()["Nintendo Entertainment System"][3:] == ["✓ Ready", ""] and "2 of 3 systems ready" in hub.status.text()
    hub.close()


def test_the_overview_shows_how_much_space_each_part_takes(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    put(config.rom_root_path / "ps2" / "g.iso", b"1" * 2048)
    hub = make_hub(tmp_path, config=config)
    assert "ROMs 2.0 KB" in hub.sizes.text() and "Emulators" in hub.sizes.text() and "Backups" in hub.sizes.text()
    hub.close()


def test_every_system_can_be_shown(qapp, tmp_path):
    hub = make_hub(tmp_path)
    few = hub.table.rowCount()
    hub.all_box.setChecked(True)
    assert hub.table.rowCount() == len(hub.config.systems) > few
    hub.close()


def test_a_setup_that_is_still_scattered_says_so_and_a_tidy_one_names_its_folder(qapp, tmp_path):
    legacy = Config(rom_root=str(tmp_path / "ROMs"), data_dir=str(tmp_path / "data"))
    hub = make_hub(tmp_path, config=legacy, counts={})
    assert "spread across several places" in hub.where.text() and not hub.open_btn.isEnabled()
    hub.close()
    tidy = make_hub(tmp_path / "x", counts={})
    assert str(tmp_path / "x" / "Arcadia") in tidy.where.text() and tidy.open_btn.isEnabled()
    tidy.close()


def test_a_failing_check_is_reported_not_raised(qapp, tmp_path):
    def broken(app):
        raise RuntimeError("flatpak exploded")

    hub = make_hub(tmp_path, flatpak=broken)
    assert "Couldn't check" in hub.status.text() and hub.table.rowCount() == 0
    hub.close()


def test_the_hub_remembers_what_its_sub_windows_did(qapp, tmp_path, monkeypatch):
    hub = make_hub(tmp_path)

    def fake_bring_in(self):
        self.changed = True
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(BringInDialog, "exec", fake_bring_in)
    monkeypatch.setattr(BackupDialog, "exec", lambda self: setattr(self, "restored", True) or QDialog.DialogCode.Accepted)
    monkeypatch.setattr(setup_dialog.EmulatorsDialog, "exec", lambda self: setattr(self, "changed", True) or QDialog.DialogCode.Accepted)
    hub.bring_in()
    hub.backups()
    hub.emulators()
    assert hub.config_changed and hub.restored and hub.emulators_changed
    hub.close()


# ======================= bringing a library in =======================

def make_old_library(tmp_path):
    old = tmp_path / "OldROMs"
    put(old / "nes" / "Contra.nes", b"n" * 100)
    put(old / "PlayStation" / "Crash" / "Crash.cue", b"c")
    put(old / "megadrive" / "Sonic.md", b"s" * 70)
    put(old / "Photos" / "holiday.jpg", b"j")
    return old


def legacy_config(tmp_path):
    legacy = Config(rom_root=str(tmp_path / "OldROMs"), data_dir=str(tmp_path / "olddata"))
    (tmp_path / "olddata").mkdir()
    rom = put(tmp_path / "OldROMs" / "nes" / "Contra.nes", b"n" * 100)
    library = Library(legacy.db_path)
    library.sync("nes", [Game("nes", rom, "Contra")])
    library.set_favorite(str(rom), True)
    library.close()
    return legacy


def bring_in_dialog(tmp_path, config=None):
    old = make_old_library(tmp_path)
    config = config or Config(rom_root=str(old), data_dir=str(tmp_path / "olddata"))
    dialog = BringInDialog(config, Journal(config.journal_path))
    dialog.home_edit.setText(str(tmp_path / "Arcadia"))
    dialog.source_edit.setText(str(old))
    dialog.scan()
    return dialog, old


def rows_by_name(dialog):
    return {dialog.table.item(r, 1).text(): r for r in range(dialog.table.rowCount())}


def test_scanning_shows_each_folder_matched_to_a_system(qapp, tmp_path):
    dialog, _old = bring_in_dialog(tmp_path)
    rows = rows_by_name(dialog)
    assert set(rows) == {"nes", "PlayStation", "megadrive", "Photos"}
    combo = lambda name: dialog.table.cellWidget(rows[name], 4)
    assert (combo("nes").currentData(), combo("PlayStation").currentData(), combo("megadrive").currentData()) == ("nes", "psx", "genesis")
    assert combo("Photos").currentData() is None
    assert dialog.table.item(rows["nes"], 0).checkState() == Qt.CheckState.Checked
    assert dialog.table.item(rows["Photos"], 0).checkState() == Qt.CheckState.Unchecked  # unrecognised: left alone
    assert "3 folders will be brought in" in dialog.summary.text() and "1 left alone" in dialog.summary.text()
    assert dialog.start_btn.isEnabled()
    dialog.close()


def test_choosing_a_system_for_an_unrecognised_folder_ticks_it(qapp, tmp_path):
    dialog, _old = bring_in_dialog(tmp_path)
    row = rows_by_name(dialog)["Photos"]
    combo = dialog.table.cellWidget(row, 4)
    combo.setCurrentIndex(combo.findData("gba"))
    assert dialog.table.item(row, 0).checkState() == Qt.CheckState.Checked
    assert ("Photos", "gba") in [(f.path.name, s) for f, s in dialog.chosen()]
    combo.setCurrentIndex(0)  # back to "leave alone"
    assert dialog.table.item(row, 0).checkState() == Qt.CheckState.Unchecked
    dialog.close()


def test_moving_a_library_in_end_to_end(qapp, tmp_path, boxes):
    config = legacy_config(tmp_path)
    dialog, old = bring_in_dialog(tmp_path, config)
    assert dialog.mode.currentData() == "move"
    dialog.start()

    home = tmp_path / "Arcadia"
    assert (home / "roms" / "nes" / "Contra.nes").read_bytes() == b"n" * 100
    assert (home / "roms" / "psx" / "Crash" / "Crash.cue").exists() and (home / "roms" / "genesis" / "Sonic.md").exists()
    assert not (old / "nes" / "Contra.nes").exists() and (old / "Photos" / "holiday.jpg").exists()
    assert (home / "data" / "library.db").exists()  # favorites and playtime came along
    assert config.home_dir == str(home) and config.rom_root == "" and config.data_dir == ""
    assert config.rom_root_path == home / "roms"
    assert dialog.changed and dialog.result() == QDialog.DialogCode.Accepted
    assert "Restart Arcadia" in boxes["info"][-1] and "moved" in boxes["info"][-1]
    assert boxes["ask"] and "roms" in boxes["ask"][0]  # it asked first


def test_copying_keeps_the_old_folder_as_it_was(qapp, tmp_path, boxes):
    dialog, old = bring_in_dialog(tmp_path)
    dialog.mode.setCurrentIndex(dialog.mode.findData("copy"))
    dialog.start()
    assert (old / "nes" / "Contra.nes").exists() and (tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes").exists()
    assert "copied" in boxes["info"][-1]
    assert not dialog.journal.can_undo()


def test_declining_the_confirmation_moves_nothing(qapp, tmp_path, monkeypatch):
    dialog, old = bring_in_dialog(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dialog.start()
    assert (old / "nes" / "Contra.nes").exists() and not (tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes").exists()
    assert not dialog.changed and dialog.config.home_dir == ""


def test_leaving_the_library_data_behind_keeps_the_old_data_folder(qapp, tmp_path, boxes):
    config = legacy_config(tmp_path)
    dialog, _old = bring_in_dialog(tmp_path, config)
    dialog.data_box.setChecked(False)
    dialog.start()
    assert config.rom_root == "" and config.data_dir == str(tmp_path / "olddata")  # ROMs moved; data stays where it was
    assert not (tmp_path / "Arcadia" / "data" / "library.db").exists()


def test_if_something_could_not_be_moved_the_old_library_is_not_abandoned(qapp, tmp_path, boxes, monkeypatch):
    config = legacy_config(tmp_path)
    dialog, old = bring_in_dialog(tmp_path, config)
    real = consolidate.safe_move

    def flaky(src, dst):
        if src.name == "Sonic.md":
            raise SortError("disk full")
        real(src, dst)

    monkeypatch.setattr(consolidate, "safe_move", flaky)
    dialog.start()
    assert (old / "megadrive" / "Sonic.md").exists()  # the one that failed is still where it was
    assert (tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes").exists()  # the rest went
    assert config.home_dir == "" and config.rom_root == str(old) and not dialog.changed  # so nothing was switched
    message = boxes["info"][-1]
    assert "Sonic.md" in message and "disk full" in message and "hasn't switched" in message


def test_things_that_already_exist_are_reported_but_do_not_block_the_switch(qapp, tmp_path, boxes):
    config = legacy_config(tmp_path)
    put(tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes", b"already here")
    dialog, _old = bring_in_dialog(tmp_path, config)
    dialog.start()
    assert (tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes").read_bytes() == b"already here"
    assert "already existed" in boxes["info"][-1] and config.home_dir == str(tmp_path / "Arcadia")


def test_pointing_at_the_arcadia_rom_folder_itself_is_explained(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    dialog = BringInDialog(config, Journal(config.journal_path))
    dialog.source_edit.setText(str(config.rom_root_path))
    dialog.scan()
    assert "Can't use that ROM folder" in dialog.summary.text() and "already the ROM folder" in dialog.summary.text()
    assert not dialog.start_btn.isEnabled() and dialog.table.rowCount() == 0
    dialog.close()


def test_a_folder_with_no_system_folders_in_it_says_so(qapp, tmp_path):
    (tmp_path / "empty").mkdir()
    config = Config.new_install(tmp_path / "Arcadia")
    dialog = BringInDialog(config, Journal(config.journal_path))
    dialog.source_edit.setText(str(tmp_path / "empty"))
    dialog.scan()
    assert "no subfolders" in dialog.summary.text() and not dialog.start_btn.isEnabled()
    dialog.close()


# ======================= backing up and restoring =======================

def make_saves(tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    path = tmp_path / "Arcadia" / "config.json"
    config.save(path)
    put(config.savestate_path / "abc" / "Game.srm", b"my save")
    put(config.emulators_path / "pcsx2" / "config" / "PCSX2.ini", b"settings")
    return config, path


def test_backing_up_from_the_window(qapp, tmp_path):
    config, path = make_saves(tmp_path)
    dialog = BackupDialog(config, path)
    assert dialog.table.rowCount() == 0
    dialog.back_up()
    assert dialog.table.rowCount() == 1 and cells(dialog.table, 0)[0].startswith("Arcadia-backup-")
    assert "Backed up" in dialog.status.text()
    assert dialog.restore_btn.isEnabled()
    dialog.close()


def test_there_is_a_clear_message_when_there_is_nothing_to_back_up(qapp, tmp_path, boxes):
    config = Config.new_install(tmp_path / "Empty")
    config.ensure_layout()
    dialog = BackupDialog(config, tmp_path / "Empty" / "config.json")
    dialog.back_up()
    assert boxes["warn"] and "nothing to back up" in boxes["warn"][0]
    assert dialog.table.rowCount() == 0
    dialog.close()


def test_restoring_from_the_list(qapp, tmp_path, boxes):
    config, path = make_saves(tmp_path)
    create_backup(config, path)
    (config.savestate_path / "abc" / "Game.srm").write_text("damaged")
    dialog = BackupDialog(config, path)
    dialog.restore_selected()
    assert (config.savestate_path / "abc" / "Game.srm").read_bytes() == b"my save"
    assert dialog.restored is True
    assert "Restart Arcadia" in boxes["info"][-1] and "before-restore" in boxes["info"][-1]
    assert "save states" in boxes["ask"][0]  # it said what the backup holds before doing anything
    dialog.close()


def test_declining_a_restore_changes_nothing(qapp, tmp_path, monkeypatch):
    config, path = make_saves(tmp_path)
    create_backup(config, path)
    (config.savestate_path / "abc" / "Game.srm").write_text("current")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dialog = BackupDialog(config, path)
    dialog.restore_selected()
    assert (config.savestate_path / "abc" / "Game.srm").read_text() == "current" and not dialog.restored
    dialog.close()


def test_restoring_something_that_is_not_a_backup_is_refused(qapp, tmp_path, boxes, monkeypatch):
    config, path = make_saves(tmp_path)
    plain = tmp_path / "notes.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("hello.txt", "hi")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(plain), ""))
    dialog = BackupDialog(config, path)
    dialog.restore_from_file()
    assert boxes["warn"] and "no manifest" in boxes["warn"][0] and not dialog.restored
    dialog.close()


def test_a_failed_restore_reports_that_nothing_changed(qapp, tmp_path, boxes, monkeypatch):
    config, path = make_saves(tmp_path)
    create_backup(config, path)
    (config.savestate_path / "abc" / "Game.srm").write_text("current")

    def boom(*a, **k):
        raise setup_dialog.BackupError("the disk is full")

    monkeypatch.setattr(setup_dialog, "restore_backup", boom)
    dialog = BackupDialog(config, path)
    dialog.restore_selected()
    assert "Nothing was changed: the disk is full" in boxes["warn"][-1] and not dialog.restored
    assert (config.savestate_path / "abc" / "Game.srm").read_text() == "current"
    dialog.close()


# ======================= sweeping the Downloads folder as well =======================

import time  # noqa: E402

import arcadia.sorter as sorter_module  # noqa: E402
from arcadia.import_dialog import ImportDialog  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_downloads(monkeypatch, tmp_path):
    """Never let a test depend on the machine's real Downloads folder."""
    monkeypatch.setattr(setup_dialog, "default_downloads_dir", lambda: tmp_path / "no-such-downloads")


def nes_rom():
    return b"NES\x1a" + bytes(0x4000)


def gb_rom(flag_ext_mismatch=False):
    data = bytearray(0x200)
    data[0x104:0x10C] = bytes.fromhex("CEED6666CC0D000B")
    return bytes(data)


def old_file(path: Path, data=b"x", age=3600.0):
    put(path, data)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def make_downloads(tmp_path):
    dl = tmp_path / "Downloads"
    old_file(dl / "Contra.nes", nes_rom())
    old_file(dl / "Pokemon pack" / "Tetris.gb", gb_rom())
    old_file(dl / "Pokemon pack" / "Mislabelled.gbc", gb_rom())  # a Game Boy header in a .gbc file: asks
    old_file(dl / "holiday.jpg", b"jpg")
    return dl


def sweep_dialog(tmp_path, config, source="", downloads=True):
    dialog = BringInDialog(config, Journal(config.journal_path))
    dialog.home_edit.setText(str(tmp_path / "Arcadia"))
    dialog.source_edit.setText(source)
    dialog.dl_box.setChecked(downloads)
    dialog.dl_edit.setText(str(tmp_path / "Downloads"))
    dialog.scan()
    return dialog


def current_config(tmp_path):
    """A setup that hasn't moved to an Arcadia folder yet: ROMs are in ~/ROMs somewhere."""
    return Config(rom_root=str(tmp_path / "OldROMs"), data_dir=str(tmp_path / "olddata"))


def test_the_downloads_sweep_is_on_by_default_when_the_folder_exists(qapp, tmp_path, monkeypatch):
    (tmp_path / "RealDownloads").mkdir()
    monkeypatch.setattr(setup_dialog, "default_downloads_dir", lambda: tmp_path / "RealDownloads")
    dialog = BringInDialog(current_config(tmp_path), Journal(tmp_path / "j.json"))
    assert dialog.dl_box.isChecked() and dialog.dl_edit.text() == str(tmp_path / "RealDownloads")
    assert not dialog.keep_box.isChecked()  # watching it for good is never on by itself
    dialog.close()


def test_the_sweep_is_off_when_there_is_no_downloads_folder(qapp, tmp_path):
    dialog = BringInDialog(current_config(tmp_path), Journal(tmp_path / "j.json"))
    assert not dialog.dl_box.isChecked()  # the fixture points it at a folder that doesn't exist
    dialog.close()


def test_scanning_looks_at_the_library_and_downloads_together(qapp, tmp_path):
    make_downloads(tmp_path)
    config = current_config(tmp_path)
    old = make_old_library(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source=str(old))
    assert dialog.table.rowCount() == 4  # the library's folders
    assert len(dialog.dl_plan.items) == 3  # Contra, Tetris and the mislabelled one (the photo isn't a ROM)
    assert "3 ROMs found in Downloads; 2 will be sorted in" in dialog.dl_summary.text()
    assert "1 needs your decision" in dialog.dl_summary.text()
    assert sorted(i.source.name for i in dialog.dl_selection) == ["Contra.nes", "Tetris.gb"]  # the uncertain one isn't ticked
    assert dialog.review_btn.isEnabled() and dialog.start_btn.isEnabled()
    dialog.close()


def test_downloads_can_be_swept_without_a_rom_folder(qapp, tmp_path):
    make_downloads(tmp_path)
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source="")
    assert dialog.table.rowCount() == 0 and len(dialog.dl_plan.items) == 3
    assert "current ROM folder" in dialog.dl_summary.text() and str(tmp_path / "OldROMs") in dialog.dl_summary.text()
    assert dialog.start_btn.isEnabled()
    dialog.close()


def test_sweeping_downloads_alone_uses_the_current_rom_folder_and_starts_no_second_library(qapp, tmp_path, boxes):
    dl = make_downloads(tmp_path)
    config = current_config(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source="")
    dialog.start()

    assert (tmp_path / "OldROMs" / "nes" / "Contra.nes").exists() and (tmp_path / "OldROMs" / "gb" / "Tetris.gb").exists()
    assert not (tmp_path / "Arcadia").exists()  # no new folder was made
    assert (dl / "Pokemon pack" / "Mislabelled.gbc").exists() and (dl / "holiday.jpg").exists()  # not a certain ROM, not a ROM
    assert not (dl / "Contra.nes").exists() and not (dl / "Pokemon pack" / "Tetris.gb").exists()
    assert config.home_dir == "" and config.rom_root == str(tmp_path / "OldROMs")  # nothing was switched
    assert dialog.changed and dialog.result() == QDialog.DialogCode.Accepted  # so the window rescans
    assert "2 ROMs from Downloads sorted into your library" in boxes["info"][-1]


def test_downloads_swept_during_a_migration_go_into_the_new_arcadia_folder(qapp, tmp_path, boxes):
    make_downloads(tmp_path)
    config = legacy_config(tmp_path)
    old = tmp_path / "OldROMs"
    put(old / "nes" / "Zelda.nes", nes_rom())
    dialog = sweep_dialog(tmp_path, config, source=str(old))
    dialog.start()

    home = tmp_path / "Arcadia"
    assert (home / "roms" / "nes" / "Zelda.nes").exists()  # from the library
    assert (home / "roms" / "nes" / "Contra.nes").exists() and (home / "roms" / "gb" / "Tetris.gb").exists()  # from Downloads
    assert config.home_dir == str(home) and config.rom_root == ""  # and Arcadia moved over
    assert "from your ROM folder" in boxes["info"][-1] and "from Downloads sorted" in boxes["info"][-1]


def test_the_review_step_lets_the_user_decide_what_is_included(qapp, tmp_path, monkeypatch, boxes):
    dl = make_downloads(tmp_path)
    config = current_config(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source="")
    seen = {}

    def choose(self):
        seen.update(verb=self.verb, base=self.base, button=self.move_btn.text(), labels=[i.source.name for i in self.items])
        for row, item in enumerate(self.items):
            check = self.table.item(row, 0)
            if item.source.name == "Contra.nes":
                check.setCheckState(Qt.CheckState.Unchecked)  # leave this one in Downloads
            if item.source.name == "Mislabelled.gbc":
                check.setCheckState(Qt.CheckState.Checked)  # the user says yes to the uncertain one
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ImportDialog, "exec", choose)
    dialog.review()
    assert seen["verb"] == "Include" and seen["base"] == tmp_path / "Downloads" and seen["button"] == "Include 2 ROMs"
    assert sorted(i.source.name for i in dialog.dl_selection) == ["Mislabelled.gbc", "Tetris.gb"]

    dialog.start()
    assert (dl / "Contra.nes").exists()  # the one they unticked stayed
    assert (tmp_path / "OldROMs" / "gb" / "Mislabelled.gbc").exists()  # the uncertain one went because they said so


def test_cancelling_the_review_keeps_the_default_selection(qapp, tmp_path, monkeypatch):
    make_downloads(tmp_path)
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source="")
    before = list(dialog.dl_selection)
    monkeypatch.setattr(ImportDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    dialog.review()
    assert dialog.dl_selection == before
    dialog.close()


def test_the_review_window_says_which_subfolder_a_rom_was_found_in(qapp, tmp_path):
    make_downloads(tmp_path)
    config = current_config(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source="")
    review = ImportDialog(config, dialog.dl_plan, base=tmp_path / "Downloads", verb="Include")
    labels = {review.table.item(r, 1).text() for r in range(review.table.rowCount())}
    assert "Contra.nes" in labels  # at the top level: just the name
    assert any(label.startswith("Tetris.gb") and "in Pokemon pack/" in label for label in labels)
    review.close()
    dialog.close()


def test_keeping_the_folder_watched_is_a_separate_choice(qapp, tmp_path, boxes):
    make_downloads(tmp_path)
    config = current_config(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source="")
    dialog.keep_box.setChecked(True)
    dialog.start()
    assert config.inbox_dir == str(tmp_path / "Downloads") and "keep watching" in boxes["info"][-1]

    other = current_config(tmp_path)
    other.inbox_dir = "~/Elsewhere"  # an existing choice is never overwritten
    old_file(tmp_path / "Downloads" / "Zelda.nes", nes_rom())  # something new to sweep, so start really runs
    again = sweep_dialog(tmp_path, other, source="")
    assert [i.source.name for i in again.dl_selection] == ["Zelda.nes"]
    again.keep_box.setChecked(True)
    again.start()
    assert (tmp_path / "OldROMs" / "nes" / "Zelda.nes").exists()  # it did run...
    assert other.inbox_dir == "~/Elsewhere"  # ...and left the existing choice alone


def test_without_the_keep_watching_box_the_setting_is_untouched(qapp, tmp_path, boxes):
    make_downloads(tmp_path)
    config = current_config(tmp_path)
    sweep_dialog(tmp_path, config, source="").start()
    assert config.inbox_dir == ""


def test_a_rom_already_in_the_library_is_left_in_downloads(qapp, tmp_path, boxes):
    dl = make_downloads(tmp_path)
    put(tmp_path / "OldROMs" / "nes" / "Contra.nes", b"already here")
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source="")
    assert [i.source.name for i in dialog.dl_selection] == ["Tetris.gb"]  # the collision isn't even ticked
    dialog.start()
    assert (dl / "Contra.nes").exists() and (tmp_path / "OldROMs" / "nes" / "Contra.nes").read_bytes() == b"already here"


def test_a_failure_moving_one_rom_is_reported_and_the_rest_still_move(qapp, tmp_path, boxes, monkeypatch):
    dl = make_downloads(tmp_path)
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source="")
    real = sorter_module.safe_move

    def flaky(src, dst):
        if src.name == "Tetris.gb":
            raise sorter_module.SortError("disk full")
        real(src, dst)

    monkeypatch.setattr(sorter_module, "safe_move", flaky)
    dialog.start()
    assert (tmp_path / "OldROMs" / "nes" / "Contra.nes").exists() and (dl / "Pokemon pack" / "Tetris.gb").exists()
    assert "Left in Downloads: Tetris.gb: disk full" in boxes["info"][-1]


def test_editing_the_arcadia_folder_after_looking_still_puts_everything_in_the_right_place(qapp, tmp_path, boxes):
    make_downloads(tmp_path)
    old = make_old_library(tmp_path)
    config = Config(rom_root=str(old), data_dir=str(tmp_path / "olddata"))
    dialog = sweep_dialog(tmp_path, config, source=str(old))
    dialog.home_edit.setText(str(tmp_path / "Somewhere Else"))  # changed their mind after the scan
    dialog.start()
    assert (tmp_path / "Somewhere Else" / "roms" / "nes" / "Contra.nes").exists()
    assert not (tmp_path / "Arcadia" / "roms" / "nes" / "Contra.nes").exists()


def test_a_library_inside_downloads_is_not_listed_twice(qapp, tmp_path):
    dl = tmp_path / "Downloads"
    old_file(dl / "MyROMs" / "nes" / "Contra.nes", nes_rom())  # the library being migrated happens to live in Downloads
    old_file(dl / "Loose.nes", nes_rom())
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source=str(dl / "MyROMs"))
    assert [i.source.name for i in dialog.dl_plan.items] == ["Loose.nes"]  # the library is handled by the library part
    dialog.close()


def test_nothing_in_downloads_and_no_library_means_nothing_to_do(qapp, tmp_path):
    (tmp_path / "Downloads").mkdir()
    old_file(tmp_path / "Downloads" / "notes.txt", b"hi")
    dialog = sweep_dialog(tmp_path, current_config(tmp_path), source="")
    assert "No ROMs found in Downloads" in dialog.dl_summary.text()
    assert not dialog.start_btn.isEnabled() and not dialog.review_btn.isEnabled()
    dialog.close()


def test_choosing_nothing_to_look_at_explains_itself(qapp, tmp_path):
    dialog = BringInDialog(current_config(tmp_path), Journal(tmp_path / "j.json"))
    dialog.source_edit.setText("")
    dialog.dl_box.setChecked(False)
    dialog.scan()
    assert "Choose your ROM folder" in dialog.summary.text() and not dialog.start_btn.isEnabled()
    dialog.close()


def test_a_sweep_can_be_undone_from_the_file_menu(qapp, tmp_path, boxes):
    dl = make_downloads(tmp_path)
    config = current_config(tmp_path)
    dialog = sweep_dialog(tmp_path, config, source="")
    dialog.start()
    restored, problems = dialog.journal.undo_last()
    assert problems == [] and restored == 2
    assert (dl / "Contra.nes").exists() and (dl / "Pokemon pack" / "Tetris.gb").exists()
    assert not (tmp_path / "OldROMs" / "nes" / "Contra.nes").exists()


def test_the_hub_names_the_button_for_what_it_now_does(qapp, tmp_path):
    hub = make_hub(tmp_path)
    assert hub.bring_btn.text() == "Bring my ROMs in…"
    hub.close()
