import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from arcadia.folder_picker import UP, FolderPicker, subfolders

app = QApplication.instance() or QApplication([])


def test_navigate_and_choose(tmp_path):
    (tmp_path / "roms" / "snes").mkdir(parents=True)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    assert [p.name for p in subfolders(tmp_path)] == ["roms"]
    dialog = FolderPicker("Pick", tmp_path)
    texts = [dialog.listing.item(i).text() for i in range(dialog.listing.count())]
    assert "Up" in texts[0] and any("roms" in t for t in texts)
    assert dialog.listing.currentRow() == 1  # starts on the first real folder, not "up"
    dialog._open_item(dialog.listing.item(1))
    assert dialog.folder == tmp_path / "roms"
    dialog._open_item(dialog.listing.item(0))  # up
    assert dialog.folder == tmp_path
    dialog.go(tmp_path / "roms")
    dialog._accept()
    assert dialog.chosen == str(tmp_path / "roms")


def test_missing_start_falls_back(tmp_path):
    assert FolderPicker("Pick", tmp_path / "nope" / "deeper").folder == tmp_path
