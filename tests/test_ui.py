"""Smoke tests for the Qt window. Skipped automatically where Qt can't load."""

import os

import pytest

import isoutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcadia.config import Config  # noqa: E402
from arcadia.coverflow import CoverFlow  # noqa: E402
from arcadia.library import Library  # noqa: E402
from arcadia.ui import VIEW_FAVORITES, VIEW_RECENT, MainWindow, _shorten  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pix():
    pix = QPixmap(40, 56)
    pix.fill(Qt.GlobalColor.gray)
    return pix


def test_coverflow_lazy_loading_and_type_to_jump(qapp):
    loaded = []

    def make(name):
        def loader():
            loaded.append(name)
            return _pix()

        return loader

    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
    flow = CoverFlow()
    flow.resize(900, 520)
    flow.set_items([(n.lower(), n, make(n)) for n in names])
    changes = []
    flow.currentChanged.connect(changes.append)

    assert flow.count() == 6 and flow.current_key() == "alpha"
    assert flow.jump_to_letter("d") is True
    assert flow.current_key() == "delta"
    assert flow.jump_to_letter("a") is True  # wraps around
    assert flow.current_key() == "alpha"
    assert flow.jump_to_letter("z") is False
    assert changes == [3, 0]

    flow.grab()  # paint once; only nearby covers load
    assert "Alpha" in loaded and len(loaded) == len(set(loaded))  # each loaded once


def test_coverflow_empty_state_paints(qapp):
    flow = CoverFlow()
    flow.resize(600, 400)
    flow.set_items([])
    assert flow.current_key() is None
    flow.grab()


@pytest.fixture
def window(qapp, tmp_path):
    roms = tmp_path / "roms"
    for folder, names in {"snes": ["Zelda, The (USA).sfc", "Mario (USA).sfc"], "nes": ["Contra.nes"]}.items():
        (roms / folder).mkdir(parents=True)
        for n in names:
            (roms / folder / n).write_text("x")
    cfg = Config(rom_root=str(roms), data_dir=str(tmp_path / "data"))
    for s in cfg.systems:
        s.command = "echo {rom}"
    lib = Library(cfg.db_path)
    win = MainWindow(cfg, tmp_path / "config.json", lib)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def _pills(win):
    return [win.systems_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(win.systems_list.count())]


def test_empty_systems_are_hidden_by_default(window):
    assert _pills(window) == ["nes", "snes"]
    window.empty_action.setChecked(True)  # View > Show systems with no games
    assert len(_pills(window)) == len(window.config.systems)
    assert window.config.show_empty_systems is True


def test_browse_favorite_and_virtual_views(window):
    window.systems_list.setCurrentRow(_pills(window).index("snes"))
    assert window.coverflow.count() == 2
    assert window.coverflow.current_title() == "Mario"  # sorted A-Z, article moved to the front

    window.coverflow.setFocus()
    QTest.keyClick(window.coverflow, Qt.Key.Key_Right)
    assert window.coverflow.current_title() == "The Zelda"

    window.toggle_favorite()
    assert VIEW_FAVORITES in _pills(window)
    assert window.coverflow.current_title() == "★ The Zelda"  # selection survives the rebuild

    window.systems_list.setCurrentRow(_pills(window).index(VIEW_FAVORITES))
    assert window.coverflow.count() == 1


def test_sort_by_most_played_persists(window):
    window.systems_list.setCurrentRow(_pills(window).index("snes"))
    zelda = next(r["key"] for r in window.library.games("snes") if r["title"] == "The Zelda")
    window.library.record_session(zelda, 1000.0, 600)
    window.refresh_systems()
    assert window.coverflow.titles() == ["Mario", "The Zelda"]
    window.sort_combo.setCurrentIndex(window.sort_combo.findData("played"))
    assert window.coverflow.titles() == ["The Zelda", "Mario"]  # most played first
    assert window.coverflow.current_title() == "Mario"  # the selected game stays selected
    assert '"sort": "played"' in window.config_path.read_text()


