"""A folder chooser that works with a controller: a short list of places, the folders in the current one,
and A on a folder opens it. (The system's own file dialog needs a mouse.)"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

UP = ".."


def places() -> list[tuple[str, Path]]:
    """Handy starting points: home, Downloads, and any memory card or USB drive that is plugged in."""
    home = Path.home()
    found = [("Home", home), ("Downloads", home / "Downloads"), ("Desktop", home / "Desktop")]
    user = os.environ.get("USER") or home.name
    for base in (Path("/run/media") / user, Path("/media") / user, Path("/run/media"), Path("/mnt")):
        try:
            for drive in sorted(base.iterdir()):
                if drive.is_dir():
                    found.append((f"Drive: {drive.name}", drive))
        except OSError:
            pass
    found.append(("Whole computer (/)", Path("/")))
    return [(n, p) for n, p in found if p.is_dir()]


def subfolders(folder: Path, show_hidden: bool = False) -> list[Path]:
    try:
        entries = [p for p in folder.iterdir() if p.is_dir() and (show_hidden or not p.name.startswith("."))]
    except OSError:
        return []
    return sorted(entries, key=lambda p: p.name.lower())


class FolderPicker(QDialog):
    def __init__(self, title: str, start: str | Path | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 420)
        self.chosen: str = ""
        begin = Path(start).expanduser() if start else Path.home()
        while not begin.is_dir() and begin != begin.parent:
            begin = begin.parent
        self.folder = begin

        layout = QVBoxLayout(self)
        self.where = QLabel()
        self.where.setWordWrap(True)
        layout.addWidget(self.where)
        self.places = QComboBox()
        for name, path in places():
            self.places.addItem(name, str(path))
        self.places.setCurrentIndex(-1)
        self.places.setPlaceholderText("Jump to…")
        self.places.activated.connect(lambda _i: self.go(Path(self.places.currentData())))
        layout.addWidget(self.places)
        self.listing = QListWidget()
        self.listing.itemActivated.connect(self._open_item)
        layout.addWidget(self.listing, 1)
        hint = QLabel("A / Enter opens a folder. Pick “Use this folder” when you’re in the right one.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.buttons = QDialogButtonBox()
        self.use = self.buttons.addButton("Use this folder", QDialogButtonBox.ButtonRole.AcceptRole)
        self.use.setObjectName("primary")
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.go(self.folder)

    def go(self, folder: Path) -> None:
        self.folder = folder
        self.where.setText(f"<b>{folder}</b>")
        self.listing.clear()
        if folder != folder.parent:
            up = QListWidgetItem("⬆  Up one folder")
            up.setData(Qt.ItemDataRole.UserRole, UP)
            self.listing.addItem(up)
        for sub in subfolders(folder):
            item = QListWidgetItem("📁  " + sub.name)
            item.setData(Qt.ItemDataRole.UserRole, str(sub))
            self.listing.addItem(item)
        self.listing.setCurrentRow(1 if self.listing.count() > 1 else 0)

    def _open_item(self, item: QListWidgetItem) -> None:
        target = item.data(Qt.ItemDataRole.UserRole)
        self.go(self.folder.parent if target == UP else Path(target))

    def _accept(self) -> None:
        self.chosen = str(self.folder)
        self.accept()


def choose_folder(parent: QWidget | None, title: str, start: str | Path | None = None) -> str:
    """The chosen folder's path, or "" if cancelled."""
    dialog = FolderPicker(title, start, parent)
    return dialog.chosen if dialog.exec() == QDialog.DialogCode.Accepted else ""
