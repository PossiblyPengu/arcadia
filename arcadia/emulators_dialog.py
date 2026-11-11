"""File > Emulators: install, update and remove emulators kept inside Arcadia's own folder."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from arcadia.config import Config
from arcadia.emulators import (
    CATALOG,
    Asset,
    Candidates,
    EmulatorError,
    EmulatorSpec,
    Installer,
    Release,
    candidate_assets,
)
from arcadia.tasks import Task
from arcadia.updates import (
    CHOOSE,
    CURRENT,
    READY,
    UpdateRow,
    apply_updates,
    flatpaks_in_use,
    installed_flatpaks,
    plan_updates,
    update_flatpaks,
)
from arcadia.util import fmt_size


TaskClass = Task  # tests swap this for a version that runs immediately


class InstallConfirmDialog(QDialog):
    """Shows exactly what is about to be downloaded, and lets the user pick when it's unclear."""

    def __init__(self, spec: EmulatorSpec, release: Release, found: Candidates, destination: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Install {spec.name}")
        self.resize(680, 300)
        self.found = found

        self.spec, self.release = spec, release
        self.source = QLabel()
        self.source.setTextFormat(Qt.TextFormat.RichText)
        self.source.setWordWrap(True)
        self.notes = QLabel(spec.notes)  # e.g. which of several builds suits which hardware
        self.notes.setWordWrap(True)
        self.notes.setVisible(bool(spec.notes))
        where = QLabel(f"It will be installed in <b>{destination}</b>, together with its own settings and saves.")
        where.setTextFormat(Qt.TextFormat.RichText)
        where.setWordWrap(True)

        self.combo = QComboBox()
        for asset in found.assets:
            self.combo.addItem(f"{asset.name}   ({fmt_size(asset.size)})" if asset.size else asset.name, asset)
        if found.preselected is not None:
            self.combo.setCurrentIndex(found.assets.index(found.preselected))
            self.hint = QLabel("This looks like the 64-bit Linux build.")
        else:
            self.hint = QLabel(
                "Arcadia couldn't tell which of these is the right one for this emulator, so it hasn't picked one. "
                "Choose the Linux 64-bit (x86-64) build."
            )
        self.hint.setWordWrap(True)
        self.checksum = QLabel()
        self.checksum.setWordWrap(True)
        self.combo.currentIndexChanged.connect(self._update_checksum)
        self._update_checksum()
        self._update_source()
        self.combo.currentIndexChanged.connect(self._update_source)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        install = QPushButton("Download and install")
        install.setObjectName("primary")
        self.buttons.addButton(install, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.source)
        layout.addWidget(where)
        layout.addWidget(self.combo)
        layout.addWidget(self.notes)
        layout.addWidget(self.hint)
        layout.addWidget(self.checksum)
        layout.addStretch(1)
        layout.addWidget(self.buttons)

    def chosen_asset(self) -> Asset:
        return self.combo.currentData()

    def _update_source(self) -> None:
        """Say where the chosen file really comes from: the host in its address, not an assumption."""
        asset = self.chosen_asset()
        host = urlparse(asset.url).hostname if asset is not None else ""
        self.source.setText(
            f"Release <b>{self.release.tag}</b> of <b>{self.spec.repo}</b>, downloaded from <b>{host}</b>."
        )

    def _update_checksum(self) -> None:
        asset = self.chosen_asset()
        if asset is not None and asset.digest:
            self.checksum.setText("GitHub publishes a SHA-256 checksum for this file. It will be checked, and thrown away if it doesn't match.")
        else:
            self.checksum.setText(
                "GitHub doesn't publish a checksum for this file, so the download can't be verified. "
                "Only continue if you trust this project's releases."
            )


class UpdateAllDialog(QDialog):
    """Everything an update would do, laid out before it happens: what's installed, what's new, which
    file it would download, and whether that file's checksum can be checked."""

    def __init__(self, rows: list[UpdateRow], flatpak_apps: list[str], parent=None):
        super().__init__(parent)
        self.rows = rows
        self.flatpak_apps = flatpak_apps
        self.setWindowTitle("Update emulators")
        self.resize(940, 520)

        intro = QLabel(
            "Each update downloads the file shown, keeps the build you installed before (so a Steam Deck build "
            "stays a Steam Deck build), and leaves the emulator's settings and saves alone. If an update fails, "
            "that emulator keeps working as it was."
        )
        intro.setWordWrap(True)

        self.table = QTableWidget(len(rows), 6)
        self.table.setHorizontalHeaderLabels(["Update", "Emulator", "Installed", "New", "Download", "Checksum"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        for col in (0, 1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.combos: dict[int, QComboBox] = {}
        for r, row in enumerate(rows):
            self._fill_row(r, row)
        self.table.itemChanged.connect(lambda _i: self._update_button())

        self.flatpak_box = QCheckBox(
            f"Also update the Flatpak emulators your systems use ({len(flatpak_apps)}): " + ", ".join(flatpak_apps)
        )
        self.flatpak_box.setChecked(bool(flatpak_apps))
        self.flatpak_box.setVisible(bool(flatpak_apps))
        self.flatpak_box.setToolTip("Runs `flatpak update` for just these apps, nothing else on your machine.")
        self.flatpak_box.toggled.connect(lambda _c: self._update_button())

        self.go = QPushButton("Update")
        self.go.setObjectName("primary")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(self.go, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.flatpak_box)
        layout.addWidget(buttons)
        self._update_button()

    def _fill_row(self, r: int, row: UpdateRow) -> None:
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(r, 0, check)
        for col, text in ((1, row.spec.name), (2, row.installed.version), (3, row.newer or "—")):
            self.table.setItem(r, col, QTableWidgetItem(text))
        if row.status == READY:
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(r, 4, QTableWidgetItem(row.asset.name))
            self.table.setItem(r, 5, QTableWidgetItem(self._checksum_text(row.asset)))
        elif row.status == CHOOSE:
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Unchecked)
            combo = QComboBox()
            combo.addItem("— choose which download —", None)
            for asset in row.choices:
                combo.addItem(asset.name, asset)
            combo.setStyleSheet("padding: 3px 12px; border-radius: 12px;")
            combo.setToolTip(row.message)
            combo.currentIndexChanged.connect(lambda _i, r=r: self._chose(r))
            self.combos[r] = combo
            self.table.setCellWidget(r, 4, combo)
            self.table.setItem(r, 5, QTableWidgetItem("—"))
        else:
            note = {CURRENT: "Up to date"}.get(row.status, row.message or row.status)
            self.table.setItem(r, 4, QTableWidgetItem(note))
            self.table.setItem(r, 5, QTableWidgetItem(""))
            for col in range(1, 6):
                item = self.table.item(r, col)
                if item is not None:
                    item.setForeground(QColor(236, 238, 244, 120))

    @staticmethod
    def _checksum_text(asset: Asset) -> str:
        return "will be checked" if asset.digest else "none published"

    def _chose(self, r: int) -> None:
        """Picking a download is the user saying yes to this one."""
        asset = self.combos[r].currentData()
        self.table.item(r, 5).setText(self._checksum_text(asset) if asset else "—")
        self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if asset else Qt.CheckState.Unchecked)
        self._update_button()

    def selection(self) -> list[tuple[UpdateRow, Asset]]:
        picked = []
        for r, row in enumerate(self.rows):
            item = self.table.item(r, 0)
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable) or item.checkState() != Qt.CheckState.Checked:
                continue
            asset = row.asset if row.status == READY else self.combos[r].currentData()
            if asset is not None:
                picked.append((row, asset))
        return picked

    def include_flatpak(self) -> bool:
        return bool(self.flatpak_apps) and self.flatpak_box.isChecked()

    def _update_button(self) -> None:
        n = len(self.selection())
        parts = []
        if n:
            parts.append(f"{n} emulator{'s' if n != 1 else ''}")
        if self.include_flatpak():
            parts.append("Flatpaks")
        self.go.setText("Update " + " and ".join(parts) if parts else "Nothing selected")
        self.go.setEnabled(bool(parts))


class EmulatorsDialog(QDialog):
    def __init__(self, config: Config, installer: Installer | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.installer = installer or Installer(config.emulators_path)
        self.changed = False
        self._latest: dict[str, str] = {}
        self._task = None
        self._progress: QProgressDialog | None = None
        self._progress_bytes = True  # progress is in bytes (one download) or in steps (a batch)
        self.flatpak_run = subprocess.run  # tests swap these
        self.flatpak_which = shutil.which
        self.setWindowTitle("Emulators")
        self.resize(900, 640)

        self.intro = QLabel(
            f"Emulators installed here live in <b>{config.emulators_path}</b>, one folder each, with their own "
            "settings and saves, instead of being spread around your system. Until one is installed here, "
            "its systems use the Flatpak, as before."
        )
        self.intro.setTextFormat(Qt.TextFormat.RichText)
        self.intro.setWordWrap(True)

        self.table = QTableWidget(len(CATALOG), 5)
        self.table.setHorizontalHeaderLabels(["Emulator", "Runs", "Installed here", "Latest", "Launches with"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.install_btn = QPushButton("Install…")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self.install_selected)
        self.remove_btn = QPushButton("Remove…")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self.open_folder)
        self.check_btn = QPushButton("Check for updates")
        self.check_btn.clicked.connect(self.check_updates)
        self.update_btn = QPushButton("Update all…")
        self.update_btn.clicked.connect(self.update_all)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: rgba(236, 238, 244, 65%);")
        note = QLabel(
            "Not listed: Dolphin, PPSSPP, Snes9x, MAME, openMSX, FS-UAE and RetroArch don't publish a portable "
            "Linux build Arcadia can install, and I couldn't confirm a download source for Ryujinx, so they "
            "stay on Flatpak."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: rgba(236, 238, 244, 45%);")

        buttons = QHBoxLayout()
        for button in (self.install_btn, self.remove_btn, self.open_btn, self.check_btn, self.update_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)

        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addWidget(note)
        layout.addLayout(buttons)

        self.specs = list(CATALOG.values())
        self.refresh()
        self.table.selectRow(0)

    # ----- table -----

    def refresh(self) -> None:
        installed = self.installer.installed()
        for row, spec in enumerate(self.specs):
            inst = installed.get(spec.id)
            if inst is None:
                here = "—"
            else:
                here = inst.version + ("  ✓ verified" if inst.verified else "  (no checksum)")
            latest = self._latest.get(spec.id, "")
            if inst is not None and latest and latest != inst.version and not latest.startswith("couldn't"):
                latest += "  — update available"
            uses = "this copy" if inst else ("Flatpak" if spec.flatpak else "—")
            systems = ", ".join(self._system_name(s) for s in spec.systems)
            for col, text in enumerate([spec.name, systems, here, latest, uses]):
                item = QTableWidgetItem(text)
                if col == 2 and inst is not None:
                    item.setToolTip(f"{inst.asset}\nsha256 {inst.sha256}\n{inst.source}")
                self.table.setItem(row, col, item)
        self._update_buttons()

    def _system_name(self, system_id: str) -> str:
        try:
            return self.config.system(system_id).name
        except KeyError:
            return system_id

    def selected_spec(self) -> EmulatorSpec | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.specs[rows[0].row()] if rows else None

    def _update_buttons(self) -> None:
        busy = self._task is not None
        spec = self.selected_spec()
        installed = spec is not None and self.installer.get(spec.id) is not None
        self.install_btn.setEnabled(spec is not None and not busy)
        self.install_btn.setText("Update…" if installed else "Install…")
        self.remove_btn.setEnabled(installed and not busy)
        self.open_btn.setEnabled(spec is not None and self.installer.folder(spec.id).exists())
        self.check_btn.setEnabled(not busy and bool(self.installer.installed()))
        self.update_btn.setEnabled(not busy)

    # ----- running things in the background -----

    def _run(self, fn, on_done, message: str) -> None:
        self.status.setText(message)
        task = TaskClass(fn, self)
        self._task = task
        task.progress.connect(self._on_progress)
        task.done.connect(lambda value, error: self._finish(on_done, value, error))
        self._update_buttons()
        task.start()

    def _finish(self, on_done, value, error) -> None:
        self._task = None
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self.status.setText("")
        self._update_buttons()
        on_done(value, error)

    def _cancellable(self, report):
        """The progress callback, but stopping the download as soon as Cancel is pressed."""
        cancel = self._cancel

        def checked(done: int, total: int) -> None:
            if cancel.is_set():
                raise EmulatorError("cancelled")
            report(done, total)

        return checked

    def _on_progress(self, done: int, total: int) -> None:
        if self._progress is None:
            return
        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(done * 100 / total))
            if self._progress_bytes:
                text = f"{self._progress_label}\n{fmt_size(done)} of {fmt_size(total)}"
                elapsed = time.monotonic() - getattr(self, "_started", time.monotonic())
                if elapsed >= 2 and done > 0 and done < total:
                    rate = done / elapsed
                    text += f"  ({fmt_size(int(rate))}/s, about {max(1, round((total - done) / rate))} s left)"
                elif done >= total:
                    text += "\nUnpacking…"
                self._progress.setLabelText(text)
        else:
            self._progress.setRange(0, 0)

    # ----- install / update -----

    def install_selected(self) -> None:
        spec = self.selected_spec()
        if spec is None:
            return
        self._run(
            lambda report: self.installer.latest_release(spec),
            lambda release, error: self._on_release(spec, release, error),
            f"Looking up the latest {spec.name} release…",
        )

    def _on_release(self, spec: EmulatorSpec, release: Release | None, error: Exception | None) -> None:
        if error is not None:
            self._explain_failure(spec, f"Couldn't look up {spec.name}: {error}")
            return
        found = candidate_assets(spec, release)
        if not found.assets:
            self._explain_failure(
                spec,
                f"Release {release.tag} of {spec.name} has no Linux 64-bit download Arcadia can unpack "
                "(it needs an AppImage, .zip or .tar archive).",
            )
            return
        confirm = InstallConfirmDialog(spec, release, found, self.installer.folder(spec.id), self)
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return
        asset = confirm.chosen_asset()
        self._progress_label = f"Downloading {asset.name}"
        self._progress_bytes = True
        self._cancel = threading.Event()
        self._started = time.monotonic()
        self._progress = QProgressDialog(self._progress_label, "Cancel", 0, 0, self)
        self._progress.canceled.connect(self._cancel.set)
        self._progress.setWindowTitle(f"Installing {spec.name}")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()
        self._run(
            lambda report: self.installer.install(spec, release, asset, self._cancellable(report)),
            lambda installed, err: self._on_installed(spec, installed, err),
            f"Installing {spec.name}…",
        )

    def _on_installed(self, spec: EmulatorSpec, installed, error: Exception | None) -> None:
        if error is not None and str(error) == "cancelled":
            self.status.setText(f"Installing {spec.name} was cancelled. Nothing was changed.")
            return
        if error is not None:
            self._explain_failure(spec, f"{spec.name} wasn't installed: {error}")
            return
        self.changed = True
        self._latest[spec.id] = installed.version
        self.refresh()
        self.status.setText(f"{spec.name} {installed.version} is installed. Its systems will now use this copy.")

    def _explain_failure(self, spec: EmulatorSpec, message: str) -> None:
        QMessageBox.warning(
            self,
            f"{spec.name}",
            f"{message}\n\nNothing was changed. You can still use the Flatpak:\nflatpak install flathub {spec.flatpak}",
        )

    # ----- updates -----

    def check_updates(self) -> None:
        specs = [s for s in self.specs if self.installer.get(s.id) is not None]

        def look(report):
            found = {}
            for spec in specs:
                try:
                    found[spec.id] = self.installer.latest_release(spec).tag
                except EmulatorError as exc:
                    found[spec.id] = f"couldn't check: {exc}"
            return found

        self._run(look, self._on_checked, "Checking for updates…")

    def _on_checked(self, found: dict[str, str] | None, error: Exception | None) -> None:
        if error is not None:
            self.status.setText(f"Couldn't check for updates: {error}")
            return
        self._latest.update(found or {})
        self.refresh()
        newer = [CATALOG[i].name for i, tag in (found or {}).items()
                 if not tag.startswith("couldn't") and self.installer.get(i) and tag != self.installer.get(i).version]
        self.status.setText("Updates available: " + ", ".join(newer) if newer else "Everything installed is up to date.")

    # ----- update everything -----

    def update_all(self) -> None:
        def look(report):
            rows = plan_updates(self.installer)
            installed = installed_flatpaks(self.flatpak_run, self.flatpak_which)
            apps = flatpaks_in_use(self.config, installed, self.installer) if installed else []
            return rows, apps

        self._run(look, self._on_update_plan, "Looking for updates…")

    def _on_update_plan(self, value, error: Exception | None) -> None:
        if error is not None:
            QMessageBox.warning(self, "Update emulators", f"Couldn't look for updates: {error}")
            return
        rows, apps = value
        if not rows and not apps:
            self.status.setText("Nothing to update: no emulators are installed in Arcadia's folder, and none of your Flatpak emulators were found.")
            return
        if not apps and all(r.status == CURRENT for r in rows):
            self._latest.update({r.spec.id: r.newer for r in rows})
            self.refresh()
            self.status.setText("Everything installed is up to date.")
            return
        dialog = UpdateAllDialog(rows, apps, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen, with_flatpak = dialog.selection(), dialog.include_flatpak()
        if not chosen and not with_flatpak:
            return
        self._progress_label = "Updating emulators"
        self._progress_bytes = False
        self._cancel = threading.Event()
        self._started = time.monotonic()
        self._progress = QProgressDialog(self._progress_label, "Cancel", 0, 0, self)
        self._progress.canceled.connect(self._cancel.set)
        self._progress.setWindowTitle("Updating")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        def work(report):
            outcomes = apply_updates(self.installer, chosen, report)
            flatpak = update_flatpaks(apps, self.flatpak_run, self.flatpak_which) if with_flatpak else None
            return outcomes, flatpak

        self._run(work, self._on_updated, "Updating…")

    def _on_updated(self, value, error: Exception | None) -> None:
        if error is not None:
            QMessageBox.warning(self, "Update emulators", f"The update stopped: {error}")
            return
        outcomes, flatpak = value
        lines = []
        for outcome in outcomes:
            if outcome.ok:
                lines.append(f"✓ {outcome.spec.name} is now {outcome.version}")
                self._latest[outcome.spec.id] = outcome.version
            else:
                lines.append(f"✗ {outcome.spec.name} wasn't updated and still works as before: {outcome.error}")
        if flatpak is not None:
            lines.append("✓ Flatpak emulators updated" if flatpak.ok else f"✗ Flatpak update didn't finish: {flatpak.output}")
        self.changed = self.changed or any(o.ok for o in outcomes)
        self.refresh()
        failed = any(not o.ok for o in outcomes) or (flatpak is not None and not flatpak.ok)
        self.status.setText(lines[0] if len(lines) == 1 else f"{len(lines)} results: see the summary.")
        (QMessageBox.warning if failed else QMessageBox.information)(self, "Update emulators", "\n".join(lines))

    # ----- remove / open -----

    def _ask_remove(self, spec: EmulatorSpec) -> str | None:
        """'keep' (remove the program only), 'wipe' (remove its settings and saves too), or None."""
        folder = self.installer.folder(spec.id)
        box = QMessageBox(self)
        box.setWindowTitle(f"Remove {spec.name}")
        box.setText(f"Remove {spec.name} from Arcadia's folder?")
        box.setInformativeText(
            f"Its settings and saves in {folder} are kept unless you choose to delete them too. "
            "That can't be undone."
        )
        keep = box.addButton("Remove program, keep settings and saves", QMessageBox.ButtonRole.AcceptRole)
        wipe = box.addButton("Remove everything", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        return "keep" if clicked is keep else "wipe" if clicked is wipe else None

    def remove_selected(self) -> None:
        spec = self.selected_spec()
        if spec is None or self.installer.get(spec.id) is None:
            return
        choice = self._ask_remove(spec)
        if choice is None:
            return
        self.installer.remove(spec.id, delete_data=(choice == "wipe"))
        self.changed = True
        self._latest.pop(spec.id, None)
        self.refresh()
        self.status.setText(f"{spec.name} removed" + (" along with its settings and saves." if choice == "wipe" else "; its settings and saves were kept."))

    def open_folder(self) -> None:
        spec = self.selected_spec()
        if spec is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.installer.folder(spec.id))))