def test_launch_records_session_and_recent_view(window, qapp):
    window.systems_list.setCurrentRow(_pills(window).index("nes"))
    window.launch()
    assert window.process is not None
    for _ in range(300):
        qapp.processEvents()
        QTest.qWait(10)
        if window.process is None:
            break
    assert window.process is None
    assert VIEW_RECENT in _pills(window)
    contra = window.library.games("nes")[0]
    assert contra["play_count"] == 1


def test_controller_actions_move_focus_and_selection(window):
    window.systems_list.setCurrentRow(_pills(window).index("snes"))
    window.coverflow.setFocus()
    window.handle_action("right")
    assert window.coverflow.index() == 1
    window.handle_action("favorite")
    assert window.coverflow.current_title().startswith("★")
    # Pills are now [favorites, nes, snes]; the left bumper steps back one pill.
    assert _pills(window) == [VIEW_FAVORITES, "nes", "snes"]
    window.handle_action("prev_system")
    assert window.current_system_id() == "nes"


def test_shorten_trims_at_word_boundary():
    assert _shorten("short", 20) == "short"
    out = _shorten("one two three four five", 12)
    assert out == "one two…" and len(out) <= 12


# ---------- ROM inbox sorting ----------

import time  # noqa: E402
from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from arcadia.import_dialog import ImportDialog  # noqa: E402
from arcadia.sorter import Confidence, build_plan  # noqa: E402
from arcadia.ui import SettingsDialog  # noqa: E402


def _nes_bytes():
    return b"NES\x1a" + bytes(0x4000)


def _gb_bytes():
    data = bytearray(0x200)
    data[0x104:0x10C] = bytes.fromhex("CEED6666CC0D000B")
    return bytes(data)


def _put(path: Path, data: bytes):
    path.write_bytes(data)
    old = time.time() - 3600
    import os

    os.utime(path, (old, old))


def _make_inbox_window(tmp_path, auto_import=True):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _put(inbox / "Contra.nes", _nes_bytes())  # header confirms: certain
    _put(inbox / "Mislabelled.gbc", _gb_bytes())  # DMG header in a .gbc file: unsure
    cfg = Config(
        rom_root=str(tmp_path / "roms"),
        data_dir=str(tmp_path / "data"),
        inbox_dir=str(inbox),
        auto_import=auto_import,
    )
    for s in cfg.systems:
        s.command = "echo {rom}"
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    return win, inbox


@pytest.fixture
def asked(monkeypatch):
    """Record what the user would be asked instead of opening a modal dialog."""
    calls = []

    def fake(self, plan, inbox):
        calls.append(sorted(i.source.name for i in plan.items))

    monkeypatch.setattr(MainWindow, "_show_import_dialog", fake)
    return calls


def test_certain_roms_move_automatically_and_unsure_ones_ask(qapp, tmp_path, asked):
    win, inbox = _make_inbox_window(tmp_path)
    try:
        win.check_inbox()
        assert (tmp_path / "roms" / "nes" / "Contra.nes").exists()
        assert not (inbox / "Contra.nes").exists()
        assert (inbox / "Mislabelled.gbc").exists()  # never moved without confirmation
        assert asked == [["Mislabelled.gbc"]]
        assert "nes" in [win.systems_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(win.systems_list.count())]
    finally:
        win.close()


def test_with_auto_import_off_everything_is_confirmed_first(qapp, tmp_path, asked):
    win, inbox = _make_inbox_window(tmp_path, auto_import=False)
    try:
        win.check_inbox()
        assert (inbox / "Contra.nes").exists() and not (tmp_path / "roms" / "nes").exists()
        assert asked == [["Contra.nes", "Mislabelled.gbc"]]
    finally:
        win.close()


