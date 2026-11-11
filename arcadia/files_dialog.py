"""Shows every file that makes up a game: the game itself, its discs, updates, and DLC."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from arcadia.util import fmt_size


class FilesDialog(QDialog):
    def __init__(self, title: str, rows: list[tuple[str, Path]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Files: {title}")
        self.resize(820, 340)
        self.rows = rows

        intro = QLabel(f"{len(rows)} file{'s' if len(rows) != 1 else ''} make up {title}.")
        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(["Part", "File", "Size"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for i, (role, path) in enumerate(rows):
            try:
                size = fmt_size(path.stat().st_size)
            except OSError:
                size = "missing"
            name = QTableWidgetItem(path.name)
            name.setToolTip(str(path))
            self.table.setItem(i, 0, QTableWidgetItem(role))
            self.table.setItem(i, 1, name)
            self.table.setItem(i, 2, QTableWidgetItem(size))

        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self.open_folder)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.addButton(self.open_btn, QDialogButtonBox.ButtonRole.ActionRole)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    def open_folder(self) -> None:
        if self.rows:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.rows[0][1].parent)))
