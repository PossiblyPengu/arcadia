"""The BIOS / RetroArch / sync window."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import arcadia.setup_dialog as setup_dialog  # noqa: E402
import arcadia.tools_dialog as tools_dialog  # noqa: E402
from arcadia import retroarch  # noqa: E402
from arcadia.config import Config  # noqa: E402
from arcadia.tools_dialog import ToolsDialog  # noqa: E402
from qtutil import SyncTask  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(setup_dialog, "TaskClass", SyncTask)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    return ToolsDialog(config)


def cells(table, col):
    return [table.item(r, col).text() for r in range(table.rowCount())]


def test_bios_tab_lists_what_is_missing_and_found(dialog):
    assert any("missing" in s for s in cells(dialog.bios_table, 2))
    assert "still need" in dialog.bios_summary.text()
    (dialog.config.bios_path / "lynxboot.img").write_bytes(b"x")
    dialog.refresh_bios()
    rows = list(zip(cells(dialog.bios_table, 1), cells(dialog.bios_table, 2)))
    assert ("Lynx boot ROM", "✓  found (lynxboot.img)") in rows


def test_settings_are_written_to_the_config_on_close(dialog):
    dialog.integer_box.setChecked(True)
    dialog.saves_box.setChecked(True)
    dialog.fullscreen_box.setChecked(False)
    dialog.sync_edit.setText("  /somewhere  ")
    dialog.accept()
    c = dialog.config
    assert c.ra_integer_scale and c.ra_saves_in_home and not c.ra_fullscreen and c.sync_dir == "/somewhere"


def test_cores_button_installs_and_refreshes(dialog, monkeypatch, tmp_path):
    cores = tmp_path / "cores"
    for s in dialog.config.systems:
        s.command = s.command.replace("~/.var/app/org.libretro.RetroArch/config/retroarch/cores", str(cores))
    dialog.refresh_cores()
    assert dialog.cores_btn.isEnabled() and all("not installed" in s for s in cells(dialog.cores_table, 2))

    def fake(rows, fetcher=None, progress=None):
        for r in rows:
            r.path.parent.mkdir(parents=True, exist_ok=True)
            r.path.write_bytes(b"core")
        return [retroarch.CoreOutcome(r.name, True) for r in rows]

    monkeypatch.setattr(retroarch, "update_cores", fake)
    dialog.update_cores()
    assert all("✓" in s for s in cells(dialog.cores_table, 2))


def test_sync_buttons_preview_then_copy(dialog, tmp_path):
    (dialog.config.saves_path / "a.srm").write_bytes(b"x")
    dialog.sync_edit.setText(str(tmp_path / "cloud"))
    dialog.run_sync(dry_run=True)
    assert "Would copy 1" in dialog.sync_result.text() and not (tmp_path / "cloud").exists()
    dialog.run_sync(dry_run=False)
    assert "Copied 1" in dialog.sync_result.text()
    assert (tmp_path / "cloud" / "Arcadia" / "saves" / "a.srm").is_file()


def test_sync_errors_are_shown(dialog):
    dialog.sync_edit.setText("")
    dialog.run_sync(dry_run=False)
    assert "Choose a sync folder" in dialog.sync_result.text()


def test_grant_asks_first_and_only_then_runs(dialog, monkeypatch):
    ran = []
    monkeypatch.setattr(tools_dialog, "installed_flatpaks", lambda: {"org.libretro.RetroArch", "org.DolphinEmu.dolphin-emu"})
    monkeypatch.setattr(retroarch, "grant_access", lambda apps, paths: ran.append((apps, paths)) or retroarch.GrantResult(True, 1))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dialog.grant_access()
    assert ran == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dialog.grant_access()
    assert ran and "org.libretro.RetroArch" in ran[0][0] and ran[0][1] == [dialog.config.home_path]


def test_grant_without_flatpak_does_nothing(dialog, monkeypatch):
    monkeypatch.setattr(tools_dialog, "installed_flatpaks", lambda: None)
    monkeypatch.setattr(retroarch, "grant_access", lambda *a: pytest.fail("must not run"))
    dialog.grant_access()