def test_each_file_is_only_asked_about_once(qapp, tmp_path, asked):
    win, inbox = _make_inbox_window(tmp_path)
    try:
        win.check_inbox()
        win.check_inbox()
        assert len(asked) == 1
        _put(inbox / "Weird.nes", b"junk")  # a new file triggers a new question
        win.check_inbox()
        assert len(asked) == 2 and "Weird.nes" in asked[1]
    finally:
        win.close()


def test_a_running_game_is_never_interrupted_by_the_dialog(qapp, tmp_path, asked):
    win, inbox = _make_inbox_window(tmp_path)
    try:
        win.process = object()  # pretend a game is running
        win.check_inbox(rescan_after=False)
        assert asked == []  # no dialog while playing...
        assert (tmp_path / "roms" / "nes" / "Contra.nes").exists()  # ...but sure matches still move quietly
        win.process = None
        win.check_inbox()
        assert asked == [["Mislabelled.gbc"]]  # and it asks once the game is over
    finally:
        win.process = None
        win.close()


def test_undo_import_moves_files_back(qapp, tmp_path, asked, monkeypatch):
    win, inbox = _make_inbox_window(tmp_path)
    try:
        win.check_inbox()
        assert not (inbox / "Contra.nes").exists()
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        win._update_undo_action()
        assert win.undo_import_action.isEnabled() and "1 file" in win.undo_import_action.text()
        win.undo_import()
        assert (inbox / "Contra.nes").exists()
        assert not (tmp_path / "roms" / "nes" / "Contra.nes").exists()
        win._update_undo_action()
        assert not win.undo_import_action.isEnabled()
    finally:
        win.close()


def test_no_inbox_configured_does_nothing(qapp, tmp_path, asked):
    win, inbox = _make_inbox_window(tmp_path)
    try:
        win.config.inbox_dir = ""
        win.check_inbox()
        assert asked == [] and (inbox / "Contra.nes").exists()
    finally:
        win.close()


