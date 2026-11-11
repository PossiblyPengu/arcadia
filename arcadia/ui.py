"""Qt user interface: system list, game grid, details panel, and settings."""

from __future__ import annotations

import time
import zlib
from pathlib import Path

from PySide6.QtCore import QEvent, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from arcadia.config import Config, SystemConfig
from arcadia.gamepad import ControllerReader
from arcadia.library import Library
from arcadia.launcher import LaunchError, build_command
from arcadia.metadata import load_metadata
from arcadia.savestates import SaveStateError, create_snapshot, list_snapshots, restore_snapshot
from arcadia.scanner import scan_system
from arcadia.util import fmt_duration, fmt_timestamp

GRID_ICON = QSize(140, 200)
DETAIL_COVER = QSize(220, 300)

ACTION_KEYS = {
    "up": Qt.Key.Key_Up,
    "down": Qt.Key.Key_Down,
    "left": Qt.Key.Key_Left,
    "right": Qt.Key.Key_Right,
    "confirm": Qt.Key.Key_Return,
    "back": Qt.Key.Key_Escape,
}


def placeholder_pixmap(title: str, size: QSize) -> QPixmap:
    """Colored tile with the title, used when a game has no cover art."""
    hue = zlib.crc32(title.encode("utf-8")) % 360
    pix = QPixmap(size)
    pix.fill(QColor.fromHsv(hue, 140, 110))
    painter = QPainter(pix)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        pix.rect().adjusted(8, 8, -8, -8),
        int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
        title,
    )
    painter.end()
    return pix


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(1000, 520)

        self.rom_root = QLineEdit(config.rom_root)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        rom_row = QHBoxLayout()
        rom_row.addWidget(self.rom_root)
        rom_row.addWidget(browse)

        self.media_dir = QLineEdit(config.media_dir)
        self.media_dir.setPlaceholderText(str(config.media_path))
        self.savestate_dir = QLineEdit(config.savestate_dir)
        self.savestate_dir.setPlaceholderText(str(config.savestate_path))

        form = QFormLayout()
        form.addRow("ROM root folder:", rom_row)
        form.addRow("Media folder (covers, metadata):", self.media_dir)
        form.addRow("Save-state folder:", self.savestate_dir)

        headers = ["ID", "Name", "ROM folder", "Extensions (comma separated)", "Launch command", "Emulator save folder"]
        self.table = QTableWidget(len(config.systems), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, s in enumerate(config.systems):
            values = [s.id, s.name, s.folder, ", ".join(s.extensions), s.command, s.save_dir]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)

        hint = QLabel(
            "Launch command: use {rom} where the ROM path goes, e.g. "
            "'retroarch -L /path/core.so {rom}'. Leave empty to disable launching for that system."
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "ROM root folder", self.rom_root.text())
        if folder:
            self.rom_root.setText(folder)

    def apply(self, config: Config) -> None:
        config.rom_root = self.rom_root.text().strip() or config.rom_root
        config.media_dir = self.media_dir.text().strip()
        config.savestate_dir = self.savestate_dir.text().strip()
        systems: list[SystemConfig] = []
        for row in range(self.table.rowCount()):
            cell = lambda c: (self.table.item(row, c).text().strip() if self.table.item(row, c) else "")
            exts = []
            for e in cell(3).split(","):
                e = e.strip().lower()
                if e:
                    exts.append(e if e.startswith(".") else f".{e}")
            systems.append(
                SystemConfig(
                    id=cell(0),
                    name=cell(1),
                    folder=cell(2),
                    extensions=exts,
                    command=cell(4),
                    save_dir=cell(5),
                )
            )
        config.systems = systems


