"""The Options screen: every item from the menu bar as one big list, for when the menu bar is hidden.

In full screen (and in Game Mode on a Steam Deck) the menu bar is hidden, and a controller can't reach it. This list
holds the same actions, grouped by menu, and works with the D-pad and A: press Menu / Start (or F10, or the
Options button) to open it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QMenuBar, QVBoxLayout, QWidget


def _clean(text: str) -> str:
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").replace("…", "…").strip()


def collect(menubar: QMenuBar, skip: QAction | None = None) -> list[tuple[str, list[QAction]]]:
    """(menu title, actions) for each menu, with submenus flattened in as "Sub ▸ item"."""
    groups: list[tuple[str, list[QAction]]] = []
    for top in menubar.actions():
        menu = top.menu()
        if menu is None:
            continue
        found: list[QAction] = []

        def walk(m, prefix: str = "") -> None:
            for action in m.actions():
                if action.isSeparator() or not action.isVisible():
                    continue
                if action.menu() is not None:
                    walk(action.menu(), prefix + _clean(action.text()) + " ▸ ")
                elif action is not skip:
                    found.append((action, prefix))

        walk(menu)
        if found:
            groups.append((_clean(top.text()), found))
    return groups


class OptionsMenu(QDialog):
    def __init__(self, menubar: QMenuBar, parent: QWidget | None = None, skip: QAction | None = None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumSize(520, 420)
        self.chosen: QAction | None = None
        layout = QVBoxLayout(self)
        hint = QLabel("D-pad to move, A to choose, B to close.")
        hint.setStyleSheet("color: rgba(236, 238, 244, 60%);")
        layout.addWidget(hint)
        self.listing = QListWidget()
        self.listing.setStyleSheet("QListWidget::item { padding: 12px 14px; font-size: 16px; }")
        layout.addWidget(self.listing, 1)
        first = None
        for title, entries in collect(menubar, skip):
            header = QListWidgetItem(title.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(12)
            header.setFont(font)
            self.listing.addItem(header)
            for action, prefix in entries:
                mark = ("✓  " if action.isChecked() else "      ") if action.isCheckable() else ""
                text = mark + prefix + _clean(action.text())
                shortcut = action.shortcut().toString()
                item = QListWidgetItem(text + (f"      ({shortcut})" if shortcut else ""))
                item.setData(Qt.ItemDataRole.UserRole, action)
                if not action.isEnabled():
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.listing.addItem(item)
                if first is None and action.isEnabled():
                    first = item
        self.listing.itemActivated.connect(self._choose)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if first is not None:
            self.listing.setCurrentItem(first)
        self.listing.setFocus()

    def _choose(self, item: QListWidgetItem) -> None:
        action = item.data(Qt.ItemDataRole.UserRole)
        if action is None:
            return
        self.chosen = action
        self.accept()


def show_options(menubar: QMenuBar, parent: QWidget, skip: QAction | None = None) -> None:
    """Open the list; whatever is picked runs after the list has closed, so what it opens is on top."""
    dialog = OptionsMenu(menubar, parent, skip)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen is not None:
        QTimer.singleShot(0, dialog.chosen.trigger)
