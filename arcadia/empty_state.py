"""What the shelf shows when there's nothing on it: a clear message and what to do about it."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from arcadia.util import fit_label_height


class EmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel("")
        self.title.setObjectName("gameTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel("")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setWordWrap(True)
        self.body.setFixedWidth(620)
        self.body.setStyleSheet("color: rgba(236, 238, 244, 70%); font-size: 15px;")
        self.row = QHBoxLayout()
        self.row.setSpacing(12)
        self.row.addStretch(1)
        self.row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.title)
        layout.addWidget(self.body, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addLayout(self.row)
        layout.addStretch(2)
        self.buttons: list[QPushButton] = []

    def show_message(self, title: str, body: str, actions: list[tuple[str, Callable[[], None], bool]]) -> None:
        """actions are (label, what to do, is it the main one)."""
        self.title.setText(title)
        self.body.setText(body)
        fit_label_height(self.body)
        for button in self.buttons:
            self.row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        for label, callback, primary in actions:
            button = QPushButton(label)
            if primary:
                button.setObjectName("primary")
            button.clicked.connect(lambda _c=False, cb=callback: cb())
            self.row.insertWidget(self.row.count() - 1, button)
            self.buttons.append(button)