class MainWindow(QMainWindow):
    def __init__(self, config: Config, config_path: Path, library: Library):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.library = library
        self.process: QProcess | None = None
        self.running_key: str | None = None
        self.session_start = 0.0
        self._pixmap_cache: dict[str, QPixmap] = {}

        self.setWindowTitle("Arcadia")
        self.resize(1280, 800)

        # Left: systems
        self.systems_list = QListWidget()
        self.systems_list.setMaximumWidth(260)
        self.systems_list.currentRowChanged.connect(lambda _row: self.populate_games())
        self.systems_list.itemActivated.connect(lambda _item: self.games_list.setFocus())

        # Center: search + grid
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games (Ctrl+F)")
        self.search.textChanged.connect(lambda _t: self.populate_games())
        self.fav_only = QCheckBox("Favorites only")
        self.fav_only.toggled.connect(lambda _c: self.populate_games())

        self.games_list = QListWidget()
        self.games_list.setViewMode(QListView.ViewMode.IconMode)
        self.games_list.setIconSize(GRID_ICON)
        self.games_list.setGridSize(QSize(GRID_ICON.width() + 24, GRID_ICON.height() + 48))
        self.games_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.games_list.setMovement(QListView.Movement.Static)
        self.games_list.setWordWrap(True)
        self.games_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.games_list.currentItemChanged.connect(self._on_game_changed)
        self.games_list.itemActivated.connect(lambda _item: self.launch())

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(self.search)
        center_layout.addWidget(self.fav_only)
        center_layout.addWidget(self.games_list)

        # Right: details
        self.cover = QLabel()
        self.cover.setFixedSize(DETAIL_COVER)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl = QLabel()
        self.title_lbl.setWordWrap(True)
        font = self.title_lbl.font()
        font.setPointSize(font.pointSize() + 5)
        font.setBold(True)
        self.title_lbl.setFont(font)
        self.info_lbl = QLabel()
        self.info_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.info_lbl.setWordWrap(True)
        self.desc_lbl = QLabel()
        self.desc_lbl.setWordWrap(True)

        self.launch_btn = QPushButton("Launch")
        self.launch_btn.clicked.connect(self.launch)
        self.stop_btn = QPushButton("Stop game")
        self.stop_btn.clicked.connect(self.stop)
        self.fav_btn = QPushButton("Toggle favorite")
        self.fav_btn.clicked.connect(self.toggle_favorite)

        self.snap_combo = QComboBox()
        self.save_btn = QPushButton("Save state")
        self.save_btn.clicked.connect(self.save_state)
        self.restore_btn = QPushButton("Restore selected state")
        self.restore_btn.clicked.connect(self.restore_state)

        launch_row = QHBoxLayout()
        launch_row.addWidget(self.launch_btn)
        launch_row.addWidget(self.stop_btn)
        launch_row.addWidget(self.fav_btn)

        state_row = QHBoxLayout()
        state_row.addWidget(self.save_btn)
        state_row.addWidget(self.restore_btn)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignHCenter)
        right_layout.addWidget(self.title_lbl)
        right_layout.addWidget(self.info_lbl)
        right_layout.addWidget(self.desc_lbl)
        right_layout.addStretch(1)
        right_layout.addLayout(launch_row)
        right_layout.addWidget(QLabel("Save states:"))
        right_layout.addWidget(self.snap_combo)
        right_layout.addLayout(state_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.systems_list)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_menu()
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.toggle_favorite)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.rescan)

        self.controller = ControllerReader(self)
        self.controller.action.connect(self.handle_action)
        self.controller.start()

        self.rescan(initial=True)
        self._update_running_state()

    # ----- setup -----

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Rescan library", self.rescan, "Ctrl+R")
        file_menu.addAction("Settings…", self.open_settings)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, "Ctrl+Q")

    # ----- library -----

    def rescan(self, initial: bool = False) -> None:
        total = 0
        for system in self.config.systems:
            games = scan_system(self.config.rom_root_path, system)
            self.library.sync(system.id, games)
            total += len(games)
        self.refresh_systems()
        self.populate_games()
        if not self.config.rom_root_path.is_dir():
            self.statusBar().showMessage(f"ROM folder not found: {self.config.rom_root_path}. Set it in Settings.")
        else:
            self.statusBar().showMessage(f"Found {total} games in {self.config.rom_root_path}")
        if initial and self.systems_list.count():
            self.systems_list.setCurrentRow(0)

    def refresh_systems(self) -> None:
        current = self.current_system_id()
        self.systems_list.blockSignals(True)
        self.systems_list.clear()
        for system in self.config.systems:
            item = QListWidgetItem(f"{system.name}  ({self.library.count(system.id)})")
            item.setData(Qt.ItemDataRole.UserRole, system.id)
            self.systems_list.addItem(item)
            if system.id == current:
                self.systems_list.setCurrentItem(item)
        self.systems_list.blockSignals(False)

    def current_system_id(self) -> str | None:
        item = self.systems_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def current_game_key(self) -> str | None:
        item = self.games_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _cover_pixmap(self, system_id: str, title: str, rom: Path, size: QSize) -> QPixmap:
        meta = load_metadata(self.config.media_path, system_id, rom)
        if meta.cover:
            return QPixmap(str(meta.cover)).scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        return placeholder_pixmap(meta.title or title, size)

    def populate_games(self) -> None:
        system_id = self.current_system_id()
        self.games_list.blockSignals(True)
        self.games_list.clear()
        if system_id is not None:
            rows = self.library.games(
                system_id, search=self.search.text().strip(), favorites_only=self.fav_only.isChecked()
            )
            for row in rows:
                key = row["key"]
                if key not in self._pixmap_cache:
                    self._pixmap_cache[key] = self._cover_pixmap(
                        system_id, row["title"], Path(row["path"]), GRID_ICON
                    )
                item = QListWidgetItem(("★ " if row["favorite"] else "") + row["title"])
                item.setIcon(QIcon(self._pixmap_cache[key]))
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setToolTip(row["path"])
                self.games_list.addItem(item)
        self.games_list.blockSignals(False)
        if self.games_list.count():
            self.games_list.setCurrentRow(0)
        self._on_game_changed(self.games_list.currentItem())

    def _select_game(self, key: str) -> None:
        for i in range(self.games_list.count()):
            if self.games_list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.games_list.setCurrentRow(i)
                return

    def _on_game_changed(self, current, _previous=None) -> None:
        if current is None:
            self.cover.clear()
            self.title_lbl.setText("")
            self.info_lbl.setText("No game selected.")
            self.desc_lbl.setText("")
            self.snap_combo.clear()
        else:
            self.show_details(current.data(Qt.ItemDataRole.UserRole))
        self._update_running_state()

    def show_details(self, key: str) -> None:
        row = self.library.get(key)
        if row is None:
            return
        system = self._system_name(row["system_id"])
        rom = Path(row["path"])
        meta = load_metadata(self.config.media_path, row["system_id"], rom)
        self.cover.setPixmap(self._cover_pixmap(row["system_id"], row["title"], rom, DETAIL_COVER))
        self.title_lbl.setText(("★ " if row["favorite"] else "") + (meta.title or row["title"]))
        extra = []
        if meta.year:
            extra.append(f"<b>Year:</b> {meta.year}")
        if meta.genre:
            extra.append(f"<b>Genre:</b> {meta.genre}")
        info = [
            f"<b>System:</b> {system}",
            f"<b>File:</b> {rom.name}",
            f"<b>Played:</b> {row['play_count']} time(s), {fmt_duration(row['total_seconds'])}",
            f"<b>Last played:</b> {fmt_timestamp(row['last_played'])}",
        ] + extra
        self.info_lbl.setText("<br>".join(info))
        self.desc_lbl.setText(meta.description)
        self._refresh_snapshots(row)

    def _refresh_snapshots(self, row) -> None:
        self.snap_combo.clear()
        for snap in list_snapshots(self.config.savestate_path, Path(row["path"])):
            self.snap_combo.addItem(snap.name, str(snap))

    def _system_name(self, system_id: str) -> str:
        try:
            return self.config.system(system_id).name
        except KeyError:
            return system_id

    # ----- launching -----

    def launch(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        if self.process is not None:
            QMessageBox.information(self, "Already running", "A game is already running. Stop it first.")
            return
        row = self.library.get(key)
        system = self.config.system(row["system_id"])
        try:
            args = build_command(system.command, Path(row["path"]))
        except LaunchError as exc:
            QMessageBox.warning(self, "Cannot launch", str(exc))
            return

        proc = QProcess(self)
        proc.setProgram(args[0])
        proc.setArguments(args[1:])
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_process_error)
        self.process = proc
        self.running_key = key
        self.session_start = time.time()
        proc.start()
        self.statusBar().showMessage(f"Launching {row['title']}…")
        self._update_running_state()

    def _on_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            QMessageBox.warning(
                self, "Cannot launch", f"Could not start: {' '.join([self.process.program()] + self.process.arguments())}"
            )
            self._end_session(record=False)

    def _on_finished(self, _exit_code, _exit_status) -> None:
        if self.process is None:
            return
        self._end_session(record=True)

    def _end_session(self, record: bool) -> None:
        key = self.running_key
        seconds = int(time.time() - self.session_start)
        if record and key:
            self.library.record_session(key, self.session_start, seconds)
        if self.process is not None:
            self.process.deleteLater()
        self.process = None
        self.running_key = None
        self.statusBar().showMessage(f"Session ended after {fmt_duration(seconds)}" if record else "")
        self.refresh_systems()
        self.populate_games()
        if key:
            self._select_game(key)
        self._update_running_state()

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        QTimer.singleShot(3000, self._force_kill)

    def _force_kill(self) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _update_running_state(self) -> None:
        running = self.process is not None
        has_game = self.games_list.currentItem() is not None
        self.launch_btn.setEnabled(has_game and not running)
        self.stop_btn.setEnabled(running)
        self.restore_btn.setEnabled(has_game and not running)
        self.save_btn.setEnabled(has_game)
        self.fav_btn.setEnabled(has_game)

    # ----- favorites & save states -----

    def toggle_favorite(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        row = self.library.get(key)
        self.library.set_favorite(key, not bool(row["favorite"]))
        self.populate_games()
        self._select_game(key)

    def _save_dir_for(self, row) -> Path | None:
        system = self.config.system(row["system_id"])
        if not system.save_dir:
            QMessageBox.warning(
                self, "No save folder", "Set this system's emulator save folder in Settings first."
            )
            return None
        return Path(system.save_dir).expanduser()

    def save_state(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        row = self.library.get(key)
        save_dir = self._save_dir_for(row)
        if save_dir is None:
            return
        try:
            dest = create_snapshot(save_dir, Path(row["path"]), self.config.savestate_path)
        except SaveStateError as exc:
            QMessageBox.warning(self, "Save state failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved snapshot {dest.name}")
        self._refresh_snapshots(row)

    def restore_state(self) -> None:
        key = self.current_game_key()
        if key is None or self.process is not None:
            return
        snap = self.snap_combo.currentData()
        if not snap:
            QMessageBox.information(self, "No snapshot", "There are no save states for this game yet.")
            return
        row = self.library.get(key)
        save_dir = self._save_dir_for(row)
        if save_dir is None:
            return
        answer = QMessageBox.question(
            self,
            "Restore save state",
            "Restore this snapshot? Current saves are backed up first.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_snapshot(Path(snap), save_dir, Path(row["path"]), self.config.savestate_path)
        except SaveStateError as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))
            return
        self.statusBar().showMessage("Save state restored")
        self._refresh_snapshots(row)

    # ----- controller & keyboard -----

    def handle_action(self, name: str) -> None:
        if name == "favorite":
            self.toggle_favorite()
            return
        if name in ("prev_system", "next_system"):
            step = -1 if name == "prev_system" else 1
            row = max(0, min(self.systems_list.count() - 1, self.systems_list.currentRow() + step))
            self.systems_list.setCurrentRow(row)
            return
        key = ACTION_KEYS.get(name)
        if key is None:
            return
        focus = QApplication.focusWidget()
        if focus is not self.systems_list and focus is not self.games_list:
            self.games_list.setFocus()
            focus = self.games_list
        if name == "back" and focus is self.games_list:
            self.systems_list.setFocus()
            return
        QApplication.sendEvent(focus, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    # ----- settings & shutdown -----

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply(self.config)
            self.config.save(self.config_path)
            self._pixmap_cache.clear()
            self.rescan()

    def closeEvent(self, event) -> None:
        self.controller.stop()
        if self.process is not None:
            self.process.terminate()
            self.process.waitForFinished(3000)
            self._end_session(record=True)
        self.library.close()
        super().closeEvent(event)