def test_import_dialog_defaults_and_user_confirmation(qapp, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _put(inbox / "Contra.nes", _nes_bytes())
    _put(inbox / "Mislabelled.gbc", _gb_bytes())
    _put(inbox / "Weird.nes", b"junk")  # extension only: likely
    _put(inbox / "Dupe.nes", _nes_bytes())
    (tmp_path / "roms" / "nes").mkdir(parents=True)
    (tmp_path / "roms" / "nes" / "Dupe.nes").write_bytes(b"already here")
    cfg = Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"))
    plan = build_plan(inbox, cfg)

    dialog = ImportDialog(cfg, plan)
    names = lambda: sorted(i.source.name for i in dialog.selected_items())
    # Sure and likely matches are pre-ticked; the unsure one and the duplicate are not.
    assert names() == ["Contra.nes", "Weird.nes"]
    assert dialog.move_btn.text() == "Move 2 ROMs" and dialog.move_btn.isEnabled()
    assert dialog.items[0].confidence is Confidence.UNSURE  # questions are listed first

    # Choosing a system for the unsure row is the user's confirmation.
    row = next(r for r, i in enumerate(dialog.items) if i.source.name == "Mislabelled.gbc")
    dialog.combos[row].setCurrentIndex(dialog.combos[row].findData("gbc"))
    assert names() == ["Contra.nes", "Mislabelled.gbc", "Weird.nes"]
    chosen = next(i for i in dialog.selected_items() if i.source.name == "Mislabelled.gbc")
    assert chosen.system_id == "gbc" and chosen.manual and chosen.destination.parent.name == "gbc"
    assert dialog.move_btn.text() == "Move 3 ROMs"
    assert dialog.keep_both() is False


def test_import_dialog_with_nothing_ticked_cannot_move(qapp, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _put(inbox / "Mislabelled.gbc", _gb_bytes())
    cfg = Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"))
    dialog = ImportDialog(cfg, build_plan(inbox, cfg))
    assert dialog.selected_items() == []
    assert dialog.move_btn.isEnabled() is False


def test_settings_dialog_saves_inbox_options(qapp, tmp_path):
    cfg = Config(data_dir=str(tmp_path / "data"))
    dialog = SettingsDialog(cfg)
    dialog.inbox_dir.setText("~/Downloads")
    dialog.auto_import.setChecked(False)
    dialog.apply(cfg)
    assert cfg.inbox_dir == "~/Downloads" and cfg.auto_import is False
    assert cfg.inbox_path == Path("~/Downloads").expanduser()


# ---------- multi-disc games and updates / DLC ----------

from arcadia.bundles import write_m3u  # noqa: E402
from arcadia.files_dialog import FilesDialog  # noqa: E402

_TID = "0100ABCD0001"


def _psx_bin():
    return isoutil.psx_disc()


def _library_window(tmp_path, template="echo {rom}"):
    roms = tmp_path / "roms"
    psx = roms / "psx"
    (psx / "Final Fantasy VII").mkdir(parents=True)
    (psx / "Final Fantasy VII" / "Final Fantasy VII (Disc 1).cue").write_text("x")
    (psx / "Final Fantasy VII" / "Final Fantasy VII (Disc 2).cue").write_text("x")
    write_m3u(psx / "Final Fantasy VII.m3u", ["Final Fantasy VII/Final Fantasy VII (Disc 1).cue", "Final Fantasy VII/Final Fantasy VII (Disc 2).cue"])
    sw = roms / "switch"
    sw.mkdir(parents=True)
    (sw / f"Super Game [{_TID}2000][v0].nsp").write_bytes(b"PFS0")
    (sw / f"Super Game [{_TID}2800][v65536].nsp").write_bytes(b"PFS0")
    (sw / f"Super Game DLC [{_TID}3001][v0].nsp").write_bytes(b"PFS0")
    (sw / f"Orphan Game [0100FFFF00022800][v1].nsp").write_bytes(b"PFS0")
    cfg = Config(rom_root=str(roms), data_dir=str(tmp_path / "data"))
    for s in cfg.systems:
        s.command = template
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    win.show()
    return win


def _select_view(win, view):
    ids = [win.systems_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(win.systems_list.count())]
    win.systems_list.setCurrentRow(ids.index(view))


def test_discs_and_updates_are_hidden_inside_their_game(qapp, tmp_path):
    win = _library_window(tmp_path)
    try:
        _select_view(win, "psx")
        assert win.coverflow.titles() == ["Final Fantasy VII"]  # one game, not three entries
        assert "2 discs" in win.meta_lbl.text()
        _select_view(win, "switch")
        assert win.coverflow.titles() == ["Orphan Game (update)", "Super Game"]
        win.coverflow.set_index(win.coverflow.titles().index("Super Game"), animate=False)
        assert "1 update (latest v65536), 1 DLC" in win.meta_lbl.text()
    finally:
        win.close()


def test_launch_passes_the_playlist_and_linked_files(qapp, tmp_path):
    win = _library_window(tmp_path, template="echo --u {updates} --d {dlc} {rom}")
    try:
        _select_view(win, "switch")
        win.coverflow.set_index(win.coverflow.titles().index("Super Game"), animate=False)
        win.launch()
        args = win.process.arguments()
        assert any("2800" in a for a in args[args.index("--u") + 1 :]) and any("3001" in a for a in args)
        assert args[-1].endswith("[0100ABCD00012000][v0].nsp")  # the base game is what launches
        for _ in range(300):
            qapp.processEvents()
            QTest.qWait(10)
            if win.process is None:
                break

        _select_view(win, "psx")
        win.launch()
        assert win.process.arguments()[-1].endswith("Final Fantasy VII.m3u")  # emulators open the playlist
        for _ in range(300):
            qapp.processEvents()
            QTest.qWait(10)
            if win.process is None:
                break
    finally:
        win.close()


def test_launching_a_stray_update_explains_instead_of_launching(qapp, tmp_path, monkeypatch):
    win = _library_window(tmp_path)
    try:
        _select_view(win, "switch")
        win.coverflow.set_index(win.coverflow.titles().index("Orphan Game (update)"), animate=False)
        shown = []
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
        win.launch()
        assert win.process is None
        assert shown and "an update" in shown[0] and "base game" in shown[0]
        assert "update file" in win.meta_lbl.text()
    finally:
        win.close()


def test_files_dialog_lists_every_part(qapp, tmp_path):
    win = _library_window(tmp_path)
    try:
        _select_view(win, "psx")
        rows = win._file_rows(win.current_game_key())
        assert [r for r, _p in rows] == ["Playlist", "Disc", "Disc"]
        _select_view(win, "switch")
        win.coverflow.set_index(win.coverflow.titles().index("Super Game"), animate=False)
        rows = win._file_rows(win.current_game_key())
        assert [r for r, _p in rows] == ["Game", "DLC", "Update v65536"]

        dialog = FilesDialog("Super Game", rows)
        assert dialog.table.rowCount() == 3
        assert dialog.table.item(0, 2).text() == "4 B"  # real file sizes
    finally:
        win.close()


def test_import_dialog_describes_sets_and_bundles(qapp, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for n in (1, 2):
        _put(inbox / f"Game (Disc {n}).cue", f'FILE "Game (Disc {n}).bin" BINARY\n'.encode())
        _put(inbox / f"Game (Disc {n}).bin", _psx_bin())
    _put(inbox / f"Super Game [{_TID}2000][v0].nsp", b"PFS0")
    _put(inbox / f"Super Game [{_TID}2800][v1].nsp", b"PFS0")
    _put(inbox / "Lost (Disc 1).cue", b'FILE "Lost (Disc 1).bin" BINARY\n')
    _put(inbox / "Lost (Disc 1).bin", _psx_bin())
    _put(inbox / "Lost (Disc 3).cue", b'FILE "Lost (Disc 3).bin" BINARY\n')
    _put(inbox / "Lost (Disc 3).bin", _psx_bin())
    cfg = Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"))
    dialog = ImportDialog(cfg, build_plan(inbox, cfg))

    cells = {dialog.table.item(r, 1).text(): r for r in range(dialog.table.rowCount())}
    assert "Game  (2 discs)" in cells and "Super Game [0100ABCD00012000][v0].nsp  (+1 update)" in cells
    set_row, bundle_row = cells["Game  (2 discs)"], cells["Super Game [0100ABCD00012000][v0].nsp  (+1 update)"]
    assert dialog.table.item(set_row, 4).text() == "psx/Game/"
    assert dialog.table.item(bundle_row, 4).text() == "switch/"
    selected = {i.label for i in dialog.selected_items()}
    assert "Game" in selected and "Super Game [0100ABCD00012000][v0].nsp" in selected
    assert "Lost" not in selected  # disc 2 is missing, so the user has to decide


def test_discs_in_the_downloads_folder_are_joined_automatically(qapp, tmp_path, asked):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for n in (1, 2):
        _put(inbox / f"Game (Disc {n}).cue", f'FILE "Game (Disc {n}).bin" BINARY\n'.encode())
        _put(inbox / f"Game (Disc {n}).bin", _psx_bin())
    cfg = Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"), inbox_dir=str(inbox))
    for s in cfg.systems:
        s.command = "echo {rom}"
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    try:
        win.check_inbox()
        assert asked == []  # certain, so no question
        assert (tmp_path / "roms" / "psx" / "Game.m3u").exists()
        _select_view(win, "psx")
        assert win.coverflow.titles() == ["Game"] and "2 discs" in win.meta_lbl.text()
        assert list(inbox.iterdir()) == []
    finally:
        win.close()


def test_mouse_wheel_scrolls_the_system_bar_sideways(qapp, tmp_path):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    from arcadia.config import default_systems

    roms = tmp_path / "roms"
    for s in default_systems():  # a game in every system, so every pill shows
        (roms / s.folder).mkdir(parents=True)
        (roms / s.folder / f"G{s.extensions[0]}").write_text("x")
    cfg = Config(rom_root=str(roms), data_dir=str(tmp_path / "data"))
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    win.resize(900, 700)
    win.show()
    try:
        qapp.processEvents()
        bar = win.systems_list.horizontalScrollBar()
        assert bar.maximum() > 0  # more pills than fit
        start = bar.value()
        down = QWheelEvent(QPointF(50, 20), QPointF(50, 20), QPoint(0, 0), QPoint(0, -120),
                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        win.systems_list.wheelEvent(down)
        assert bar.value() > start  # wheel down moves right, to later systems
    finally:
        win.close()


# ---------- emulators kept in Arcadia's own folder ----------

import json as _json  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

import arcadia.emulators_dialog as emulators_dialog  # noqa: E402
from arcadia.emulators import CATALOG, Asset, Candidates, Installer, Release  # noqa: E402
from arcadia.emulators_dialog import EmulatorsDialog, InstallConfirmDialog  # noqa: E402
from test_emulators import APPIMAGE, _install_fake, fetcher_for, publish, server  # noqa: E402,F401


class SyncTask(QObject):
    """Stands in for the background thread so a test can run a whole flow in order."""

    progress = Signal(int, int)
    done = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self):
        try:
            value, error = self._fn(self.progress.emit), None
        except Exception as exc:
            value, error = None, exc
        self.done.emit(value, error)


@pytest.fixture
def emu_dialog(qapp, tmp_path, server, monkeypatch):
    base, routes = server
    monkeypatch.setattr(emulators_dialog, "TaskClass", SyncTask)
    config = Config.new_install(tmp_path / "Arcadia")
    dialog = EmulatorsDialog(config, Installer(config.emulators_path, fetcher_for(base)))
    dialog.base, dialog.routes = base, routes
    yield dialog
    dialog.close()


def _select(dialog, emu_id):
    dialog.table.selectRow([s.id for s in dialog.specs].index(emu_id))


def _row(dialog, emu_id):
    row = [s.id for s in dialog.specs].index(emu_id)
    return [dialog.table.item(row, c).text() for c in range(5)]


def _accept_install(monkeypatch):
    monkeypatch.setattr(InstallConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


def _record_warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    return shown


def test_the_emulator_list_shows_what_each_one_runs_and_uses(emu_dialog):
    assert emu_dialog.table.rowCount() == len(CATALOG)
    name, runs, here, latest, uses = _row(emu_dialog, "mgba")
    assert (name, here, uses) == ("mGBA", "—", "Flatpak")
    assert runs == "Game Boy, Game Boy Color, Game Boy Advance"
    _select(emu_dialog, "mgba")
    assert emu_dialog.install_btn.text() == "Install…" and not emu_dialog.remove_btn.isEnabled()
    assert str(emu_dialog.config.emulators_path) in emu_dialog.intro.text()


def test_installing_from_the_dialog_end_to_end(emu_dialog, monkeypatch):
    _accept_install(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE, "pcsx2-windows.7z": b"w"}, tag="v2.0")
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()

    inst = emu_dialog.installer.get("pcsx2")
    assert inst is not None and inst.version == "v2.0" and inst.verified
    assert emu_dialog.changed is True
    name, runs, here, latest, uses = _row(emu_dialog, "pcsx2")
    assert here == "v2.0  ✓ verified" and uses == "this copy"
    assert "is installed" in emu_dialog.status.text()
    assert emu_dialog.install_btn.text() == "Update…" and emu_dialog.remove_btn.isEnabled()


def test_a_release_with_no_linux_build_changes_nothing_and_points_to_the_flatpak(emu_dialog, monkeypatch):
    shown = _record_warnings(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-windows-x64.7z": b"w", "pcsx2-macos.tar.xz": b"m"})
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    assert emu_dialog.installer.get("pcsx2") is None and not emu_dialog.changed
    assert shown and "no Linux 64-bit download" in shown[0] and "flatpak install flathub net.pcsx2.PCSX2" in shown[0]


def test_a_network_failure_is_explained_not_thrown(emu_dialog, monkeypatch):
    shown = _record_warnings(monkeypatch)
    _select(emu_dialog, "cemu")  # nothing published for this repo: the server answers 404
    emu_dialog.install_selected()
    assert shown and "Couldn't look up Cemu" in shown[0] and "Nothing was changed" in shown[0]
    assert emu_dialog.installer.get("cemu") is None
    assert emu_dialog._task is None  # the dialog is usable again
    assert emu_dialog.install_btn.isEnabled()


def test_a_bad_checksum_is_reported_and_leaves_nothing_installed(emu_dialog, monkeypatch):
    _accept_install(monkeypatch)
    shown = _record_warnings(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE}, digest="wrong")
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    assert emu_dialog.installer.get("pcsx2") is None and not emu_dialog.changed
    assert shown and "wasn't installed" in shown[0] and "checksum" in shown[0]


def test_cancelling_the_confirmation_downloads_nothing(emu_dialog, monkeypatch):
    monkeypatch.setattr(InstallConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE})
    hits = []
    real = emu_dialog.installer.install
    emu_dialog.installer.install = lambda *a, **k: hits.append(1) or real(*a, **k)
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    assert hits == [] and emu_dialog.installer.get("pcsx2") is None


def test_check_for_updates_reports_a_newer_release(emu_dialog, monkeypatch):
    _accept_install(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE}, tag="v1")
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    assert emu_dialog.check_btn.isEnabled()

    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE}, tag="v2")
    emu_dialog.check_updates()
    assert _row(emu_dialog, "pcsx2")[3] == "v2  — update available"
    assert "Updates available: PCSX2" in emu_dialog.status.text()

    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE}, tag="v1")
    emu_dialog.check_updates()
    assert "up to date" in emu_dialog.status.text()


