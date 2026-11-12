"""Qt user interface.

Layout, top to bottom: wordmark with search and sort, a bar of system pills, the
current system's banner, the cover-flow shelf, then the selected game's info and
actions, and a line of key hints. Messages appear as toasts.
"""

from __future__ import annotations

import dataclasses
import random
import shutil
import time
import zlib
from pathlib import Path

from PySide6.QtCore import QEvent, QFileSystemWatcher, QProcess, QProcessEnvironment, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QKeyEvent, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QPlainTextEdit,
    QTabBar,
    QTextEdit,
    QProgressDialog,
    QTabWidget,
    QStackedWidget,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcadia.folder_picker import choose_folder
from arcadia.config import Config, SystemConfig
from arcadia.consoles_view import ConsoleCarousel, Entry
from arcadia.coverflow import COVER_H, COVER_W, CoverFlow
from arcadia.empty_state import EmptyState
from arcadia.welcome_dialog import WelcomeDialog
from arcadia import appupdate, logos, pixelart, screenfit
from arcadia.sounds import Sounds
from arcadia.transitions import ZoomOverlay
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
from arcadia.setup_dialog import BringInDialog, SetupDialog
from arcadia.tools_dialog import ToolsDialog
from arcadia.sorter import Confidence, Journal, Plan, apply_plan, build_plan
from arcadia import savesync
from arcadia.tasks import DaemonTask, Task

TaskClass = Task  # tests swap this for a version that runs immediately
from arcadia.theme import DEFAULT_ACCENT, Backdrop, Toast, build_stylesheet
from arcadia.updates import CHOOSE, READY, plan_updates
from arcadia.util import bundle_summary, fmt_clock, fmt_duration, fmt_timestamp, snapshot_label

COVER_SIZE = QSize(COVER_W, COVER_H)

VIEW_RECENT = "__recent__"
VIEW_FAVORITES = "__favorites__"
VIEW_ACCENTS = {VIEW_RECENT: "#f2a33a", VIEW_FAVORITES: "#ff5a7a", "__all__": "#8a93a6"}
VIEW_NAMES = {VIEW_RECENT: "Recently played", VIEW_FAVORITES: "Favorites", "__all__": "All games"}

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

