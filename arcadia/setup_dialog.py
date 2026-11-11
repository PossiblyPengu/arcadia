"""File > Arcadia folder & setup: see what's ready, bring an existing library in, back up and restore."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcadia.backup import BackupError, create_backup, inspect_backup, restore_backup
from arcadia.config import DEFAULT_HOME, Config
from arcadia.consolidate import (
    BringInResult,
    ConsolidateError,
    SourceFolder,
    adopt_home,
    bring_in,
    config_for_home,
    default_downloads_dir,
    migrate_data,
    scan_source,
)
from arcadia.emulators import Installer
from arcadia.emulators_dialog import EmulatorsDialog
from arcadia.import_dialog import ImportDialog
from arcadia.setup_status import NONE, OK, PROBLEM, flatpak_installed, folder_sizes, status_rows
from arcadia.sorter import Journal, Plan, PlanItem, apply_plan, default_selection, sweep
from arcadia.tasks import Task
from arcadia.util import fmt_size

TaskClass = Task  # tests swap this for a version that runs immediately

GOOD, WARN, DIM = QColor("#6fcf97"), QColor("#f2a33a"), QColor(236, 238, 244, 130)


class _Busy:
    """Run one background job at a time and keep the buttons honest while it runs."""

    def _run(self, fn, on_done, message: str) -> None:
        self.status.setText(message)
        task = TaskClass(fn, self)
        self._task = task
        task.progress.connect(self._on_progress)
        task.done.connect(lambda value, error: self._finish(on_done, value, error))
        self._busy_changed()
        task.start()

    def _finish(self, on_done, value, error) -> None:
        self._task = None
        self.status.setText("")
        self.bar.setVisible(False)
        self._busy_changed()
        on_done(value, error)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setVisible(True)
            self.bar.setRange(0, total)
            self.bar.setValue(done)

    def _busy_changed(self) -> None:  # overridden
        pass


# ----------------------------------------------------------------------------
# Bring an existing library in
# ----------------------------------------------------------------------------

class BringInDialog(QDialog, _Busy):
    """Brings what you already have into place: an existing ROM folder, and the ROMs sitting in your
    Downloads folder. When a library is being moved in, everything lands in the new Arcadia folder.
    When only Downloads is swept, ROMs go to the ROM folder you already use, so no second library appears."""

    def __init__(self, config: Config, journal: Journal, parent=None):
        super().__init__(parent)
        self.config = config
        self.journal = journal
        self.changed = False  # the configuration or the library changed: save it and rescan
        self.folders: list[SourceFolder] = []
        self.dl_plan: Plan | None = None
        self.dl_selection: list[PlanItem] = []
        self.dl_keep_both = False
        self._folder_error = ""  # why the ROM folder couldn't be used, if it couldn't
        self._had_source = False  # a ROM folder was looked at (as opposed to only Downloads)
        self._task = None
        self.setWindowTitle("Bring my ROMs in")
        self.resize(940, 800)

        intro = QLabel(
            "Pick your existing ROM folder (the one that holds nes/, psx/, snes/ and so on), your Downloads folder, "
            "or both. Arcadia works out which system each thing is for, shows you what it would do, and only "
            "then moves or copies it. Nothing is ever overwritten."
        )
        intro.setWordWrap(True)

        self.home_edit = QLineEdit(str(config.home_path or DEFAULT_HOME))
        home_browse = QPushButton("Browse…")
        home_browse.clicked.connect(lambda: self._browse(self.home_edit, "Arcadia folder"))
        self.source_edit = QLineEdit()
        current = config.rom_root_path
        if current.is_dir() and not (config.home_path and config.home_path in current.parents):
            self.source_edit.setText(str(current))
        self.source_edit.setPlaceholderText("Leave empty to only sweep Downloads")
        source_browse = QPushButton("Browse…")
        source_browse.clicked.connect(lambda: self._browse(self.source_edit, "Your existing ROM folder"))

        form = QFormLayout()
        form.addRow("Arcadia folder:", self._row(self.home_edit, home_browse))
        form.addRow("Your ROM folder:", self._row(self.source_edit, source_browse))

        self.mode = QComboBox()
        self.mode.addItem("Move: the games leave the old folder (you can undo this from the File menu)", "move")
        self.mode.addItem("Copy: keep the old folder as it is (needs twice the space; can't be undone)", "copy")
        self.data_box = QCheckBox("Also bring my library (favorites, playtime), covers and save-state snapshots")
        self.data_box.setChecked(True)
        self.data_box.setToolTip("These are copied, never deleted from where they are now.")

        downloads = default_downloads_dir()
        self.dl_box = QCheckBox("Also sweep my Downloads folder for ROMs")
        self.dl_box.setChecked(downloads.is_dir())
        self.dl_box.setToolTip("Looks in this folder and the folders inside it (two levels). Only files Arcadia recognises as ROMs are listed.")
        self.dl_edit = QLineEdit(str(downloads))
        dl_browse = QPushButton("Browse…")
        dl_browse.clicked.connect(lambda: self._browse(self.dl_edit, "Your Downloads folder"))
        self.keep_box = QCheckBox("Keep watching this folder and sort new ROMs into the library automatically")
        self.keep_box.setToolTip("Turns on the downloads sorting in Settings for this folder. Off unless you tick it.")

        self.scan_btn = QPushButton("Look")
        self.scan_btn.clicked.connect(self.scan)
        self.review_btn = QPushButton("Review the ROMs found in Downloads…")
        self.review_btn.setEnabled(False)
        self.review_btn.clicked.connect(self.review)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Bring in", "Folder", "Files", "Size", "Goes to"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 270)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setMinimumHeight(190)
        self.table.itemChanged.connect(lambda _i: self._update_summary())

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.dl_summary = QLabel("")
        self.dl_summary.setWordWrap(True)
        self.status = QLabel("")
        self.status.setStyleSheet("color: rgba(236, 238, 244, 65%);")
        self.bar = QProgressBar()
        self.bar.setVisible(False)

        self.start_btn = QPushButton("Bring it in")
        self.start_btn.setObjectName("primary")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.mode)
        layout.addWidget(self.data_box)
        layout.addWidget(self.dl_box)
        layout.addWidget(self._row(self.dl_edit, dl_browse))
        layout.addWidget(self.keep_box)
        layout.addWidget(self.scan_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary)
        layout.addWidget(self.dl_summary)
        layout.addWidget(self.review_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(box)

    @staticmethod
    def _row(edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        row.addWidget(button)
        return widget

    def _browse(self, edit: QLineEdit, title: str) -> None:
        folder = QFileDialog.getExistingDirectory(self, title, edit.text() or str(Path.home()))
        if folder:
            edit.setText(folder)

    def _home(self) -> Path:
        return Path(self.home_edit.text().strip() or str(DEFAULT_HOME)).expanduser()

    def _dest_root(self) -> Path:
        return Config.new_install(self._home()).rom_root_path

    def _downloads(self) -> Path | None:
        text = self.dl_edit.text().strip()
        return Path(text).expanduser() if self.dl_box.isChecked() and text else None

    def _target(self, migrating: bool) -> Config:
        """Where swept ROMs go: the new Arcadia folder while a library is moving in, otherwise the ROM
        folder already in use (so sweeping Downloads alone never starts a second library)."""
        return config_for_home(self.config, self._home()) if migrating else self.config

    def _busy_changed(self) -> None:
        idle = self._task is None
        self.scan_btn.setEnabled(idle)
        self.review_btn.setEnabled(idle and bool(self.dl_plan and self.dl_plan.items))
        self.start_btn.setEnabled(idle and self._anything_chosen())

    # ----- looking -----

    def scan(self) -> None:
        source_text = self.source_edit.text().strip()
        downloads = self._downloads()
        if not source_text and downloads is None:
            self.summary.setText("Choose your ROM folder, tick the Downloads sweep, or both.")
            return
        dest = self._dest_root()
        source = Path(source_text).expanduser() if source_text else None

        def work(report):
            folders: list[SourceFolder] = []
            folder_error = ""
            if source is not None:
                try:
                    folders = scan_source(source, self.config, dest)
                except ConsolidateError as exc:
                    folder_error = str(exc)
            plan = None
            if downloads is not None:
                migrating = any(f.system_id for f in folders)
                target = self._target(migrating)
                leave_alone = [p for p in (self._home(), target.rom_root_path, source) if p is not None]
                plan = sweep(downloads, target, exclude=leave_alone)
            return folders, folder_error, plan

        self._run(work, self._on_scanned, "Looking… (this can take a while for a large library)")

    def _on_scanned(self, value, error) -> None:
        self.table.setRowCount(0)
        self.folders, self.dl_plan, self.dl_selection = [], None, []
        if error is not None:
            self.summary.setText(f"Couldn't look: {error}")
            self.dl_summary.setText("")
            self._update_summary()
            return
        folders, folder_error, plan = value
        self.folders = folders
        self.dl_plan = plan
        self.dl_selection = default_selection(plan.items) if plan else []
        self.table.blockSignals(True)
        self.table.setRowCount(len(folders))
        for row, folder in enumerate(folders):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked if folder.system_id else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            name = QTableWidgetItem(folder.path.name)
            name.setToolTip(str(folder.path))
            self.table.setItem(row, 1, name)
            self.table.setItem(row, 2, QTableWidgetItem(f"{folder.files:,}"))
            self.table.setItem(row, 3, QTableWidgetItem(fmt_size(folder.bytes)))
            combo = QComboBox()
            combo.addItem("— leave alone —", None)
            for system in self.config.systems:
                combo.addItem(system.name, system.id)
            combo.setCurrentIndex(max(0, combo.findData(folder.system_id)))
            combo.setStyleSheet("padding: 3px 12px; border-radius: 12px;")
            combo.currentIndexChanged.connect(lambda _i, r=row: self._assigned(r))
            self.table.setCellWidget(row, 4, combo)
        self.table.blockSignals(False)
        self._folder_error = folder_error
        self._had_source = bool(self.source_edit.text().strip())
        self._update_summary()

    def _assigned(self, row: int) -> None:
        """Choosing a system for a folder is how the user says 'yes, this one'."""
        combo = self.table.cellWidget(row, 4)
        self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if combo.currentData() else Qt.CheckState.Unchecked)
        self._update_summary()

    def chosen(self) -> list[tuple[SourceFolder, str | None]]:
        picked = []
        for row, folder in enumerate(self.folders):
            system_id = self.table.cellWidget(row, 4).currentData()
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked and system_id:
                picked.append((folder, system_id))
        return picked

    def _anything_chosen(self) -> bool:
        return bool(self.chosen()) or bool(self.dl_selection)

    def _update_summary(self) -> None:
        picked = self.chosen()
        parts = []
        if self._folder_error:
            parts.append(f"Can't use that ROM folder: {self._folder_error}.")
        elif self._had_source and not self.folders:
            parts.append("That folder has no subfolders. Point this at the folder that holds nes/, psx/, snes/…")
        elif self.folders:
            files = sum(f.files for f, _ in picked)
            size = sum(f.bytes for f, _ in picked)
            left = len(self.folders) - len(picked)
            text = f"{len(picked)} folder{'s' if len(picked) != 1 else ''} will be brought in ({files:,} files, {fmt_size(size)})."
            if left:
                text += f" {left} left alone."
            parts.append(text)
        self.summary.setText(" ".join(parts))

        plan = self.dl_plan
        if plan is None:
            self.dl_summary.setText("")
        elif not plan.items:
            extra = f" ({len(plan.waiting)} still downloading)" if plan.waiting else ""
            self.dl_summary.setText(f"No ROMs found in Downloads{extra}.")
        else:
            asking = sum(1 for i in plan.items if i.confidence.value == "unsure")
            text = f"{len(plan.items)} ROM{'s' if len(plan.items) != 1 else ''} found in Downloads; {len(self.dl_selection)} will be sorted in."
            if asking:
                text += f" {asking} need{'s' if asking == 1 else ''} your decision: use Review to look at them."
            if not picked:
                text += f" They go to your current ROM folder, {self.config.rom_root_path}."
            self.dl_summary.setText(text)
        self.review_btn.setEnabled(self._task is None and bool(plan and plan.items))
        self.start_btn.setEnabled(self._task is None and self._anything_chosen())

    def review(self) -> None:
        """Look at, tick and re-assign the ROMs found in Downloads, using the same window as importing them."""
        if not self.dl_plan or not self.dl_plan.items:
            return
        target = self._target(bool(self.chosen()))
        for item in self.dl_plan.items:
            item.retarget(target, item.system_id)  # the destination may have changed since the scan
        dialog = ImportDialog(target, self.dl_plan, self, inbox_label=str(self._downloads() or ""), verb="Include", base=self._downloads())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.dl_selection = dialog.selected_items()
            self.dl_keep_both = dialog.keep_both()
            self._update_summary()

    # ----- doing -----

    def start(self) -> None:
        picked = self.chosen()
        sweep_items = list(self.dl_selection)
        if not picked and not sweep_items:
            return
        migrating = bool(picked)
        mode = self.mode.currentData()
        home = self._home()
        target = self._target(migrating)
        for item in sweep_items:
            item.retarget(target, item.system_id)  # the Arcadia folder may have been edited since the scan

        lines = []
        if picked:
            lines.append(f"{'Move' if mode == 'move' else 'Copy'} {len(picked)} folder(s) into {home / 'roms'}")
        if sweep_items:
            lines.append(f"Sort {len(sweep_items)} ROM{'s' if len(sweep_items) != 1 else ''} from Downloads into {target.rom_root_path}")
        answer = QMessageBox.question(
            self,
            "Bring your ROMs in",
            "\n".join(lines) + "?\n\n"
            + ("Moves can be undone from File → Undo last import. " if mode == "move" or sweep_items else "")
            + ("Copies leave the originals where they are." if picked and mode == "copy" else ""),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with_data = self.data_box.isChecked() and migrating
        keep_both = self.dl_keep_both
        downloads = self._downloads()

        def work(report):
            result = BringInResult()
            if migrating:
                Config.new_install(home).ensure_layout()
                result = bring_in(picked, self.config, target.rom_root_path, mode, self.journal, lambda d, t, n: report(d, t))
            swept = apply_plan(sweep_items, self.journal, keep_both=keep_both) if sweep_items else None
            notes = migrate_data(self.config, home) if with_data else []
            return result, swept, notes, home

        self._run(work, lambda value, error: self._on_done(value, error, with_data, migrating, downloads), "Bringing your ROMs in…")

    def _on_done(self, value, error, with_data: bool, migrating: bool, downloads: Path | None) -> None:
        if error is not None:
            QMessageBox.warning(self, "Couldn't bring your ROMs in", f"{error}\n\nWhat was already moved is kept, and you can run this again.")
            return
        result, swept, notes, home = value
        problems = [(p, why) for p, why in result.skipped if "already exists" not in why]
        brought = result.moved + result.copied
        # Only switch to the new folder if everything that could be brought in was; otherwise the old
        # library would silently lose the games that didn't make it.
        switched = migrating and not problems and (brought > 0 or bool(result.skipped))
        if switched:
            adopt_home(self.config, home, roms=True, data=with_data)

        lines = []
        if migrating:
            lines.append(f"{brought} item(s) {'moved' if result.moved else 'copied'} from your ROM folder ({fmt_size(result.bytes)}).")
        lines += notes
        conflicts = len(result.skipped) - len(problems)
        if conflicts:
            lines.append(f"{conflicts} already existed in the Arcadia folder and were left alone.")
        for path, why in problems[:8]:
            lines.append(f"Couldn't bring in {path.name}: {why}.")

        swept_count = len(swept.moved) if swept else 0
        if swept is not None:
            lines.append(f"{swept_count} ROM{'s' if swept_count != 1 else ''} from Downloads sorted into your library.")
            for item, why in swept.skipped[:8]:
                lines.append(f"Left in Downloads: {item.label}: {why}.")
        if self.keep_box.isChecked() and downloads is not None and not self.config.inbox_dir.strip():
            self.config.inbox_dir = str(downloads)
            lines.append(f"Arcadia will keep watching {downloads} and sort new ROMs automatically.")

        if problems:
            lines.append("Arcadia hasn't switched to the new folder yet, so nothing is lost. Fix the above and run this again.")
        elif switched:
            lines.append("Arcadia now uses the Arcadia folder. Restart Arcadia to finish switching over.")
        self.changed = switched or swept_count > 0 or self.keep_box.isChecked() and downloads is not None
        done = switched or (not migrating and swept is not None)
        QMessageBox.information(self, "Done" if done and not problems else "Not finished", "\n".join(lines))
        if done and not problems:
            self.accept()


# ----------------------------------------------------------------------------
# Back up and restore
# ----------------------------------------------------------------------------

class BackupDialog(QDialog, _Busy):
    def __init__(self, config: Config, config_path: Path, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.restored = False
        self._task = None
        self.setWindowTitle("Back up and restore")
        self.resize(780, 520)

        intro = QLabel(
            f"A backup holds your saves, settings, library (favorites and playtime) and save-state snapshots as one "
            f"zip in <b>{config.backups_path}</b>. It doesn't include ROMs or the emulator programs. Flatpak "
            "emulators keep their saves under <code>~/.var/app</code>, which Arcadia doesn't manage, so those "
            "aren't in it."
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Backup", "Made", "Size"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._busy_changed)

        self.media_box = QCheckBox("Include covers and metadata (can be large)")
        self.backup_btn = QPushButton("Back up now")
        self.backup_btn.setObjectName("primary")
        self.backup_btn.clicked.connect(self.back_up)
        self.restore_btn = QPushButton("Restore selected…")
        self.restore_btn.clicked.connect(self.restore_selected)
        self.file_btn = QPushButton("Restore from a file…")
        self.file_btn.clicked.connect(self.restore_from_file)
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.backups_path))))

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: rgba(236, 238, 244, 65%);")
        self.bar = QProgressBar()
        self.bar.setVisible(False)

        buttons = QHBoxLayout()
        for b in (self.backup_btn, self.restore_btn, self.file_btn, self.open_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.media_box)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.paths = sorted(self.config.backups_path.glob("Arcadia-backup-*.zip"), reverse=True) if self.config.backups_path.is_dir() else []
        self.table.setRowCount(len(self.paths))
        for row, path in enumerate(self.paths):
            made = ""
            try:
                made = inspect_backup(path).created.replace("T", " ")[:16]
            except BackupError:
                made = "unreadable"
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(made))
            self.table.setItem(row, 2, QTableWidgetItem(fmt_size(path.stat().st_size)))
        if self.paths:
            self.table.selectRow(0)
        self._busy_changed()

    def _busy_changed(self) -> None:
        idle = self._task is None
        self.backup_btn.setEnabled(idle)
        self.restore_btn.setEnabled(idle and bool(self.table.selectionModel() and self.table.selectionModel().selectedRows()))
        self.file_btn.setEnabled(idle)

    # ----- back up -----

    def back_up(self) -> None:
        include_media = self.media_box.isChecked()
        self._run(
            lambda report: create_backup(self.config, self.config_path, include_media=include_media, progress=report),
            self._on_backed_up,
            "Backing up…",
        )

    def _on_backed_up(self, result, error) -> None:
        if error is not None:
            QMessageBox.warning(self, "Backup", f"The backup wasn't made: {error}")
            return
        self.refresh()
        self.status.setText(f"Backed up {result.files} files ({fmt_size(result.bytes)}) to {result.path.name}.")

    # ----- restore -----

    def restore_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._restore(self.paths[rows[0].row()])

    def restore_from_file(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Restore from a backup", str(self.config.backups_path), "Arcadia backups (*.zip)")
        if name:
            self._restore(Path(name))

    def _restore(self, path: Path) -> None:
        try:
            info = inspect_backup(path)
        except BackupError as exc:
            QMessageBox.warning(self, "Restore", str(exc))
            return
        parts = [f"{count} {area}" for area, count in info.areas.items() if count]
        answer = QMessageBox.question(
            self,
            "Restore this backup?",
            f"{path.name}\nMade {info.created.replace('T', ' ')[:16]}\n\nIt contains: {', '.join(parts)}.\n\n"
            "Restoring replaces your current copies of these. Whatever it replaces is kept in "
            f"{self.config.backups_path / 'before-restore-…'}, nothing is deleted, and if the restore fails "
            "everything is put back.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda report: restore_backup(self.config, self.config_path, path, progress=report),
            self._on_restored,
            "Restoring…",
        )

    def _on_restored(self, result, error) -> None:
        if error is not None:
            QMessageBox.warning(self, "Restore", f"Nothing was changed: {error}")
            return
        self.restored = True
        self.refresh()
        where = f" The old versions are in {result.replaced_to.name}." if result.replaced_to else ""
        QMessageBox.information(
            self,
            "Restored",
            f"Restored {result.files} files.{where}\n\nRestart Arcadia to use the restored settings.",
        )


# ----------------------------------------------------------------------------
# The hub
# ----------------------------------------------------------------------------

class SetupDialog(QDialog, _Busy):
    def __init__(
        self,
        config: Config,
        config_path: Path,
        journal: Journal,
        game_counts: dict[str, int],
        installer: Installer | None = None,
        flatpak_check=flatpak_installed,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.journal = journal
        self.game_counts = game_counts
        self.installer = installer or Installer(config.emulators_path)
        self.flatpak_check = flatpak_check
        self.config_changed = False  # the Arcadia folder was adopted
        self.restored = False
        self.emulators_changed = False
        self._task = None
        self.setWindowTitle("Arcadia folder and setup")
        self.resize(1000, 640)

        self.where = QLabel()
        self.where.setTextFormat(Qt.TextFormat.RichText)
        self.where.setWordWrap(True)
        self.sizes = QLabel("")
        self.sizes.setStyleSheet("color: rgba(236, 238, 244, 65%);")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["System", "Games", "Launches with", "Ready?", "What to do"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setWordWrap(True)  # the advice is the point of this table: never cut it off
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)

        self.all_box = QCheckBox("Show every system, not just the ones with games")
        self.all_box.toggled.connect(lambda _c: self.refresh())

        self.status = QLabel("")
        self.status.setStyleSheet("color: rgba(236, 238, 244, 65%);")
        self.bar = QProgressBar()
        self.bar.setVisible(False)

        self.bring_btn = QPushButton("Bring my ROMs in…")
        self.bring_btn.clicked.connect(self.bring_in)
        self.backup_btn = QPushButton("Back up and restore…")
        self.backup_btn.clicked.connect(self.backups)
        self.emu_btn = QPushButton("Emulators…")
        self.emu_btn.clicked.connect(self.emulators)
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self.open_folder)
        self.refresh_btn = QPushButton("Check again")
        self.refresh_btn.clicked.connect(self.refresh)

        buttons = QHBoxLayout()
        for b in (self.bring_btn, self.backup_btn, self.emu_btn, self.open_btn, self.refresh_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)

        layout = QVBoxLayout(self)
        layout.addWidget(self.where)
        layout.addWidget(self.sizes)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.all_box)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addLayout(buttons)
        self._describe_home()
        self.refresh()

    def _describe_home(self) -> None:
        home = self.config.home_path
        if home is None:
            self.where.setText(
                "<b>Your setup is still spread across several places.</b> "
                "“Move my library in…” brings your ROMs and library into one Arcadia folder."
            )
        else:
            self.where.setText(f"Everything lives in <b>{home}</b>.")
        self.open_btn.setEnabled(home is not None)

    def _busy_changed(self) -> None:
        idle = self._task is None
        for b in (self.bring_btn, self.backup_btn, self.emu_btn, self.refresh_btn):
            b.setEnabled(idle)

    # ----- the overview -----

    def refresh(self) -> None:
        only = not self.all_box.isChecked()

        def work(report):
            rows = status_rows(self.config, self.game_counts, self.installer, self.flatpak_check, only_with_games=only)
            return rows, folder_sizes(self.config)

        self._run(work, self._on_checked, "Checking each system…")

    def _on_checked(self, value, error) -> None:
        if error is not None:
            self.status.setText(f"Couldn't check: {error}")
            return
        rows, sizes = value
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            state = row.launcher.state
            mark = {OK: "✓ Ready", PROBLEM: "⚠ Needs attention", NONE: "—"}[state]
            cells = [row.system.name, f"{row.games:,}", row.launcher.summary, mark, row.launcher.detail if state != OK else ""]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 3:
                    item.setForeground(GOOD if state == OK else WARN if state == PROBLEM else DIM)
                if row.launcher.detail:
                    item.setToolTip(row.launcher.detail)
                self.table.setItem(r, c, item)
        self._fit_rows()
        self.sizes.setText("   ·   ".join(f"{name} {fmt_size(size)}" for name, size in sizes.items()))
        ready = sum(1 for row in rows if row.launcher.state == OK)
        self.status.setText(f"{ready} of {len(rows)} system{'s' if len(rows) != 1 else ''} ready to play." if rows else "No games yet.")

    def _fit_rows(self) -> None:
        """Make each row tall enough for its wrapped advice, at the column widths in force right now."""
        self.table.resizeRowsToContents()
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, max(36, self.table.rowHeight(r)))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_rows()  # the columns only have their real widths once the window is laid out

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_rows()

    # ----- actions -----

    def bring_in(self) -> None:
        dialog = BringInDialog(self.config, self.journal, self)
        dialog.exec()
        if dialog.changed:
            self.config_changed = True
            self._describe_home()
            self.refresh()

    def backups(self) -> None:
        dialog = BackupDialog(self.config, self.config_path, self)
        dialog.exec()
        self.restored = self.restored or dialog.restored

    def emulators(self) -> None:
        dialog = EmulatorsDialog(self.config, self.installer, self)
        dialog.exec()
        self.emulators_changed = self.emulators_changed or dialog.changed
        self.refresh()

    def open_folder(self) -> None:
        if self.config.home_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.home_path)))