@pytest.mark.parametrize("choice, data_survives", [("keep", True), ("wipe", False)])
def test_removing_keeps_or_deletes_the_settings_as_chosen(emu_dialog, monkeypatch, choice, data_survives):
    _accept_install(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE})
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    folder = emu_dialog.installer.folder("pcsx2")
    (folder / "config").mkdir(exist_ok=True)
    (folder / "config" / "PCSX2.ini").write_text("my settings")

    monkeypatch.setattr(EmulatorsDialog, "_ask_remove", lambda self, spec: choice)
    emu_dialog.remove_selected()
    assert emu_dialog.installer.get("pcsx2") is None
    assert (folder / "config" / "PCSX2.ini").exists() is data_survives
    assert _row(emu_dialog, "pcsx2")[2] == "—" and _row(emu_dialog, "pcsx2")[4] == "Flatpak"


def test_declining_to_remove_changes_nothing(emu_dialog, monkeypatch):
    _accept_install(monkeypatch)
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-linux-x64.AppImage": APPIMAGE})
    _select(emu_dialog, "pcsx2")
    emu_dialog.install_selected()
    monkeypatch.setattr(EmulatorsDialog, "_ask_remove", lambda self, spec: None)
    emu_dialog.remove_selected()
    assert emu_dialog.installer.get("pcsx2") is not None


