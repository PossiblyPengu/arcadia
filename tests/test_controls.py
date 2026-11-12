import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from arcadia import controls
from arcadia.config import Config
from arcadia.retroarch import config_text


def test_starter_controls_are_created_in_the_emulators_own_folder(tmp_path):
    out = controls.apply("duckstation", tmp_path / "ds", tmp_path / "bk")
    assert out.action == "created" and out.path == tmp_path / "ds" / "data" / "duckstation" / "settings.ini"
    text = out.path.read_text()
    assert "[Pad1]" in text and "Cross = SDL-0/A" in text and "LUp = SDL-0/-LeftY" in text and "Type = AnalogController" in text
    pcsx2 = controls.apply("pcsx2", tmp_path / "p", tmp_path / "bk")
    assert pcsx2.path == tmp_path / "p" / "config" / "PCSX2" / "inis" / "PCSX2.ini"
    assert "Type = DualShock2" in pcsx2.path.read_text() and "Triangle = SDL-0/Y" in pcsx2.path.read_text()
    assert controls.status("duckstation", tmp_path / "ds") == "set"
    assert controls.status("duckstation", tmp_path / "nothing") == "none"


def test_existing_settings_are_added_to_never_overwritten(tmp_path):
    path = controls.settings_file("duckstation", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[Main]\nSetupWizardIncomplete = false\n\n[GPU]\nRenderer = Vulkan\n")
    assert controls.status("duckstation", tmp_path) == "none"
    out = controls.apply("duckstation", tmp_path, tmp_path / "bk")
    assert out.action == "added" and out.backup is not None and out.backup.read_text().startswith("[Main]")
    text = path.read_text()
    assert "Renderer = Vulkan" in text and "SetupWizardIncomplete = false" in text and "[Pad1]" in text
    # your own bindings are kept without force
    path.write_text("[Pad1]\nType = AnalogController\nCross = Keyboard/Z\nCircle = SDL-1/B\n\n[GPU]\nRenderer = Vulkan\n")
    kept = controls.apply("duckstation", tmp_path, tmp_path / "bk")
    assert kept.action == "kept" and "Keyboard/Z" in path.read_text()
    # reset replaces only that section, after a backup
    reset = controls.apply("duckstation", tmp_path, tmp_path / "bk", force=True)
    assert reset.action == "replaced" and reset.backup and "Keyboard/Z" in reset.backup.read_text()
    text = path.read_text()
    assert "Keyboard/Z" not in text and "Cross = SDL-0/A" in text and "[GPU]\nRenderer = Vulkan" in text
    assert text.count("[Pad1]") == 1


def test_retroarch_hotkeys_follow_the_setting(tmp_path):
    cfg = Config.new_install(tmp_path)
    assert 'input_exit_emulator_btn = "7"' in config_text(cfg) and 'input_enable_hotkey_btn = "6"' in config_text(cfg)
    cfg.ra_hotkeys = False
    assert "input_exit_emulator_btn" not in config_text(cfg)


def test_launching_an_installed_emulator_seeds_controls_once(tmp_path, monkeypatch):
    from arcadia.library import Library
    from arcadia.ui import MainWindow
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    cfg = Config.new_install(tmp_path / "A")
    cfg.ensure_layout()
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    try:
        class Plan:
            via = "local:duckstation"

        win._starter_controls(Plan())
        ini = controls.settings_file("duckstation", cfg.emulators_path / "duckstation")
        assert ini.is_file()
        ini.write_text("[Pad1]\nCross = SDL-0/B\n")  # the user changed it
        win._starter_controls(Plan())
        assert ini.read_text() == "[Pad1]\nCross = SDL-0/B\n"
        cfg.emulator_controls = False
        ini.unlink()
        win._starter_controls(Plan())
        assert not ini.exists()
        Plan.via = "command"
        cfg.emulator_controls = True
        win._starter_controls(Plan())
        assert not ini.exists()
    finally:
        win.close()


def test_controls_tab_lists_emulators_and_sets_them_up(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from arcadia.emulators import Installer
    from arcadia.tools_dialog import ToolsDialog

    QApplication.instance() or QApplication([])
    cfg = Config.new_install(tmp_path / "A")
    cfg.ensure_layout()
    # pretend DuckStation is installed
    inst = Installer(cfg.emulators_path)
    folder = inst.folder("duckstation")
    (folder / "app").mkdir(parents=True)
    (folder / "app" / "ds").write_text("x")
    (folder / "install.json").write_text('{"id": "duckstation", "version": "v1", "asset": "a", "sha256": "", "verified": false, "exe": "ds", "source": "", "installed_at": ""}')
    dialog = ToolsDialog(cfg, tab=2)
    try:
        rows = {dialog.controls_table.item(r, 0).text(): dialog.controls_table.item(r, 1).text() for r in range(dialog.controls_table.rowCount())}
        assert rows["DuckStation"] == "not set up yet" and rows["PCSX2"] == "—"
        dialog.controls_table.selectRow(next(r for r in range(dialog.controls_table.rowCount()) if dialog.controls_table.item(r, 0).text() == "DuckStation"))
        dialog.setup_btn.click()
        assert controls.settings_file("duckstation", folder).is_file()
        assert dialog.controls_table.item(next(r for r in range(dialog.controls_table.rowCount()) if dialog.controls_table.item(r, 0).text() == "DuckStation"), 1).text().startswith("✓")
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        dialog.reset_btn.click()
        assert list((cfg.backups_path / "controls").glob("duckstation-*.ini"))
        dialog.hotkeys_box.setChecked(False)
        assert cfg.ra_hotkeys is False
    finally:
        dialog.reject()
