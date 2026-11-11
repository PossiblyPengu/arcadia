"""Qt user interface.

Layout, top to bottom: wordmark with search and sort, a bar of system pills, the
current system's banner, the cover-flow shelf, then the selected game's info and
actions, and a line of key hints. Messages appear as toasts.
"""

from __future__ import annotations

import random
import time
import zlib
from pathlib import Path

from PySide6.QtCore import QEvent, QFileSystemWatcher, QProcess, QProcessEnvironment, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeyEvent, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcadia.config import Config, SystemConfig
from arcadia.coverflow import COVER_H, COVER_W, CoverFlow
from arcadia.bundles import parse_switch
from arcadia.emulators import Installer
from arcadia.emulators_dialog import EmulatorsDialog
from arcadia.files_dialog import FilesDialog
from arcadia.gamepad import ControllerReader
from arcadia.import_dialog import ImportDialog
from arcadia.launcher import LaunchError, resolve_launch
from arcadia.library import Library
from arcadia.metadata import load_metadata
from arcadia.presets import PRESETS, accent_for
from arcadia.savestates import SaveStateError, create_snapshot, list_snapshots, restore_snapshot
from arcadia.scanner import scan_system
from arcadia.setup_dialog import SetupDialog
from arcadia.tools_dialog import ToolsDialog
from arcadia.sorter import Confidence, Journal, Plan, apply_plan, build_plan
from arcadia.tasks import DaemonTask
from arcadia.theme import DEFAULT_ACCENT, Backdrop, Toast, build_stylesheet
from arcadia.updates import CHOOSE, READY, plan_updates
from arcadia.util import bundle_summary, fmt_clock, fmt_duration, fmt_timestamp, snapshot_label

COVER_SIZE = QSize(COVER_W, COVER_H)

VIEW_RECENT = "__recent__"
VIEW_FAVORITES = "__favorites__"
VIEW_ACCENTS = {VIEW_RECENT: "#f2a33a", VIEW_FAVORITES: "#ff5a7a"}
VIEW_NAMES = {VIEW_RECENT: "Recently played", VIEW_FAVORITES: "Favorites"}

SORT_CHOICES = [
    ("A – Z", "title"),
    ("Recently played", "recent"),
    ("Most played", "played"),
    ("Favorites first", "favorites"),
]

ACTION_KEYS = {
    "up": Qt.Key.Key_Up,
    "down": Qt.Key.Key_Down,
    "left": Qt.Key.Key_Left,
    "right": Qt.Key.Key_Right,
    "confirm": Qt.Key.Key_Return,
    "back": Qt.Key.Key_Escape,
}

HINTS = "←  →  browse     A–Z  jump to letter     Enter  launch     ↑  systems     Ctrl+D  favorite     Ctrl+F  search     F11  fullscreen"