def test_the_confirmation_shows_what_will_be_downloaded(qapp, tmp_path):
    spec = CATALOG["pcsx2"]
    verified = Asset("pcsx2-linux-x64.AppImage", "https://github.com/x/a", 5 * 1024 * 1024, "ab" * 32)
    unverified = Asset("other-linux.zip", "https://github.com/x/b", 100, "")
    release = Release("v9.9", (verified, unverified))

    sure = InstallConfirmDialog(spec, release, Candidates((verified, unverified), verified), tmp_path / "pcsx2")
    assert sure.chosen_asset() is verified and "64-bit Linux build" in sure.hint.text()
    assert "SHA-256" in sure.checksum.text() and "thrown away" in sure.checksum.text()
    assert "5.0 MB" in sure.combo.itemText(0)
    sure.combo.setCurrentIndex(1)  # picking a file with no checksum says so
    assert sure.chosen_asset() is unverified and "can't be verified" in sure.checksum.text()

    unsure = InstallConfirmDialog(spec, release, Candidates((verified, unverified), None), tmp_path / "pcsx2")
    assert "hasn't picked one" in unsure.hint.text()  # it asks rather than guessing


# ---------- launching through the main window ----------

def _local_window(tmp_path, script):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    (config.rom_root_path / "ps2" / "Game Name.iso").write_bytes(isoutil.ps2_disc())
    _install_fake(config, "pcsx2", script=script)
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    win.show()
    return win, config


