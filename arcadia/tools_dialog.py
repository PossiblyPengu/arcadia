"""File > BIOS, emulator settings and sync: BIOS files, RetroArch settings and cores, Flatpak access, save sync."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from arcadia import bios, retroarch, savesync
from arcadia.config import Config
from arcadia.setup_dialog import _Busy
from arcadia.updates import flatpaks_in_use, installed_flatpaks

GOOD, WARN, DIM = QColor("#6fcf97"), QColor("#f2a33a"), QColor(236, 238, 244, 130)


def _table(headers: list[str], stretch: int) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setWordWrap(True)
    header = table.horizontalHeader()
    for i in range(len(headers)):
        header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i == stretch else QHeaderView.ResizeMode.ResizeToContents)
    return table


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: rgba(236, 238, 244, 60%);")
    return label


class ToolsDialog(QDialog, _Busy):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._task = None
        self.setWindowTitle("BIOS, emulator settings and sync")
        self.resize(900, 640)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_bios(), "BIOS files")
        self.tabs.addTab(self._build_retroarch(), "RetroArch and Flatpak")
        self.tabs.addTab(self._build_sync(), "Save sync")

        self.status = QLabel("")
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(self.buttons)
        self.refresh_bios()
        self.refresh_cores()

    # ----- BIOS -----

    def _build_bios(self) -> QWidget:
        page = QWidget()
        self.bios_summary = QLabel("")
        self.bios_summary.setWordWrap(True)
        self.bios_table = _table(["System", "File", "Status", "Notes"], 3)
        open_btn = QPushButton("Open the bios folder")
        open_btn.clicked.connect(self.open_bios_folder)
        again = QPushButton("Check again")
        again.clicked.connect(self.refresh_bios)
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addWidget(again)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(self.bios_summary)
        layout.addWidget(self.bios_table, 1)
        layout.addLayout(row)
        layout.addWidget(
            _note(
                "Arcadia can't supply BIOS files; put dumps from your own consoles in this folder. It only checks that a file "
                "with the right name is there, not that it's a good dump. RetroArch is pointed at this folder automatically "
                "(see the next tab). Standalone emulators keep their own BIOS folder, so copy the file there too."
            )
        )
        return page

    def refresh_bios(self) -> None:
        rows = bios.check_bios(self.config)
        self.bios_summary.setText(f"{bios.summarize(rows)}  Folder: {self.config.bios_path}")
        self.bios_table.setRowCount(0)
        for system in rows:
            for status in system.needs:
                r = self.bios_table.rowCount()
                self.bios_table.insertRow(r)
                if status.ok:
                    state, color = f"✓  found ({status.found})", GOOD
                elif status.need.required:
                    state, color = "✗  missing", WARN
                else:
                    state, color = "–  not needed", DIM
                names = ", ".join(status.need.names[:3]) + (" …" if len(status.need.names) > 3 else "")
                cells = [system.name, status.need.label, state, "  ".join(x for x in (status.need.note, f"looks for: {names}" if not status.ok else "") if x)]
                for c, text in enumerate(cells):
                    self.bios_table.setItem(r, c, QTableWidgetItem(text))
                self.bios_table.item(r, 2).setForeground(color)
        self.bios_table.resizeRowsToContents()

    def open_bios_folder(self) -> None:
        self.config.bios_path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.bios_path)))

    # ----- RetroArch and Flatpak -----

    def _build_retroarch(self) -> QWidget:
        page = QWidget()
        c = self.config
        self.manage_box = QCheckBox("Apply Arcadia's settings when starting RetroArch (also points it at the bios folder)")
        self.manage_box.setChecked(c.manage_retroarch)
        self.fullscreen_box = QCheckBox("Start games full screen")
        self.fullscreen_box.setChecked(c.ra_fullscreen)
        self.vsync_box = QCheckBox("Wait for the screen (vsync)")
        self.vsync_box.setChecked(c.ra_vsync)
        self.integer_box = QCheckBox("Integer scaling (sharp pixels; adds borders)")
        self.integer_box.setChecked(c.ra_integer_scale)
        self.autosave_box = QCheckBox("Save a state when a game closes and load it when it starts")
        self.autosave_box.setChecked(c.ra_auto_save_state)
        self.saves_box = QCheckBox("Keep in-game saves in Arcadia's saves folder (so they're backed up and synced)")
        self.saves_box.setChecked(c.ra_saves_in_home)
        self.saves_hint = _note("Turning this on starts RetroArch with an empty save folder; saves you already have stay where they are and aren't moved.")

        self.cores_table = _table(["Core", "Used by", "Status"], 1)
        self.cores_btn = QPushButton("Install missing cores / update all")
        self.cores_btn.clicked.connect(self.update_cores)
        self.grant_btn = QPushButton("Let Flatpak emulators use the Arcadia folder…")
        self.grant_btn.clicked.connect(self.grant_access)

        layout = QVBoxLayout(page)
        for box in (self.manage_box, self.fullscreen_box, self.vsync_box, self.integer_box, self.autosave_box, self.saves_box):
            layout.addWidget(box)
        layout.addWidget(self.saves_hint)
        layout.addWidget(QLabel("RetroArch cores"))
        layout.addWidget(self.cores_table, 1)
        row = QHBoxLayout()
        row.addWidget(self.cores_btn)
        row.addWidget(self.grant_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(
            _note(
                "Cores are downloaded from libretro's build server (the nightly builds, as RetroArch's own Core Downloader does). "
                "Flatpak emulators can only see folders they've been given: the second button grants each one you use the Arcadia "
                "folder with `flatpak override --user` (undo with `flatpak override --user --reset <app>`)."
            )
        )
        return page

    def refresh_cores(self) -> None:
        self.core_rows = retroarch.cores_in_use(self.config)
        self.cores_table.setRowCount(0)
        for row in self.core_rows:
            r = self.cores_table.rowCount()
            self.cores_table.insertRow(r)
            for c, text in enumerate([row.name, ", ".join(row.systems), "✓  installed" if row.installed else "✗  not installed"]):
                self.cores_table.setItem(r, c, QTableWidgetItem(text))
            self.cores_table.item(r, 2).setForeground(GOOD if row.installed else WARN)
        self.cores_table.resizeRowsToContents()
        self.cores_btn.setEnabled(bool(self.core_rows) and self._task is None)

    def update_cores(self) -> None:
        rows = list(self.core_rows)
        self._run(lambda report: retroarch.update_cores(rows, progress=report), self._on_cores_done, "Downloading cores…")

    def _on_cores_done(self, outcomes, error) -> None:
        self.refresh_cores()
        if error is not None:
            QMessageBox.warning(self, "Cores", f"Updating the cores failed: {error}")
            return
        failed = [o for o in outcomes if not o.ok]
        text = f"{len(outcomes) - len(failed)} of {len(outcomes)} cores are up to date."
        if failed:
            text += "\n\nCouldn't get:\n" + "\n".join(f"• {o.name}: {o.error}" for o in failed)
        (QMessageBox.warning if failed else QMessageBox.information)(self, "Cores", text)

    def grant_access(self) -> None:
        paths = retroarch.access_paths(self.config)
        installed = installed_flatpaks()
        if installed is None:
            QMessageBox.information(self, "Flatpak", "Flatpak isn't available on this machine, so there is nothing to grant.")
            return
        apps = list(flatpaks_in_use(self.config, installed))
        if retroarch.RETROARCH_APP in installed and retroarch.RETROARCH_APP not in apps:
            apps.append(retroarch.RETROARCH_APP)
        if not apps or not paths:
            QMessageBox.information(self, "Flatpak", "No Flatpak emulators from your systems are installed, so there is nothing to grant.")
            return
        commands = retroarch.shell_form(retroarch.grant_commands(apps, paths))
        answer = QMessageBox.question(
            self,
            "Let Flatpak emulators use these folders?",
            f"This will run, for your user only:\n\n{commands}\n\nContinue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda report: retroarch.grant_access(apps, paths), lambda v, e: self._on_granted(v, e, apps), "Granting access…")

    def _on_granted(self, result, error, apps) -> None:
        if error is not None or not result.ok:
            QMessageBox.warning(self, "Flatpak", f"Couldn't grant access: {error or result.output}")
        else:
            QMessageBox.information(self, "Flatpak", f"Done for {len(apps)} app{'s' if len(apps) != 1 else ''}. Restart any emulator that was open.")

    # ----- Save sync -----

    def _build_sync(self) -> QWidget:
        page = QWidget()
        self.sync_edit = QLineEdit(self.config.sync_dir)
        self.sync_edit.setPlaceholderText("A folder that Syncthing, a cloud drive or an SD card keeps in step")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_sync)
        self.remote_edit = QLineEdit(self.config.sync_remote)
        self.remote_edit.setPlaceholderText("Or an rclone remote and folder, e.g. gdrive:Arcadia (Google Drive)")
        detect = QPushButton("Find remotes")
        detect.clicked.connect(self.find_remotes)
        self.remote_hint = _note("")
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.clicked.connect(lambda: self.run_sync(dry_run=True))
        self.sync_btn = QPushButton("Sync now")
        self.sync_btn.setObjectName("primary")
        self.sync_btn.clicked.connect(lambda: self.run_sync(dry_run=False))
        self.sync_result = QLabel("")
        self.sync_result.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(self.sync_edit, 1)
        top.addWidget(browse)
        remote_row = QHBoxLayout()
        remote_row.addWidget(self.remote_edit, 1)
        remote_row.addWidget(detect)
        row = QHBoxLayout()
        row.addWidget(self.preview_btn)
        row.addWidget(self.sync_btn)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Sync folder"))
        layout.addLayout(top)
        layout.addWidget(QLabel("Google Drive or another cloud, through rclone (used instead of the folder when filled in)"))
        layout.addLayout(remote_row)
        layout.addWidget(self.remote_hint)
        layout.addLayout(row)
        layout.addWidget(self.sync_result)
        layout.addStretch(1)
        layout.addWidget(
            _note(
                "Arcadia has no online login of its own: with a folder it keeps that folder and your saves and save states matching, "
                "and whatever syncs the folder (Syncthing, a cloud drive) does the rest. A save that changed on only one device "
                "is copied to the other. If it changed on both, the newer one wins and the other copy is kept in a _conflicts "
                "folder. Nothing is ever deleted, and anything overwritten here is first copied to backups/savesync. Run it "
                "after playing and before playing on another device; not while an emulator is open."
            )
        )
        return page

    def browse_sync(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose the sync folder", self.sync_edit.text() or str(Path.home()))
        if chosen:
            self.sync_edit.setText(chosen)

    def find_remotes(self) -> None:
        try:
            remotes = savesync.rclone_remotes()
        except savesync.SyncError as exc:
            self.remote_hint.setText(f"✗  {exc}")
            return
        drives = [name for name, kind in remotes if kind == "drive"]
        if not remotes:
            self.remote_hint.setText("rclone has no remotes yet. Run `rclone config` and add one of type “drive” (Google Drive).")
        else:
            self.remote_hint.setText("Remotes found: " + ", ".join(f"{n}{'  (Google Drive)' if n in drives else ''}" for n, _k in remotes) + ". Type one with a folder, e.g. " + (drives or [remotes[0][0]])[0] + "Arcadia")
            if drives and not self.remote_edit.text().strip():
                self.remote_edit.setText(drives[0] + "Arcadia")

    def run_sync(self, dry_run: bool) -> None:
        self.config.sync_dir = self.sync_edit.text().strip()
        self.config.sync_remote = self.remote_edit.text().strip()
        self.sync_result.setText("")
        config = self.config
        self._run(lambda report: savesync.run_sync(config, dry_run=dry_run, progress=report), lambda v, e: self._on_synced(v, e, dry_run), "Comparing saves…")

    def _on_synced(self, report, error, dry_run: bool) -> None:
        if error is not None:
            self.sync_result.setText(f"✗  {error}")
            return
        verb = "Would copy" if dry_run else "Copied"
        text = f"{verb} {report.pushed} to the sync folder and {report.pulled} to this device; {report.unchanged} already matched."
        if report.conflicts:
            text += f"\n{report.conflicts} changed on both sides: the newer copy {'would win' if dry_run else 'won'} and the other was kept."
        if report.errors:
            text += "\nCouldn't sync:\n" + "\n".join(f"• {e}" for e in report.errors[:8])
        self.sync_result.setText(text)

    # ----- plumbing -----

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.bios_table.resizeRowsToContents()  # wrapped text can only be measured once the widths are known
        self.cores_table.resizeRowsToContents()

    def _busy_changed(self) -> None:
        busy = self._task is not None
        for button in (self.cores_btn, self.grant_btn, self.preview_btn, self.sync_btn):
            button.setEnabled(not busy)
        if not busy:
            self.cores_btn.setEnabled(bool(self.core_rows))

    def reject(self) -> None:
        if self._task is not None:
            return  # let the running job finish first
        self.done(QDialog.DialogCode.Rejected)

    def done(self, result) -> None:
        c = self.config
        c.manage_retroarch = self.manage_box.isChecked()
        c.ra_fullscreen = self.fullscreen_box.isChecked()
        c.ra_vsync = self.vsync_box.isChecked()
        c.ra_integer_scale = self.integer_box.isChecked()
        c.ra_auto_save_state = self.autosave_box.isChecked()
        c.ra_saves_in_home = self.saves_box.isChecked()
        c.sync_dir = self.sync_edit.text().strip()
        c.sync_remote = self.remote_edit.text().strip()
        super().done(result)