HINTS = "←  →  browse     A–Z  jump to letter     Enter  launch     Esc  back to consoles     Ctrl+D  favorite     Ctrl+F  search     F11  fullscreen"
CONSOLE_HINTS = "←  ↑  ↓  →  choose     Enter  open     A–Z  jump to a console     Ctrl+F  search all games     F11  fullscreen"
VIEW_ALL = "__all__"


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

        self.check_app_updates = QCheckBox("Check for a newer Arcadia when it starts (contacts GitHub; nothing installs without asking)")
        self.check_app_updates.setChecked(config.check_app_updates)

        form = QFormLayout()
        form.addRow("Arcadia folder (everything in one place):", home_row)
        form.addRow("ROM root folder:", rom_row)
        form.addRow("Downloads folder (ROM inbox):", inbox_row)
        form.addRow("", self.auto_import)
        form.addRow("", self.check_updates)
        form.addRow("", self.check_app_updates)
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
        folder = choose_folder(self, "Arcadia folder", start)
        if folder:
            self.home_dir.setText(folder)

    def _browse(self) -> None:
        folder = choose_folder(self, "ROM root folder", self.rom_root.text())
        if folder:
            self.rom_root.setText(folder)

    def _browse_inbox(self) -> None:
        start = self.inbox_dir.text().strip() or str(Path.home() / "Downloads")
        folder = choose_folder(self, "Downloads folder (ROM inbox)", start)
        if folder:
            self.inbox_dir.setText(folder)

    def apply(self, config: Config) -> None:
        config.home_dir = self.home_dir.text().strip()
        config.rom_root = self.rom_root.text().strip() if config.home_dir else (self.rom_root.text().strip() or config.rom_root)
        config.inbox_dir = self.inbox_dir.text().strip()
        config.auto_import = self.auto_import.isChecked()
        config.check_updates = self.check_updates.isChecked()
        config.check_app_updates = self.check_app_updates.isChecked()
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
        self._sync_task = None
        self._importing = False  # an import dialog is open
        self._asked: set[str] = set()  # inbox files the user has already been asked about
        self.journal = Journal(config.journal_path)
        self._db_path = config.db_path

        self._configure_art()  # your own pictures, your downloaded logos, and which style to show
        screenfit.install()  # dialogs shrink to the screen (a Steam Deck's is small)
        self.setWindowTitle("Arcadia")
        self.resize(1360, 860)
        self.setStyleSheet(build_stylesheet(DEFAULT_ACCENT))

        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        outer = QVBoxLayout(self.backdrop)
        outer.setContentsMargins(0, 0, 0, 0)
        self.sounds = Sounds(config.sounds)
        self.stack = QStackedWidget()  # page 0: choose a console; page 1: choose a game
        outer.addWidget(self.stack)
        self.zoom = ZoomOverlay(self.backdrop)  # the zoom between the two screens
        self.games_page = QWidget()
        root = QVBoxLayout(self.games_page)
        root.setContentsMargins(32, 14, 32, 10)
        root.setSpacing(6)

        # --- top row: back, search, sort ---
        self.back_btn = QPushButton("‹   Consoles")
        self.back_btn.setToolTip("Back to the consoles  (Esc)")
        self.back_btn.clicked.connect(self.show_consoles)

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
        top.addWidget(self.back_btn)
        top.addStretch(1)
        top.addWidget(self.search)
        top.addWidget(self.sort_combo)
        root.addLayout(top)

        # --- page 0: choose a console ---
        self.console_page = QWidget()
        cp = QVBoxLayout(self.console_page)
        cp.setContentsMargins(40, 18, 40, 12)
        cp.setSpacing(6)
        self.wordmark = QLabel("ARCADIA")
        self.wordmark.setObjectName("wordmark")
        wm_font = self.wordmark.font()
        wm_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
        self.wordmark.setFont(wm_font)
        self.library_lbl = QLabel("")
        self.library_lbl.setStyleSheet("color: rgba(236, 238, 244, 55%);")
        console_top = QHBoxLayout()
        console_top.addWidget(self.wordmark)
        console_top.addStretch(1)
        console_top.addWidget(self.library_lbl)
        cp.addLayout(console_top)
        self.choose_lbl = QLabel("CHOOSE A CONSOLE")
        self.choose_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose_font = self.choose_lbl.font()
        choose_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7.0)
        choose_font.setWeight(QFont.Weight.DemiBold)
        self.choose_lbl.setFont(choose_font)
        self.choose_lbl.setStyleSheet("color: rgba(236, 238, 244, 55%); font-size: 14px;")
        cp.addWidget(self.choose_lbl)
        self.carousel = ConsoleCarousel()
        self.carousel.currentChanged.connect(self._on_system_changed)
        self.carousel.currentChanged.connect(lambda _i: self.sounds.play("tick"))
        self.carousel.activated.connect(lambda _i: self.show_games())
        cp.addWidget(self.carousel, 1)
        self.console_empty = EmptyState()
        self.console_empty.hide()
        cp.addWidget(self.console_empty, 1)
        self.console_hint = QLabel(CONSOLE_HINTS)
        self.console_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.console_hint.setStyleSheet("color: rgba(236, 238, 244, 38%); font-size: 12px;")
        cp.addWidget(self.console_hint)
        self.stack.addWidget(self.console_page)

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
        self.empty = EmptyState()
        self.empty.hide()
        root.addWidget(self.empty, 1)

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
        self.stack.addWidget(self.games_page)

        self.toast = Toast(self)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(1000)
        self.play_timer.timeout.connect(self._update_play_label)

        self._build_menu()
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
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
        QTimer.singleShot(0, self.carousel.setFocus)
        QTimer.singleShot(800, self.check_inbox)
        QTimer.singleShot(5000, self._startup_update_check)
        QTimer.singleShot(7000, lambda: self.check_app_update(quiet=True))
        QTimer.singleShot(3000, self._auto_sync)

    # ----- menu, fullscreen, persistence -----

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Get started…", self.show_welcome)
        file_menu.addSeparator()
        file_menu.addAction("Rescan library", self.rescan, "Ctrl+R")
        file_menu.addAction("Import ROMs…", self.import_roms, "Ctrl+I")
        self.undo_import_action = file_menu.addAction("Undo last import", self.undo_import)
        file_menu.aboutToShow.connect(self._update_undo_action)
        file_menu.addAction("Emulators…", self.open_emulators, "Ctrl+E")
        file_menu.addAction("Arcadia folder and setup…", self.open_setup, "Ctrl+Shift+S")
        file_menu.addAction("BIOS, emulator settings and sync…", lambda: self.open_tools(0), "Ctrl+Shift+B")
        file_menu.addAction("Settings…", self.open_settings)
        file_menu.addAction("Check for Arcadia updates…", lambda: self.check_app_update(quiet=False))
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, "Ctrl+Q")

        view_menu = self.menuBar().addMenu("&View")
        self.sounds_action = QAction("Sound effects", self, checkable=True)
        self.sounds_action.setChecked(self.config.sounds)
        self.sounds_action.toggled.connect(self._on_sounds_toggled)
        view_menu.addAction(self.sounds_action)
        pictures = view_menu.addMenu("Pictures")
        group = QActionGroup(self)
        self.logos_action = QAction("Console logos", self, checkable=True)
        self.drawings_action = QAction("Console drawings", self, checkable=True)
        for action, style in ((self.logos_action, "logos"), (self.drawings_action, "drawings")):
            group.addAction(action)
            pictures.addAction(action)
            action.setChecked(self.config.art_style == style)
            action.triggered.connect(lambda _c=False, s=style: self._set_art_style(s))
        pictures.addSeparator()
        pictures.addAction("Download console logos…", self.download_logos)
        view_menu.addAction("Use my own console pictures…", self.open_console_art)
        view_menu.addAction("Check my console pictures", self.check_console_art)
        view_menu.addSeparator()
        self.fullscreen_action = QAction("Fullscreen", self, checkable=True)
        self.fullscreen_action.triggered.connect(lambda _c: self.toggle_fullscreen())
        view_menu.addAction(self.fullscreen_action)
        self.empty_action = QAction("Show systems with no games", self, checkable=True)
        self.empty_action.setChecked(self.config.show_empty_systems)
        self.empty_action.toggled.connect(self._on_show_empty_toggled)
        view_menu.addAction(self.empty_action)

    def _configure_art(self) -> None:
        pixelart.configure(self.config.media_path / "consoles", self.config.media_path / "logos", self.config.art_style)

    def _set_art_style(self, style: str) -> None:
        self.config.art_style = style
        self._save_config()
        self._configure_art()
        self.carousel.update()

    def download_logos(self) -> None:
        """Fetch each console's logo from Wikipedia / Wikimedia Commons, after saying what that means."""
        answer = QMessageBox.question(
            self,
            "Download console logos",
            "Arcadia will download each console's logo from Wikipedia / Wikimedia Commons and keep them in your own "
            f"media folder ({self.config.media_path / 'logos'}). They are the makers' trademarks, used here only to label "
            "each console on screen, and they aren't included with Arcadia.\n\n"
            "Each is then redrawn in the pixel style of its console's era. This takes a minute or two. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        media = self.config.media_path
        progress = QProgressDialog("Downloading console logos…", "", 0, 100, self)
        progress.setCancelButton(None)
        progress.setWindowTitle("Console logos")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        task = TaskClass(lambda report: logos.fetch_logos(media, progress=report), self)
        task.progress.connect(lambda done, total: (progress.setMaximum(max(1, total)), progress.setValue(done)))
        task.done.connect(lambda result, error: self._logos_done(progress, result, error))
        self._logo_task = task
        task.start()

    def _logos_done(self, progress, result, error) -> None:
        progress.close()
        self._logo_task = None
        self._configure_art()
        self.carousel.update()
        if error is not None:
            QMessageBox.warning(self, "Console logos", f"Couldn't download the logos: {error}")
            return
        text = f"Downloaded {len(result.done)} logo{'s' if len(result.done) != 1 else ''}."
        if result.failed:
            text += f"\n\nNo logo could be found for {len(result.failed)}: " + ", ".join(sorted(result.failed)) + (
                "\n\nThose keep their drawings. You can put your own picture in the console pictures folder (View → Use my own console pictures)."
            )
        QMessageBox.information(self, "Console logos", text)
        if result.done and self.config.art_style != "logos":
            self.toast.show_message("Logos downloaded: View → Pictures → Console logos to show them", 6000)

    def open_console_art(self) -> None:
        """Open the folder where console pictures go (nes.png, snes.png, ...), and say how it works."""
        folder = self.config.media_path / "consoles"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        QMessageBox.information(
            self,
            "Your own console pictures",
            f"Put a picture in this folder named after the console and it replaces Arcadia's drawing:\n\n{folder}\n\n"
            "For example  nes.png, snes.png, n64.png, gc.png, psx.png, genesis.webp.\n"
            "PNG or WebP with a transparent background looks best. Close and reopen Arcadia (or press Ctrl+R) to see them.",
        )

    def check_console_art(self) -> None:
        folder = self.config.media_path / "consoles"
        known = {s.id for s in self.config.systems} | set(VIEW_NAMES)
        problems = pixelart.check_custom(folder, known)
        if not folder.is_dir() or not any(folder.iterdir()):
            text = f"There are no pictures of your own yet. Put them in:\n{folder}"
        elif problems:
            text = "Things to look at:\n\n" + "\n".join("• " + p for p in problems)
        else:
            text = "Your pictures all look fine."
        QMessageBox.information(self, "Your console pictures", text)

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

    def _on_sounds_toggled(self, checked: bool) -> None:
        self.config.sounds = checked
        self.sounds.enabled = checked
        self._save_config()
        if checked:
            self.sounds.play("open")

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
        self._configure_art()  # picks up pictures added since last time
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
        """Rebuild the console grid. Consoles with no games are hidden unless the View menu says otherwise.
        A library with no games at all shows the welcome instead of a wall of empty tiles."""
        summary = self.library.summary()
        current = self.current_system_id()
        total = sum(summary["systems"].values())
        entries: list[tuple[str, str, int]] = []
        if summary["played"]:
            entries.append((VIEW_RECENT, VIEW_NAMES[VIEW_RECENT], summary["played"]))
        if summary["favorites"]:
            entries.append((VIEW_FAVORITES, VIEW_NAMES[VIEW_FAVORITES], summary["favorites"]))
        if total:
            entries.append((VIEW_ALL, VIEW_NAMES[VIEW_ALL], total))
        systems = [(s.id, s.name, summary["systems"].get(s.id, 0)) for s in self.config.systems]
        if not self.config.show_empty_systems:
            systems = [e for e in systems if e[2]]
        entries += systems
        if not total and not self.config.show_empty_systems:
            entries = []

        shown = [Entry(view_id, name, count, view_accent(view_id)) for view_id, name, count in entries]
        keep = current if any(e.view_id == current for e in shown) else next((e.view_id for e in shown if not e.view_id.startswith("__")), shown[0].view_id if shown else None)
        self.carousel.blockSignals(True)
        self.carousel.set_entries(shown, select_id=keep)
        self.carousel.blockSignals(False)

        consoles = sum(1 for e in systems if e[2])
        self.library_lbl.setText(f"{consoles} console{'s' if consoles != 1 else ''}  ·  {total} game{'s' if total != 1 else ''}" if total else "")
        welcome = not entries
        self.carousel.setVisible(not welcome)
        self.choose_lbl.setVisible(not welcome)
        self.console_empty.setVisible(welcome)
        if welcome:
            self.console_empty.show_message(
                "Welcome to Arcadia",
                "Your library is empty. Add your games, then install the emulators you need. The checklist walks you through it.",
                [("Get started", self.show_welcome, True), ("Import ROMs…", self.import_roms, False)],
            )
            self.stack.setCurrentIndex(0)
        self._on_system_changed(0)

    # ----- the two screens -----

    def show_games(self) -> None:
        """Open the highlighted console: from "choose a console" to "choose a game"."""
        if self.current_system_id() is None:
            return
        self.populate_games()
        if not self.on_games_page():
            self.sounds.play("open")
            self._switch_page(1, grow=True)
        (self.coverflow if self.coverflow.isVisible() else self.back_btn).setFocus()

    def show_consoles(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()  # a search belongs to the console you were in
        self.search.blockSignals(False)
        self.populate_games()
        if self.on_games_page():
            self.sounds.play("back")
            self._switch_page(0, grow=False)
        self.carousel.setFocus()

    def _switch_page(self, index: int, grow: bool) -> None:
        """Change screens with the zoom (just a cut when the window isn't on screen)."""
        snapshot = self.stack.grab() if self.isVisible() and self.stack.width() > 100 else None
        self.zoom.finish()
        self.stack.setCurrentIndex(index)
        if snapshot is not None:
            self.zoom.start(snapshot, grow)

    def on_games_page(self) -> bool:
        return self.stack.currentIndex() == 1

    def focus_search(self) -> None:
        """Ctrl+F: from the console screen this searches every game."""
        if not self.on_games_page():
            self.carousel.set_current_id(VIEW_ALL)
            self.show_games()
        self.search.setFocus()
        self.search.selectAll()

    def keyPressEvent(self, event) -> None:
        if self.on_games_page() and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace) and not self.search.hasFocus():
            self.show_consoles()
            return
        if event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown) and not self.search.hasFocus():
            self.handle_action("prev_system" if event.key() == Qt.Key.Key_PageUp else "next_system")  # the bumpers, as keys
            return
        super().keyPressEvent(event)

    def current_system_id(self) -> str | None:
        return self.carousel.current_id()

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
        if view == VIEW_ALL:
            return self.library.games(None, search=search, sort=sort)
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
        self._update_empty_state(view, bool(items))

        played = sum(r["total_seconds"] for r in rows)
        noun = "game" if len(rows) == 1 else "games"
        sub = f"{len(rows)} {noun}"
        if played:
            sub += f"   ·   {fmt_duration(played)} played"
        self.banner_sub.setText(sub)
        self._on_game_changed()

    def _update_empty_state(self, view: str | None, has_games: bool) -> None:
        """An empty shelf says why, and offers the next step, instead of sitting blank."""
        self.coverflow.setVisible(has_games)
        self.empty.setVisible(not has_games)
        if has_games:
            return
        library_total = sum(self.library.summary()["systems"].values())
        search = self.search.text().strip()
        import_btn = ("Import ROMs…", self.import_roms, False)
        if library_total == 0:
            self.empty.show_message(
                "Welcome to Arcadia",
                "Your library is empty. Add your games, then install the emulators you need. The checklist walks you through it.",
                [("Get started", self.show_welcome, True), import_btn],
            )
        elif search:
            self.empty.show_message(f"Nothing matches “{search}”", "Try a different search, or clear it to see everything.", [("Clear search", self.search.clear, True)])
        elif view == VIEW_FAVORITES:
            self.empty.show_message("No favorites yet", "Select a game and press Ctrl+D (or the Favorite button) to keep it here.", [])
        elif view == VIEW_RECENT:
            self.empty.show_message("Nothing played yet", "Games you play show up here, most recent first.", [])
        else:
            name = self._system_name(view) if view else "this system"
            folder = self.config.rom_root_path
            self.empty.show_message(
                f"No {name} games yet",
                f"Put them in the “{self.config.system(view).folder}” folder inside {folder}, or import them from your downloads. Then they appear here by themselves.",
                [("Import ROMs…", self.import_roms, True), ("Open ROM folder", lambda: self._open_rom_folder(view), False)],
            )

    def _open_rom_folder(self, view: str) -> None:
        folder = self.config.rom_root_path / self.config.system(view).folder
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

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
        if self._sync_task is not None:
            self.toast.show_message("Syncing your saves first: try again in a moment.")
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
            self._auto_sync()  # the game has closed, so its saves are complete

    def _auto_sync(self) -> None:
        """Sync saves in the background: at startup and after each game. Quiet unless something happens."""
        c = self.config
        if self._closed or not c.auto_sync or self._sync_task is not None or self.process is not None:
            return
        if not (c.sync_remote.strip() or c.sync_dir.strip()):
            return
        if c.sync_remote.strip() and shutil.which("rclone") is None:
            return  # sync is on by default; until rclone is set up there is nothing to do
        snapshot = dataclasses.replace(c)  # the window may change settings while this runs
        self._sync_task = TaskClass(lambda report: savesync.run_sync(snapshot), self)
        self._sync_task.done.connect(self._on_auto_synced)
        self._sync_task.start()

    def _on_auto_synced(self, report, error) -> None:
        self._sync_task = None
        if self._closed:
            return
        if error is not None:
            self.toast.show_message(f"Save sync failed: {error}", 7000)
        elif report.errors:
            self.toast.show_message(f"Save sync: {len(report.errors)} file(s) couldn't be synced", 6000)
        elif report.conflicts:
            self.toast.show_message(f"Saves synced; {report.conflicts} changed on two devices (the older copy was kept)", 7000)
        elif report.changed:
            self.toast.show_message(f"Saves synced ({report.pushed} up, {report.pulled} down)")

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
        """Controller buttons. On the console screen the D-pad moves between tiles and A opens one;
        on the game screen it browses games, A launches, B goes back, and the bumpers change console."""
        if self._pad_in_dialog(name):  # a dialog is open: the controller drives it, not the window behind
            return
        if name == "favorite":
            if self.on_games_page():
                self.toggle_favorite()
            return
        if name in ("prev_system", "next_system"):
            self.carousel.rotate(-1 if name == "prev_system" else 1)
            return
        if name == "back":
            if self.on_games_page():
                self.show_consoles()
            return
        key = ACTION_KEYS.get(name)
        if key is None:
            return
        target = self.coverflow if self.on_games_page() and self.coverflow.isVisible() else self.carousel
        if not self.on_games_page() and name == "confirm":
            self.show_games()
            return
        if target is not QApplication.focusWidget():
            target.setFocus()
        if self.on_games_page() and name in ("up", "down"):
            return  # nothing above or below the shelf
        QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    def _pad_in_dialog(self, name: str) -> bool:
        """Controller input while a dialog (or a drop-down list) is open. Returns True if one was, and handled it.
        D-pad moves between controls, A presses the focused one, B closes, the bumpers change tab."""
        popup, modal = QApplication.activePopupWidget(), QApplication.activeModalWidget()
        target = popup or modal
        if target is None:
            return False
        focus = QApplication.focusWidget()
        if name == "back":
            QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        elif name == "confirm":
            if popup is not None:
                QApplication.sendEvent(popup, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
            elif isinstance(focus, QAbstractButton):
                focus.click()
            elif isinstance(focus, QComboBox):
                focus.showPopup()
            elif focus is None or focus is modal:
                default = next((b for b in modal.findChildren(QPushButton) if b.isDefault() and b.isEnabled()), None)
                if default is not None:
                    default.click()
            else:
                QApplication.sendEvent(focus, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        elif name in ("up", "down", "left", "right"):
            forward = name in ("down", "right")
            key = QKeyEvent(QEvent.Type.KeyPress, ACTION_KEYS[name], Qt.KeyboardModifier.NoModifier)
            if popup is not None:
                QApplication.sendEvent(popup, key)  # moves within the open drop-down list
            elif isinstance(focus, QAbstractItemView):  # a list or table: the arrows move its selection...
                before = focus.currentIndex()
                QApplication.sendEvent(focus, key)
                if focus.currentIndex() == before:  # ...and at its end they move on to the next control
                    modal.focusNextPrevChild(forward)
            elif isinstance(focus, (QAbstractSlider, QAbstractSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QTabBar)):
                QApplication.sendEvent(focus, key)
            else:  # buttons, checkboxes, drop-downs: step through the dialog's controls in order
                modal.focusNextPrevChild(forward)
        elif name in ("prev_system", "next_system"):
            tabs = modal.findChild(QTabWidget)
            if tabs is not None:
                step = -1 if name == "prev_system" else 1
                tabs.setCurrentIndex(max(0, min(tabs.count() - 1, tabs.currentIndex() + step)))
        return True

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

    def _plan_with_subfolders(self, folder: Path) -> Plan:
        """What's in a folder; if nothing is directly in it, also what's one folder down (ROMs are often in a subfolder)."""
        plan = build_plan(folder, self.config)
        if plan.items:
            return plan
        try:
            subs = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))[:200]
        except OSError:
            return plan
        for sub in subs:
            deeper = build_plan(sub, self.config)
            plan.items += deeper.items
            plan.waiting += deeper.waiting
            plan.ignored += deeper.ignored
        return plan

    def import_roms(self) -> None:
        """File > Import ROMs: review everything in the downloads folder (or any folder you pick), including sure
        matches. If nothing is found you can pick a different folder straight away."""
        inbox = self.config.inbox_path
        if inbox is None or not inbox.is_dir():
            start = str(inbox) if inbox else str(Path.home() / "Downloads")
            folder = choose_folder(self, "Choose your downloads folder", start)
            if not folder:
                return
            self.config.inbox_dir = folder
            self._save_config()
            self._setup_inbox()
            inbox = self.config.inbox_path
        folder = inbox
        while True:
            plan = self._plan_with_subfolders(folder)
            if plan.items:
                break
            extra = f" ({len(plan.waiting)} still downloading)" if plan.waiting else ""
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("Import ROMs")
            box.setText(f"No ROMs to import in {folder}{extra}.")
            box.setInformativeText("Choose a different folder to look in?")
            another = box.addButton("Choose another folder…", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not another:
                return
            chosen = choose_folder(self, "Look for ROMs in", str(folder))
            if not chosen:
                return
            folder = Path(chosen)
        self._asked.update(str(i.source) for i in plan.items)
        self._show_import_dialog(plan, folder)

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

    def show_welcome(self) -> None:
        """The first-run checklist (also File → Get started…)."""
        actions = {
            "folder": self._open_home_folder,
            "games": self.open_bring_in,
            "emulators": self.open_emulators,
            "bios": lambda: self.open_tools(0),
            "sync": lambda: self.open_tools(2),
        }
        WelcomeDialog(self.config, actions, lambda: self.library.summary()["systems"], parent=self).exec()

    def _open_home_folder(self) -> None:
        home = self.config.home_path or self.config.rom_root_path
        home.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(home)))

    def open_bring_in(self) -> None:
        dialog = BringInDialog(self.config, self.journal, parent=self)
        dialog.exec()
        if dialog.changed:
            self._home_changed()

    def _home_changed(self) -> None:
        """The library was brought into (or moved within) the Arcadia folder: use it."""
        self._save_config()
        self.config.ensure_layout()
        self.journal = Journal(self.config.journal_path)
        self._setup_inbox()
        self.rescan()
        if self.config.db_path != self._db_path:
            self.toast.show_message("Restart Arcadia to use your library in the new folder", 6000)

    def open_tools(self, tab: int = 0) -> None:
        """BIOS files, RetroArch settings and cores, Flatpak access, save sync."""
        if self._sync_task is not None:
            self.toast.show_message("Saves are syncing: open this again in a moment.")
            return
        ToolsDialog(self.config, parent=self, tab=tab).exec()
        self._save_config()

    def open_setup(self) -> None:
        """The overview of what's ready, plus bringing a library in and backing up."""
        counts = self.library.summary()["systems"]
        dialog = SetupDialog(self.config, self.config_path, self.journal, counts, parent=self)
        dialog.exec()
        if dialog.config_changed:  # the library was brought into the Arcadia folder
            self._home_changed()
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

    # ----- updating Arcadia itself -----

    def check_app_update(self, quiet: bool = True) -> None:
        """Ask GitHub whether there's a newer Arcadia. At startup (quiet) only a short note appears, and only if
        the user turned the check on; from the File menu a result is always shown."""
        if self._closed or getattr(self, "_app_update_task", None) is not None:
            return
        if quiet and not self.config.check_app_updates:
            return
        root = appupdate.app_root()
        branch = self.config.app_update_branch
        self._app_update_quiet = quiet
        self._app_update_task = DaemonTask(lambda: appupdate.check(root, branch), self)
        self._app_update_task.done.connect(self._on_app_update_checked)
        self._app_update_task.start()
        if not quiet:
            self.toast.show_message("Looking for a newer Arcadia…", 2500)

    def _on_app_update_checked(self, status, error) -> None:
        self._app_update_task = None
        if self._closed:
            return
        quiet = self._app_update_quiet
        if error is not None:
            if not quiet:
                QMessageBox.warning(self, "Arcadia updates", f"Couldn't check for updates: {error}")
            return
        if not status.available:
            if not quiet:
                QMessageBox.information(self, "Arcadia updates", f"Arcadia is up to date ({status.short}, branch {status.branch}).")
            return
        if quiet:
            self.toast.show_message("A newer Arcadia is available: File → Check for Arcadia updates…", 7000)
            return
        lines = "\n".join("• " + c for c in status.changes[:12]) or "(GitHub didn't list the changes)"
        extra = f"\n\n{status.note}" if status.note else ""
        box = QMessageBox(self)
        box.setWindowTitle("Arcadia update available")
        box.setText(f"A newer Arcadia is available on branch {status.branch} ({status.short}).")
        box.setInformativeText(f"What's new:\n{lines}{extra}\n\nYour games, saves and settings aren't touched.")
        update = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is update:
            self._install_app_update(status)

    def _install_app_update(self, status) -> None:
        root = appupdate.app_root()
        progress = QProgressDialog("Updating Arcadia…", "", 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowTitle("Updating Arcadia")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        task = Task(lambda report: appupdate.apply(root, status, progress=report), self)
        self._app_update_apply = task

        def finished(result, err) -> None:
            progress.close()
            self._app_update_apply = None
            if err is not None:
                QMessageBox.warning(self, "Update failed", f"Arcadia wasn't updated: {err}\n\nNothing was changed.")
                return
            note = "\n\nThis update changes Arcadia's requirements: run ./install.sh once after restarting." if result.requirements_changed else ""
            answer = QMessageBox.question(
                self, "Arcadia updated", f"Arcadia is now at {result.version}. Restart to use it?{note}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.restart_app()

        task.done.connect(finished)
        task.start()

    def restart_app(self) -> None:
        """Start a fresh Arcadia with the same options, then close this one."""
        import sys

        from PySide6.QtCore import QProcess

        QProcess.startDetached(sys.executable, ["-m", "arcadia", *sys.argv[1:]], str(appupdate.app_root()))
        self.close()

    def open_emulators(self) -> None:
        dialog = EmulatorsDialog(self.config, parent=self)
        dialog.exec()
        if dialog.changed:
            self.toast.show_message("Emulators updated")

    def closeEvent(self, event) -> None:
        self._closed = True
        if self._sync_task is not None:
            self._sync_task.wait(60_000)  # never close the window on a half-finished sync
        self.inbox_debounce.stop()
        self.inbox_poll.stop()
        self.controller.stop()
        if self.process is not None:
            self.process.terminate()
            self.process.waitForFinished(3000)
            self._end_session(record=True)
        self.library.close()
        super().closeEvent(event)