def _wait_for_exit(win, qapp):
    for _ in range(300):
        qapp.processEvents()
        QTest.qWait(10)
        if win.process is None:
            return


def test_launching_runs_the_installed_copy_with_its_data_kept_in_its_folder(qapp, tmp_path):
    seen = tmp_path / "seen.txt"
    script = f'#!/bin/sh\necho "$XDG_CONFIG_HOME|$XDG_DATA_HOME|$@" > "{seen}"\n'
    win, config = _local_window(tmp_path, script)
    try:
        _select_view(win, "ps2")
        win.launch()
        _wait_for_exit(win, qapp)
        folder = config.emulators_path / "pcsx2"
        text = seen.read_text().strip()
        assert text.startswith(f"{folder / 'config'}|{folder / 'data'}|-batch -- ")
        assert text.endswith("Game Name.iso")
        assert win.library.games("ps2")[0]["play_count"] == 1  # and the session was still recorded
    finally:
        win.close()


def test_without_a_local_copy_the_game_launches_via_the_flatpak_command_as_before(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    (config.rom_root_path / "ps2" / "Game Name.iso").write_bytes(isoutil.ps2_disc())
    config.system("ps2").command = "echo flatpak-path {rom}"  # stands in for the Flatpak, so it can run here
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    win.show()
    try:
        _select_view(win, "ps2")
        win.launch()
        assert win.process.program() == "echo" and "flatpak-path" in win.process.arguments()
        _wait_for_exit(win, qapp)
    finally:
        win.close()


def test_the_file_menu_has_an_emulators_entry(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    try:
        labels = [a.text() for a in win.menuBar().actions()[0].menu().actions()]
        assert "Emulators…" in labels
    finally:
        win.close()


# ---------- settings ----------

def test_the_settings_dialog_edits_the_arcadia_folder_and_installed_emulator(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    dialog = SettingsDialog(config)
    assert dialog.home_dir.text() == str(tmp_path / "Arcadia")
    assert str(tmp_path / "Arcadia" / "roms") in dialog.rom_root.placeholderText()

    dialog.home_dir.setText(str(tmp_path / "Elsewhere"))
    row = [dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount())].index("ps2")
    assert dialog.table.item(row, 6).text() == "pcsx2"
    dialog.table.item(row, 6).setText("")  # opt this system out of the installed copy
    dialog.apply(config)
    assert config.home_dir == str(tmp_path / "Elsewhere") and config.rom_root == ""  # still derived from the home
    assert config.system("ps2").emulator == ""

    dialog._reset_presets()
    dialog.apply(config)
    assert config.system("ps2").emulator == "pcsx2"


def test_clearing_the_arcadia_folder_returns_to_the_old_layout(qapp, tmp_path):
    config = Config(rom_root="/games", data_dir=str(tmp_path / "data"))
    dialog = SettingsDialog(config)
    dialog.home_dir.setText("")
    dialog.apply(config)
    assert config.home_dir == "" and config.rom_root == "/games"