def _shorten(text: str, limit: int) -> str:
    """Trim to limit characters at a word boundary, adding an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:- ")
    return cut + "…"


def view_accent(view_id: str) -> str:
    return VIEW_ACCENTS.get(view_id) or accent_for(view_id)


def placeholder_pixmap(title: str, size: QSize, base: str | None = None) -> QPixmap:
    """Colored tile with the title, used when a game has no cover art."""
    color = QColor(base) if base else QColor.fromHsv(zlib.crc32(title.encode("utf-8")) % 360, 140, 110)
    color = color.darker(125)
    pix = QPixmap(size)
    pix.fill(color)
    painter = QPainter(pix)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 5)
    painter.setFont(font)
    painter.drawText(
        pix.rect().adjusted(16, 16, -16, -16),
        int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
        title,
    )
    painter.end()
    return pix


def _dot(color: str) -> QPixmap:
    pix = QPixmap(14, 14)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, 12, 12)
    painter.end()
    return pix


def dot_icon(color: str) -> QIcon:
    """Colored dot for a system pill; turns white when the pill is selected (the pill takes the color)."""
    icon = QIcon(_dot(color))
    icon.addPixmap(_dot("#ffffff"), QIcon.Mode.Selected)
    return icon


class PillList(QListWidget):
    """The system bar. The mouse wheel scrolls it sideways (there are a lot of systems now)."""

    def wheelEvent(self, event) -> None:
        bar = self.horizontalScrollBar()
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar.setValue(bar.value() - delta)
        event.accept()


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(1080, 560)

        self.home_dir = QLineEdit(config.home_dir)
        self.home_dir.setPlaceholderText("Not set: folders are kept wherever each one is set below")
        home_browse = QPushButton("Browse…")
        home_browse.clicked.connect(self._browse_home)
        home_row = QHBoxLayout()
        home_row.addWidget(self.home_dir)
        home_row.addWidget(home_browse)

        self.rom_root = QLineEdit(config.rom_root)
        self.rom_root.setPlaceholderText(f"{config.rom_root_path}  (inside the Arcadia folder)" if config.home_path else str(config.rom_root_path))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        rom_row = QHBoxLayout()
        rom_row.addWidget(self.rom_root)
        rom_row.addWidget(browse)

        self.media_dir = QLineEdit(config.media_dir)
        self.media_dir.setPlaceholderText(str(config.media_path))
        self.savestate_dir = QLineEdit(config.savestate_dir)
        self.savestate_dir.setPlaceholderText(str(config.savestate_path))

        self.inbox_dir = QLineEdit(config.inbox_dir)
        self.inbox_dir.setPlaceholderText("e.g. ~/Downloads  (leave empty to turn ROM sorting off)")
        inbox_browse = QPushButton("Browse…")
        inbox_browse.clicked.connect(self._browse_inbox)
        inbox_row = QHBoxLayout()
        inbox_row.addWidget(self.inbox_dir)
        inbox_row.addWidget(inbox_browse)
        self.auto_import = QCheckBox("Move ROMs automatically when their file header confirms the system (otherwise always ask)")
        self.auto_import.setChecked(config.auto_import)
        self.check_updates = QCheckBox("Check for emulator updates when Arcadia starts (contacts GitHub, and Eden's own server)")
        self.check_updates.setChecked(config.check_updates)

        form = QFormLayout()
        form.addRow("Arcadia folder (everything in one place):", home_row)
        form.addRow("ROM root folder:", rom_row)
        form.addRow("Downloads folder (ROM inbox):", inbox_row)
        form.addRow("", self.auto_import)
        form.addRow("", self.check_updates)
        form.addRow("Media folder (covers, metadata):", self.media_dir)
        form.addRow("Save-state folder:", self.savestate_dir)

        headers = ["ID", "Name", "ROM folder", "Extensions (comma separated)", "Launch command", "Emulator save folder", "Installed emulator"]
        self.table = QTableWidget(len(config.systems), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, s in enumerate(config.systems):
            self._fill_row(row, s.id, s.name, s.folder, ", ".join(s.extensions), s.command, s.save_dir, s.emulator)

        reset = QPushButton("Reset launch commands to presets")
        reset.setToolTip("Fills launch command and save folder for every system from Arcadia's presets.")
        reset.clicked.connect(self._reset_presets)

        hint = QLabel(
            "Launch command: use {rom} where the ROM path goes, e.g. "
            "'flatpak run io.mgba.mGBA {rom}'. Leave empty to disable launching for that system. "
            "Flatpak apps need access to your ROM folder: "
            "flatpak override --user --filesystem=/path/to/ROMs <app-id>"
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.table)
        layout.addWidget(reset)
        layout.addWidget(buttons)

    def _fill_row(
        self, row: int, sid: str, name: str, folder: str, exts: str, command: str, save_dir: str, emulator: str = ""
    ) -> None:
        for col, value in enumerate([sid, name, folder, exts, command, save_dir, emulator]):
            item = QTableWidgetItem(value)
            if col == 0:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

    def _reset_presets(self) -> None:
        for row in range(self.table.rowCount()):
            preset = PRESETS.get(self.table.item(row, 0).text())
            if preset:
                self.table.item(row, 4).setText(preset.command)
                self.table.item(row, 5).setText(preset.save_dir)
                self.table.item(row, 6).setText(preset.emulator)

    def _browse_home(self) -> None:
        start = self.home_dir.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Arcadia folder", start)
        if folder:
            self.home_dir.setText(folder)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "ROM root folder", self.rom_root.text())
        if folder:
            self.rom_root.setText(folder)

    def _browse_inbox(self) -> None:
        start = self.inbox_dir.text().strip() or str(Path.home() / "Downloads")
        folder = QFileDialog.getExistingDirectory(self, "Downloads folder (ROM inbox)", start)
        if folder:
            self.inbox_dir.setText(folder)

    def apply(self, config: Config) -> None:
        config.home_dir = self.home_dir.text().strip()
        config.rom_root = self.rom_root.text().strip() if config.home_dir else (self.rom_root.text().strip() or config.rom_root)
        config.inbox_dir = self.inbox_dir.text().strip()
        config.auto_import = self.auto_import.isChecked()
        config.check_updates = self.check_updates.isChecked()
        config.media_dir = self.media_dir.text().strip()
        config.savestate_dir = self.savestate_dir.text().strip()

        def cell(row: int, col: int) -> str:
            item = self.table.item(row, col)
            return item.text().strip() if item else ""

        systems: list[SystemConfig] = []
        for row in range(self.table.rowCount()):
            exts = []
            for e in cell(row, 3).split(","):
                e = e.strip().lower()
                if e:
                    exts.append(e if e.startswith(".") else f".{e}")
            systems.append(
                SystemConfig(
                    id=cell(row, 0),
                    name=cell(row, 1),
                    folder=cell(row, 2),
                    extensions=exts,
                    command=cell(row, 4),
                    save_dir=cell(row, 5),
                    emulator=cell(row, 6),
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
        self._accent_hex = ""
        self._last_view: str | None = None
        self._closed = False
        self._importing = False  # an import dialog is open
        self._asked: set[str] = set()  # inbox files the user has already been asked about
        self.journal = Journal(config.journal_path)
        self._db_path = config.db_path

        self.setWindowTitle("Arcadia")
        self.resize(1360, 860)
        self.setStyleSheet(build_stylesheet(DEFAULT_ACCENT))

        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        root = QVBoxLayout(self.backdrop)
        root.setContentsMargins(32, 14, 32, 10)
        root.setSpacing(6)

        # --- top row: wordmark, search, sort ---
        self.wordmark = QLabel("ARCADIA")
        self.wordmark.setObjectName("wordmark")
        wm_font = self.wordmark.font()
        wm_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
        self.wordmark.setFont(wm_font)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search  (Ctrl+F)")
        self.search.setFixedWidth(260)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.populate_games())
        self.search.returnPressed.connect(lambda: self.coverflow.setFocus())

        self.sort_combo = QComboBox()
        for label, value in SORT_CHOICES:
            self.sort_combo.addItem(label, value)
        index = self.sort_combo.findData(config.sort)
        self.sort_combo.setCurrentIndex(max(0, index))
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        top = QHBoxLayout()
        top.addWidget(self.wordmark)
        top.addStretch(1)
        top.addWidget(self.search)
        top.addWidget(self.sort_combo)
        root.addLayout(top)

        # --- system pills ---
        self.systems_list = PillList()
        self.systems_list.setObjectName("systems")
        self.systems_list.setViewMode(QListView.ViewMode.ListMode)
        self.systems_list.setFlow(QListView.Flow.LeftToRight)
        self.systems_list.setWrapping(False)
        self.systems_list.setFixedHeight(58)
        self.systems_list.setIconSize(QSize(14, 14))
        self.systems_list.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.systems_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.systems_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.systems_list.currentRowChanged.connect(self._on_system_changed)
        self.systems_list.itemActivated.connect(lambda _item: self.coverflow.setFocus())
        root.addWidget(self.systems_list)

        # --- banner ---
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_font = self.banner.font()
        banner_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        self.banner.setFont(banner_font)
        self.banner_sub = QLabel()
        self.banner_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner_sub.setStyleSheet("color: rgba(236, 238, 244, 65%);")
        banner_box = QWidget()
        banner_layout = QVBoxLayout(banner_box)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(0)
        banner_layout.addWidget(self.banner)
        banner_layout.addWidget(self.banner_sub)
        self._banner_fx = QGraphicsOpacityEffect(banner_box)
        banner_box.setGraphicsEffect(self._banner_fx)
        self._banner_anim = QPropertyAnimation(self._banner_fx, b"opacity", self)
        self._banner_anim.setDuration(420)
        self._banner_anim.setStartValue(0.0)
        self._banner_anim.setEndValue(1.0)
        root.addWidget(banner_box)

        # --- cover flow ---
        self.coverflow = CoverFlow()
        self.coverflow.currentChanged.connect(lambda _i: self._on_game_changed())
        self.coverflow.activated.connect(lambda _i: self.launch())
        root.addWidget(self.coverflow, 1)

        # --- game info ---
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("gameTitle")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_lbl = QLabel()
        self.meta_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_lbl.setStyleSheet("color: rgba(236, 238, 244, 70%);")
        self.desc_lbl = QLabel()
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setMinimumWidth(680)
        self.desc_lbl.setMaximumWidth(900)
        self.desc_lbl.setFixedHeight(48)  # two lines at the stylesheet's 14px font
        self.desc_lbl.setStyleSheet("color: rgba(236, 238, 244, 55%);")
        root.addWidget(self.title_lbl)
        root.addWidget(self.meta_lbl)
        root.addWidget(self.desc_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        # --- actions ---
        self.launch_btn = QPushButton("▶  Launch")
        self.launch_btn.setObjectName("primary")
        self.launch_btn.clicked.connect(self.launch)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.fav_btn = QPushButton("★  Favorite")
        self.fav_btn.clicked.connect(self.toggle_favorite)
        self.states_btn = QPushButton("Save states  ▾")
        self.states_menu = QMenu(self)
        self.states_menu.aboutToShow.connect(self._build_states_menu)
        self.states_btn.setMenu(self.states_menu)
        self.files_btn = QPushButton("Files…")
        self.files_btn.setToolTip("Every file that makes up this game: discs, updates, DLC")
        self.files_btn.clicked.connect(self.show_files)
        self.surprise_btn = QPushButton("🎲  Surprise me")
        self.surprise_btn.clicked.connect(self.surprise)

        actions = QHBoxLayout()
        actions.addStretch(1)
        for button in (self.launch_btn, self.stop_btn, self.fav_btn, self.states_btn, self.files_btn, self.surprise_btn):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.hint_lbl = QLabel(HINTS)
        self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_lbl.setStyleSheet("color: rgba(236, 238, 244, 38%); font-size: 12px;")
        root.addWidget(self.hint_lbl)

        self.toast = Toast(self)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(1000)
        self.play_timer.timeout.connect(self._update_play_label)

        self._build_menu()
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.toggle_favorite)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.rescan)
        QShortcut(QKeySequence("F11"), self).activated.connect(self.toggle_fullscreen)

        self.controller = ControllerReader(self)
        self.controller.action.connect(self.handle_action)
        self.controller.start()

        # Watch the downloads folder: new files trigger a check after they've settled, and a
        # slow poll catches files that finished downloading without a directory change.
        self.inbox_watcher = QFileSystemWatcher(self)
        self.inbox_watcher.directoryChanged.connect(lambda _p: self.inbox_debounce.start())
        self.inbox_debounce = QTimer(self)
        self.inbox_debounce.setSingleShot(True)
        self.inbox_debounce.setInterval(6000)
        self.inbox_debounce.timeout.connect(self.check_inbox)
        self.inbox_poll = QTimer(self)
        self.inbox_poll.setInterval(45000)
        self.inbox_poll.timeout.connect(self.check_inbox)
        self._setup_inbox()

        self._scan_library(initial=True)
        QTimer.singleShot(0, self.coverflow.setFocus)
        QTimer.singleShot(800, self.check_inbox)
        QTimer.singleShot(5000, self._startup_update_check)

    # ----- menu, fullscreen, persistence -----

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Rescan library", self.rescan, "Ctrl+R")
        file_menu.addAction("Import ROMs…", self.import_roms, "Ctrl+I")
        self.undo_import_action = file_menu.addAction("Undo last import", self.undo_import)
        file_menu.aboutToShow.connect(self._update_undo_action)
        file_menu.addAction("Emulators…", self.open_emulators, "Ctrl+E")
        file_menu.addAction("Arcadia folder and setup…", self.open_setup, "Ctrl+Shift+S")
        file_menu.addAction("BIOS, emulator settings and sync…", self.open_tools, "Ctrl+Shift+B")
        file_menu.addAction("Settings…", self.open_settings)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, "Ctrl+Q")

        view_menu = self.menuBar().addMenu("&View")
        self.fullscreen_action = QAction("Fullscreen", self, checkable=True)
        self.fullscreen_action.triggered.connect(lambda _c: self.toggle_fullscreen())
        view_menu.addAction(self.fullscreen_action)
        self.empty_action = QAction("Show systems with no games", self, checkable=True)
        self.empty_action.setChecked(self.config.show_empty_systems)
        self.empty_action.toggled.connect(self._on_show_empty_toggled)
        view_menu.addAction(self.empty_action)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().show()
        else:
            self.showFullScreen()
            self.menuBar().hide()
        self.fullscreen_action.setChecked(self.isFullScreen())

    def _save_config(self) -> None:
        try:
            self.config.save(self.config_path)
        except OSError as exc:
            self.toast.show_message(f"Could not save settings: {exc}")

    def _on_sort_changed(self, _index: int) -> None:
        self.config.sort = self.sort_combo.currentData()
        self._save_config()
        self.populate_games()

    def _on_show_empty_toggled(self, checked: bool) -> None:
        self.config.show_empty_systems = checked
        self._save_config()
        self.refresh_systems()

    # ----- theme -----

    def _apply_accent(self, hex_color: str) -> None:
        if hex_color == self._accent_hex:
            return
        self._accent_hex = hex_color
        self.setStyleSheet(build_stylesheet(hex_color))
        self.backdrop.set_accent(QColor(hex_color))
        self.coverflow.set_accent(QColor(hex_color))

    def _play_banner(self, text: str) -> None:
        self.banner.setText(text.upper())
        self._banner_anim.stop()
        self._banner_anim.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.reposition()

    # ----- library & views -----

    def rescan(self, initial: bool = False) -> None:
        """Sort anything waiting in the downloads folder, then rescan the library."""
        if not initial:
            self.check_inbox(rescan_after=False)
        self._scan_library(initial)

    def _scan_library(self, initial: bool = False) -> None:
        total = 0
        for system in self.config.systems:
            games = scan_system(self.config.rom_root_path, system)
            self.library.sync(system.id, games)
            total += len(games)
        self.refresh_systems()
        if not self.config.rom_root_path.is_dir():
            self.toast.show_message(f"ROM folder not found: {self.config.rom_root_path}. Set it in File → Settings.", 6000)
        elif not initial:
            self.toast.show_message(f"Found {total} games")

    def refresh_systems(self) -> None:
        """Rebuild the pill bar. Systems with no games are hidden unless they are all empty."""
        summary = self.library.summary()
        current = self.current_system_id()
        entries: list[tuple[str, str, int]] = []
        if summary["played"]:
            entries.append((VIEW_RECENT, VIEW_NAMES[VIEW_RECENT], summary["played"]))
        if summary["favorites"]:
            entries.append((VIEW_FAVORITES, VIEW_NAMES[VIEW_FAVORITES], summary["favorites"]))
        systems = [(s.id, s.name, summary["systems"].get(s.id, 0)) for s in self.config.systems]
        if not self.config.show_empty_systems and any(count for _i, _n, count in systems):
            systems = [e for e in systems if e[2]]
        entries += systems

        self.systems_list.blockSignals(True)
        self.systems_list.clear()
        selected = None
        for view_id, name, count in entries:
            item = QListWidgetItem(dot_icon(view_accent(view_id)), f"{name}   {count}")
            item.setData(Qt.ItemDataRole.UserRole, view_id)
            self.systems_list.addItem(item)
            if view_id == current:
                selected = item
        if selected is None and self.systems_list.count():
            selected = self.systems_list.item(0)
        if selected is not None:
            self.systems_list.setCurrentItem(selected)
        self.systems_list.blockSignals(False)
        self._on_system_changed(0)

    def current_system_id(self) -> str | None:
        item = self.systems_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def current_game_key(self) -> str | None:
        return self.coverflow.current_key()

    def _system_name(self, system_id: str) -> str:
        try:
            return self.config.system(system_id).name
        except KeyError:
            return system_id

    def _view_name(self, view_id: str) -> str:
        return VIEW_NAMES.get(view_id) or self._system_name(view_id)

    def _on_system_changed(self, _row: int) -> None:
        view = self.current_system_id()
        changed = view != self._last_view
        self._last_view = view
        self.populate_games()
        if view is None:
            self.banner.setText("")
            return
        self._apply_accent(view_accent(view))
        if changed:
            self._play_banner(self._view_name(view))

    def _query_rows(self, view: str | None) -> list:
        search = self.search.text().strip()
        sort = self.config.sort
        if view is None:
            return []
        if view == VIEW_RECENT:
            return self.library.games(None, search=search, played_only=True, sort="recent")
        if view == VIEW_FAVORITES:
            return self.library.games(None, search=search, favorites_only=True, sort=sort)
        return self.library.games(view, search=search, sort=sort)

    def _load_cover(self, system_id: str, title: str, rom: Path) -> QPixmap:
        meta = load_metadata(self.config.media_path, system_id, rom)
        if meta.cover:
            pix = QPixmap(str(meta.cover))
            if not pix.isNull():
                return pix.scaled(
                    COVER_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
        return placeholder_pixmap(meta.title or title, COVER_SIZE, accent_for(system_id))

    def populate_games(self) -> None:
        view = self.current_system_id()
        previous = self.current_game_key()
        rows = self._query_rows(view)
        items = []
        for row in rows:
            title = ("★ " if row["favorite"] else "") + row["title"]
            loader = lambda sid=row["system_id"], t=row["title"], p=Path(row["path"]): self._load_cover(sid, t, p)
            items.append((row["key"], title, loader))
        self.coverflow.set_items(items, select_key=previous)

        played = sum(r["total_seconds"] for r in rows)
        noun = "game" if len(rows) == 1 else "games"
        sub = f"{len(rows)} {noun}"
        if played:
            sub += f"   ·   {fmt_duration(played)} played"
        self.banner_sub.setText(sub)
        self._on_game_changed()

    def _on_game_changed(self) -> None:
        key = self.current_game_key()
        if key is None:
            self.title_lbl.setText("")
            self.meta_lbl.setText("")
            self.desc_lbl.setText("")
        else:
            self._show_details(key)
        self._update_running_state()

    def _show_details(self, key: str) -> None:
        row = self.library.get(key)
        if row is None:
            return
        rom = Path(row["path"])
        meta = load_metadata(self.config.media_path, row["system_id"], rom)
        self.title_lbl.setText(("★ " if row["favorite"] else "") + (meta.title or row["title"]))
        parts = [self._system_name(row["system_id"])]
        if meta.year:
            parts.append(meta.year)
        if meta.genre:
            parts.append(meta.genre)
        if row["play_count"]:
            plays = "play" if row["play_count"] == 1 else "plays"
            parts.append(f"{row['play_count']} {plays}, {fmt_duration(row['total_seconds'])}")
            parts.append(f"last played {fmt_timestamp(row['last_played'])}")
        else:
            parts.append("never played")
        children = self.library.children(key)
        if children:
            versions = [
                info.version
                for c in children
                if c["kind"] == "update" and (info := parse_switch(Path(c["path"]).name)) is not None
            ]
            parts.insert(1, bundle_summary([c["kind"] for c in children], versions))
        elif row["kind"] in ("update", "dlc"):
            parts.insert(1, "update file" if row["kind"] == "update" else "DLC file")
        self.meta_lbl.setText("   ·   ".join(parts))
        self.desc_lbl.setText(_shorten(meta.description, 200))
        self.desc_lbl.setToolTip(meta.description)

    def _launch_extras(self, key: str) -> dict[str, list[Path]]:
        """Files linked to a game, for the {discs} / {updates} / {dlc} launch placeholders."""
        names = {"disc": "discs", "update": "updates", "dlc": "dlc"}
        extras: dict[str, list[Path]] = {v: [] for v in names.values()}
        for child in self.library.children(key):
            if child["kind"] in names:
                extras[names[child["kind"]]].append(Path(child["path"]))
        return extras

    def _file_rows(self, key: str) -> list[tuple[str, Path]]:
        row = self.library.get(key)
        main = Path(row["path"])
        rows = [("Playlist" if main.suffix.lower() == ".m3u" else "Game", main)]
        for child in self.library.children(key):
            path = Path(child["path"])
            if child["kind"] == "update":
                info = parse_switch(path.name)
                rows.append((f"Update {info.version}".strip() if info else "Update", path))
            else:
                rows.append(({"disc": "Disc", "dlc": "DLC"}.get(child["kind"], child["kind"].title()), path))
        return rows

    def show_files(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        row = self.library.get(key)
        FilesDialog(row["title"], self._file_rows(key), self).exec()

    def surprise(self) -> None:
        count = self.coverflow.count()
        if count:
            self.coverflow.set_index(random.randrange(count))
            self.toast.show_message(f"🎲  {self.coverflow.current_title()}")

    # ----- launching -----

    def launch(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        if self.process is not None:
            self.toast.show_message("A game is already running.")
            return
        row = self.library.get(key)
        if row["kind"] in ("update", "dlc"):
            what = "an update" if row["kind"] == "update" else "DLC"
            QMessageBox.information(
                self,
                "Not a game",
                f"This file is {what}, and its base game isn't in your library, so there is nothing to launch.\n"
                "Add the base game and Arcadia will attach this to it.",
            )
            return
        system = self.config.system(row["system_id"])
        try:
            plan = resolve_launch(self.config, system, Path(row["path"]), self._launch_extras(key))
        except LaunchError as exc:
            QMessageBox.warning(self, "Cannot launch", str(exc))
            return
        args = plan.args

        proc = QProcess(self)
        proc.setProgram(args[0])
        proc.setArguments(args[1:])
        if plan.env:  # an emulator Arcadia installed keeps its settings and saves in its own folder
            environment = QProcessEnvironment.systemEnvironment()
            for name, value in plan.env.items():
                environment.insert(name, value)
            proc.setProcessEnvironment(environment)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_process_error)
        self.process = proc
        self.running_key = key
        self.session_start = time.time()
        proc.start()
        self.play_timer.start()
        self.toast.show_message(f"Launching {row['title']}…" + (" with your installed copy" if plan.via.startswith("local:") else ""))
        self._update_running_state()

    def _on_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            cmd = " ".join([self.process.program()] + self.process.arguments())
            QMessageBox.warning(self, "Cannot launch", f"Could not start:\n{cmd}\n\nCheck the launch command in Settings.")
            self._end_session(record=False)

    def _on_finished(self, _exit_code, _exit_status) -> None:
        if self.process is not None:
            self._end_session(record=True)

    def _end_session(self, record: bool) -> None:
        key = self.running_key
        seconds = int(time.time() - self.session_start)
        self.play_timer.stop()
        if record and key:
            self.library.record_session(key, self.session_start, seconds)
        if self.process is not None:
            self.process.deleteLater()
        self.process = None
        self.running_key = None
        if record:
            self.toast.show_message(f"Played for {fmt_duration(seconds)}")
        self.refresh_systems()

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        QTimer.singleShot(3000, self._force_kill)

    def _force_kill(self) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _update_play_label(self) -> None:
        if self.process is not None:
            self.launch_btn.setText(f"Playing…  {fmt_clock(time.time() - self.session_start)}")

    def _update_running_state(self) -> None:
        running = self.process is not None
        has_game = self.current_game_key() is not None
        self.launch_btn.setEnabled(has_game and not running)
        if running:
            self._update_play_label()
        else:
            self.launch_btn.setText("▶  Launch")
        self.stop_btn.setVisible(running)
        self.fav_btn.setEnabled(has_game)
        self.states_btn.setEnabled(has_game)
        self.files_btn.setEnabled(has_game)
        self.surprise_btn.setEnabled(self.coverflow.count() > 0)

    # ----- favorites & save states -----

    def toggle_favorite(self) -> None:
        key = self.current_game_key()
        if key is None:
            return
        row = self.library.get(key)
        now_fav = not bool(row["favorite"])
        self.library.set_favorite(key, now_fav)
        self.toast.show_message("★  Added to favorites" if now_fav else "Removed from favorites")
        self.refresh_systems()

    def _build_states_menu(self) -> None:
        menu = self.states_menu
        menu.clear()
        key = self.current_game_key()
        if key is None:
            menu.addAction("No game selected").setEnabled(False)
            return
        row = self.library.get(key)
        menu.addAction("Save snapshot now", self.save_state)
        snaps = list_snapshots(self.config.savestate_path, Path(row["path"]))
        sub = menu.addMenu("Restore snapshot")
        sub.setEnabled(bool(snaps) and self.process is None)
        for snap in snaps:
            action = sub.addAction(snapshot_label(snap.name))
            action.triggered.connect(lambda _checked=False, p=snap: self.restore_state(p))

    def _save_dir_for(self, row) -> Path | None:
        system = self.config.system(row["system_id"])
        if not system.save_dir:
            QMessageBox.warning(
                self, "No save folder", "Set this system's emulator save folder in File → Settings first."
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
            create_snapshot(save_dir, Path(row["path"]), self.config.savestate_path)
        except SaveStateError as exc:
            QMessageBox.warning(self, "Save state failed", str(exc))
            return
        self.toast.show_message("Snapshot saved")

    def restore_state(self, snapshot: Path) -> None:
        key = self.current_game_key()
        if key is None or self.process is not None:
            return
        row = self.library.get(key)
        save_dir = self._save_dir_for(row)
        if save_dir is None:
            return
        answer = QMessageBox.question(
            self,
            "Restore snapshot",
            f"Restore snapshot from {snapshot_label(snapshot.name)}?\nCurrent saves are backed up first.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_snapshot(snapshot, save_dir, Path(row["path"]), self.config.savestate_path)
        except SaveStateError as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))
            return
        self.toast.show_message("Snapshot restored")

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
        if name in ("up", "back") and focus is self.coverflow:
            self.systems_list.setFocus()
            return
        if name == "down" and focus is self.systems_list:
            self.coverflow.setFocus()
            return
        if focus is not self.systems_list and focus is not self.coverflow:
            self.coverflow.setFocus()
            focus = self.coverflow
        QApplication.sendEvent(focus, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    # ----- sorting ROMs from the downloads folder -----

    def _setup_inbox(self) -> None:
        for path in self.inbox_watcher.directories():
            self.inbox_watcher.removePath(path)
        inbox = self.config.inbox_path
        if inbox is not None and inbox.is_dir():
            self.inbox_watcher.addPath(str(inbox))
            self.inbox_poll.start()
        else:
            self.inbox_poll.stop()

    def check_inbox(self, rescan_after: bool = True) -> None:
        """Look at the downloads folder. ROMs whose header confirms their system are moved
        automatically (if enabled); anything else is put in front of the user once."""
        inbox = self.config.inbox_path
        if self._closed or self._importing or inbox is None or not inbox.is_dir():
            return
        plan = build_plan(inbox, self.config)
        if not plan.items:
            return

        pending = plan.items
        if self.config.auto_import:
            auto = [i for i in plan.items if i.confidence is Confidence.CERTAIN and not i.exists]
            if auto:
                result = apply_plan(auto, self.journal)
                if result.moved:
                    n = len(result.moved)
                    self.toast.show_message(f"Sorted {n} ROM{'s' if n != 1 else ''} into your library")
                    if rescan_after:
                        self._scan_library()
                moved_ids = {id(i) for i in result.moved}
                pending = [i for i in plan.items if id(i) not in moved_ids]

        fresh = [i for i in pending if str(i.source) not in self._asked]
        if fresh and self.process is None:  # don't interrupt a game with a dialog
            self._asked.update(str(i.source) for i in pending)
            self._show_import_dialog(Plan(items=pending, waiting=plan.waiting, ignored=plan.ignored), inbox)

    def _show_import_dialog(self, plan: Plan, inbox) -> None:
        self._importing = True
        try:
            dialog = ImportDialog(self.config, plan, self, inbox_label=str(inbox))
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = apply_plan(dialog.selected_items(), self.journal, keep_both=dialog.keep_both())
                self._report_import(result)
        finally:
            self._importing = False

    def _report_import(self, result) -> None:
        if result.moved:
            n = len(result.moved)
            self.toast.show_message(f"Moved {n} ROM{'s' if n != 1 else ''} into your library")
            self._scan_library()
        if result.skipped:
            lines = "\n".join(f"• {item.source.name}: {why}" for item, why in result.skipped)
            QMessageBox.warning(self, "Some ROMs were not moved", lines)

    def import_roms(self) -> None:
        """File > Import ROMs: review everything in the downloads folder, including sure matches."""
        inbox = self.config.inbox_path
        if inbox is None or not inbox.is_dir():
            start = str(inbox) if inbox else str(Path.home() / "Downloads")
            folder = QFileDialog.getExistingDirectory(self, "Choose your downloads folder", start)
            if not folder:
                return
            self.config.inbox_dir = folder
            self._save_config()
            self._setup_inbox()
            inbox = self.config.inbox_path
        plan = build_plan(inbox, self.config)
        if not plan.items:
            extra = f" ({len(plan.waiting)} still downloading)" if plan.waiting else ""
            self.toast.show_message(f"No ROMs to import in {inbox}{extra}")
            return
        self._asked.update(str(i.source) for i in plan.items)
        self._show_import_dialog(plan, inbox)

    def _update_undo_action(self) -> None:
        n = self.journal.last_count()
        self.undo_import_action.setEnabled(n > 0)
        self.undo_import_action.setText(f"Undo last import ({n} file{'s' if n != 1 else ''})" if n else "Undo last import")

    def undo_import(self) -> None:
        n = self.journal.last_count()
        if not n:
            return
        answer = QMessageBox.question(
            self, "Undo last import", f"Move the {n} file{'s' if n != 1 else ''} from the last import back to where they came from?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        restored, problems = self.journal.undo_last()
        if restored:
            self.toast.show_message(f"Moved {restored} file{'s' if restored != 1 else ''} back")
            self._asked.clear()  # they're back in the inbox, so they may be offered again
            self._scan_library()
        if problems:
            QMessageBox.warning(self, "Some files were not moved back", "\n".join(f"• {p}" for p in problems))

    # ----- settings & shutdown -----

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply(self.config)
            self._save_config()
            if self.config.home_path is not None:
                self.config.ensure_layout()
            self.journal = Journal(self.config.journal_path)
            self._setup_inbox()
            self.rescan()
            if self.config.db_path != self._db_path:
                self.toast.show_message("Restart Arcadia to use the library in its new folder", 6000)

    def open_tools(self) -> None:
        """BIOS files, RetroArch settings and cores, Flatpak access, save sync."""
        ToolsDialog(self.config, parent=self).exec()
        self._save_config()

    def open_setup(self) -> None:
        """The overview of what's ready, plus bringing a library in and backing up."""
        counts = self.library.summary()["systems"]
        dialog = SetupDialog(self.config, self.config_path, self.journal, counts, parent=self)
        dialog.exec()
        if dialog.config_changed:  # the library was brought into the Arcadia folder
            self._save_config()
            self.config.ensure_layout()
            self.journal = Journal(self.config.journal_path)
            self._setup_inbox()
            self.rescan()
            if self.config.db_path != self._db_path:
                self.toast.show_message("Restart Arcadia to use your library in the new folder", 6000)
        if dialog.restored:  # a restore replaced the library file underneath the open one
            self.library.close()
            self.library = Library(self.config.db_path)
            self._db_path = self.config.db_path
            self._scan_library()
            self.toast.show_message("Backup restored. Restart Arcadia to use the restored settings.", 6000)
        if dialog.emulators_changed:
            self.toast.show_message("Emulators updated")

    def _startup_update_check(self) -> None:
        """If the user asked for it, look for emulator updates in the background and just say so.
        Nothing is downloaded, and it never blocks closing the app."""
        if self._closed or not self.config.check_updates:
            return
        installer = Installer(self.config.emulators_path)
        if not installer.installed():
            return
        self._update_task = DaemonTask(lambda: plan_updates(installer), self)
        self._update_task.done.connect(self._on_startup_updates)
        self._update_task.start()

    def _on_startup_updates(self, rows, error) -> None:
        if self._closed or error is not None or not rows:
            return
        waiting = sum(1 for row in rows if row.status in (READY, CHOOSE))
        if waiting:
            self.toast.show_message(
                f"{waiting} emulator update{'s' if waiting != 1 else ''} available: File → Emulators… → Update all", 7000
            )

    def open_emulators(self) -> None:
        dialog = EmulatorsDialog(self.config, parent=self)
        dialog.exec()
        if dialog.changed:
            self.toast.show_message("Emulators updated")

    def closeEvent(self, event) -> None:
        self._closed = True
        self.inbox_debounce.stop()
        self.inbox_poll.stop()
        self.controller.stop()
        if self.process is not None:
            self.process.terminate()
            self.process.waitForFinished(3000)
            self._end_session(record=True)
        self.library.close()
        super().closeEvent(event)
