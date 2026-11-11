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
from arcadia.ui import VIEW_ALL, VIEW_FAVORITES, VIEW_RECENT, MainWindow, _shorten  # noqa: E402


@pytest.fixture(autouse=True)
def _never_sync_for_real(monkeypatch):
    """The window syncs saves by itself; no window test may reach a real rclone or sync folder."""
    from arcadia import savesync

    monkeypatch.setattr(savesync, "run_sync", lambda *a, **k: savesync.SyncReport())


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
    return win.carousel.ids()


def test_empty_systems_are_hidden_by_default(window):
    assert _pills(window) == [VIEW_ALL, "nes", "snes"]  # "All games" is a collection, not a console
    window.empty_action.setChecked(True)  # View > Show systems with no games
    assert len(_pills(window)) == len(window.config.systems) + 1
    assert window.config.show_empty_systems is True


def test_browse_favorite_and_virtual_views(window):
    window.carousel.set_index(_pills(window).index("snes"))
    assert window.coverflow.count() == 2
    assert window.coverflow.current_title() == "Mario"  # sorted A-Z, article moved to the front

    window.coverflow.setFocus()
    QTest.keyClick(window.coverflow, Qt.Key.Key_Right)
    assert window.coverflow.current_title() == "The Zelda"

    window.toggle_favorite()
    assert VIEW_FAVORITES in _pills(window)
    assert window.coverflow.current_title() == "★ The Zelda"  # selection survives the rebuild

    window.carousel.set_index(_pills(window).index(VIEW_FAVORITES))
    assert window.coverflow.count() == 1


def test_sort_by_most_played_persists(window):
    window.carousel.set_index(_pills(window).index("snes"))
    zelda = next(r["key"] for r in window.library.games("snes") if r["title"] == "The Zelda")
    window.library.record_session(zelda, 1000.0, 600)
    window.refresh_systems()
    assert window.coverflow.titles() == ["Mario", "The Zelda"]
    window.sort_combo.setCurrentIndex(window.sort_combo.findData("played"))
    assert window.coverflow.titles() == ["The Zelda", "Mario"]  # most played first
    assert window.coverflow.current_title() == "Mario"  # the selected game stays selected
    assert '"sort": "played"' in window.config_path.read_text()


def test_launch_records_session_and_recent_view(window, qapp):
    window.carousel.set_index(_pills(window).index("nes"))
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
    window.carousel.set_index(_pills(window).index("snes"))
    window.show_games()
    window.handle_action("right")
    assert window.coverflow.index() == 1
    window.handle_action("favorite")
    assert window.coverflow.current_title().startswith("★")
    # Tiles are now [favorites, all, nes, snes]; the left bumper steps back one console.
    assert _pills(window) == [VIEW_FAVORITES, VIEW_ALL, "nes", "snes"]
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
        assert "nes" in win.carousel.ids()
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
    ids = win.carousel.ids()
    win.carousel.set_index(ids.index(view))


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


def test_every_console_is_on_the_ring_and_it_wraps_around(qapp, tmp_path):
    from arcadia.config import default_systems

    roms = tmp_path / "roms"
    for s in default_systems():  # a game in every system, so every console shows
        (roms / s.folder).mkdir(parents=True)
        (roms / s.folder / f"G{s.extensions[0]}").write_text("x")
    cfg = Config(rom_root=str(roms), data_dir=str(tmp_path / "data"))
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    win.resize(1280, 800)
    win.show()
    try:
        qapp.processEvents()
        ring = win.carousel
        assert ring.count() == len(default_systems()) + 1  # every console, and "All games"
        ring.set_index(ring.count() - 1, animate=False)
        last = ring.current_id()
        ring.rotate(1)  # past the last one comes the first
        assert ring.index() == 0 and ring.current_id() != last
        ring.rotate(-1)  # and back before the first comes the last
        assert ring.current_id() == last
        assert win.carousel.grab().toImage().pixelColor(win.carousel.width() // 2, 100).alpha() >= 0
    finally:
        win.close()


# ---------- the two screens: choose a console, then a game ----------

def test_starts_on_the_console_screen_and_opens_a_console(window):
    assert window.stack.currentIndex() == 0 and not window.on_games_page()
    window.carousel.set_index(_pills(window).index("snes"))
    assert window.stack.currentIndex() == 0  # moving between tiles doesn't leave the screen
    window.carousel.activated.emit(window.carousel.index())  # Enter
    assert window.on_games_page() and window.coverflow.count() == 2
    assert window.banner.text() == "SUPER NINTENDO"


def test_back_returns_to_the_consoles_and_forgets_the_search(window):
    window.carousel.set_index(_pills(window).index("snes"))
    window.show_games()
    window.search.setText("zel")
    assert window.coverflow.titles() == ["The Zelda"]
    window.search.clearFocus()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.on_games_page() and window.search.text() == ""
    window.show_games()
    assert window.coverflow.count() == 2  # the console is whole again


def test_escape_in_the_search_box_does_not_leave_the_screen(window):
    window.show_games()
    window.search.setFocus()
    QTest.keyClick(window.search, Qt.Key.Key_Escape)
    assert window.on_games_page()


def test_ctrl_f_on_the_console_screen_searches_every_game(window):
    window.focus_search()
    assert window.on_games_page() and window.current_system_id() == VIEW_ALL
    window.search.setText("contra")
    assert window.coverflow.titles() == ["Contra"]  # found in NES while searching all consoles


def test_controller_flow_between_the_screens(window):
    window.carousel.set_index(_pills(window).index("nes"))
    window.handle_action("favorite")  # nothing to favorite on the console screen
    assert window.library.summary()["favorites"] == 0
    window.handle_action("confirm")  # A opens the console
    assert window.on_games_page()
    window.handle_action("next_system")  # a bumper changes console without going back
    assert window.on_games_page() and window.current_system_id() == "snes" and window.coverflow.count() == 2
    window.handle_action("up")  # nothing above the shelf
    assert window.on_games_page()
    window.handle_action("back")  # B goes back
    assert not window.on_games_page()
    window.handle_action("back")  # and does nothing more
    assert not window.on_games_page()


def test_each_console_carries_its_name_count_and_accent(window):
    entry = window.carousel.entries()[_pills(window).index("snes")]
    assert (entry.name, entry.count, entry.accent) == ("Super Nintendo", 2, "#7b4fd6")
    assert window.library_lbl.text() == "2 consoles  ·  3 games"


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


def test_the_confirmation_names_the_real_download_host_and_shows_the_hardware_note(qapp, tmp_path):
    eden = CATALOG["eden"]
    amd64 = Asset("Eden-Linux-v1-amd64-gcc-standard.AppImage", "https://stable.eden-emu.dev/v1/amd64.AppImage", 200 * 1024 * 1024, "")
    deck = Asset("Eden-Linux-v1-steamdeck-gcc-standard.AppImage", "https://stable.eden-emu.dev/v1/deck.AppImage", 200 * 1024 * 1024, "")
    dialog = InstallConfirmDialog(eden, Release("v1", (amd64, deck)), Candidates((amd64, deck), amd64), tmp_path / "eden")
    assert "stable.eden-emu.dev" in dialog.source.text() and "eden-emu/eden" in dialog.source.text()
    assert "github.com" not in dialog.source.text()  # it says where the file really comes from
    assert not dialog.notes.isHidden() and "steamdeck" in dialog.notes.text() and "Steam Deck" in dialog.notes.text()
    assert "can't be verified" in dialog.checksum.text()  # Eden publishes no checksums, and it says so
    dialog.combo.setCurrentIndex(1)
    assert dialog.chosen_asset() is deck

    plain = InstallConfirmDialog(CATALOG["pcsx2"], Release("v2", (amd64,)), Candidates((amd64,), amd64), tmp_path / "pcsx2")
    assert plain.notes.isHidden()  # no note for an emulator that has none


def test_eden_appears_in_the_emulator_list_for_the_switch(emu_dialog):
    name, runs, here, latest, uses = _row(emu_dialog, "eden")
    assert (name, runs, here, uses) == ("Eden", "Nintendo Switch", "—", "Flatpak")


# ---------- the Setup window from the main window ----------

import arcadia.ui as ui_module  # noqa: E402
from arcadia.consolidate import adopt_home  # noqa: E402


def _fake_setup(flags: dict):
    """A stand-in Setup window that records what it was given and reports the outcomes in `flags`."""

    class FakeSetup:
        def __init__(self, config, config_path, journal, counts, parent=None):
            self.config_changed = flags.get("config_changed", False)
            self.restored = flags.get("restored", False)
            self.emulators_changed = flags.get("emulators_changed", False)
            self.received = (config, config_path, journal, counts)
            flags["seen"] = self

        def exec(self):
            if flags.get("act"):
                flags["act"]()

    return FakeSetup


def test_the_file_menu_has_the_setup_entry(qapp, tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    try:
        labels = [a.text() for a in win.menuBar().actions()[0].menu().actions()]
        assert "Arcadia folder and setup…" in labels
    finally:
        win.close()


def test_the_setup_window_is_given_the_game_counts(qapp, tmp_path, monkeypatch):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    (config.rom_root_path / "psx" / "Game.cue").write_text("x")
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    flags = {}
    monkeypatch.setattr(ui_module, "SetupDialog", _fake_setup(flags))
    try:
        win.open_setup()
        given_config, given_path, given_journal, counts = flags["seen"].received
        assert given_config is config and given_path == tmp_path / "config.json" and given_journal is win.journal
        assert counts == {"psx": 1}  # how many games each system has, so it can list only the ones in use
        assert win.toast.text() == "" or "Restart" not in win.toast.text()  # nothing happened in it: no side effects
    finally:
        win.close()


def test_a_restored_backup_makes_the_window_reopen_the_library(qapp, tmp_path, monkeypatch):
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    flags = {"restored": True}
    monkeypatch.setattr(ui_module, "SetupDialog", _fake_setup(flags))
    try:
        before = win.library
        win.open_setup()
        assert win.library is not before  # the file was replaced under the old connection, so it was reopened
        assert "Backup restored" in win.toast.text()
    finally:
        win.close()


def test_bringing_a_library_in_saves_the_config_and_says_to_restart(qapp, tmp_path, monkeypatch):
    legacy = Config(rom_root=str(tmp_path / "OldROMs"), data_dir=str(tmp_path / "olddata"))
    (tmp_path / "olddata").mkdir()
    (tmp_path / "OldROMs").mkdir()
    config_path = tmp_path / "config.json"
    win = MainWindow(legacy, config_path, Library(legacy.db_path))
    flags = {"config_changed": True, "act": lambda: adopt_home(legacy, tmp_path / "Arcadia", roms=True, data=True)}
    monkeypatch.setattr(ui_module, "SetupDialog", _fake_setup(flags))
    try:
        win.open_setup()
        saved = _json.loads(config_path.read_text())
        assert saved["home_dir"] == str(tmp_path / "Arcadia") and saved["rom_root"] == "" and saved["data_dir"] == ""
        assert (tmp_path / "Arcadia" / "roms" / "nes").is_dir()  # the new folders were created
        assert win.journal.path == tmp_path / "Arcadia" / "data" / "imports.json"  # undo now reads the new place
        assert "Restart Arcadia" in win.toast.text()
    finally:
        win.close()


# ---------- updating every emulator ----------

import subprocess as _subprocess  # noqa: E402
import time as _time  # noqa: E402

from arcadia.tasks import DaemonTask  # noqa: E402
from arcadia.emulators_dialog import UpdateAllDialog  # noqa: E402
from arcadia.updates import CHOOSE, CURRENT, ERROR, NO_BUILD, READY, UpdateRow  # noqa: E402


def _installed_stub(emu_id, asset, version="v1"):
    from arcadia.emulators import Installed

    return Installed(emu_id, version, asset, "0" * 64, True, "emu")


def _update_row(emu_id, status, **kw):
    spec = CATALOG[emu_id]
    release = Release("v2", ()) if status != ERROR else None
    return UpdateRow(spec, _installed_stub(emu_id, f"{emu_id}-v1.AppImage"), release, status, **kw)


def test_the_update_window_lays_out_exactly_what_would_happen(qapp):
    verified = Asset("pcsx2-v2.AppImage", "https://github.com/x/a", 10, "ab" * 32)
    unverified = Asset("Eden-v2-steamdeck.AppImage", "https://x/b", 10, "")
    options = (Asset("mgba-v2-a.AppImage", "https://x/c", 1, "cd" * 32), Asset("mgba-v2-b.AppImage", "https://x/d", 1, ""))
    rows = [
        _update_row("pcsx2", READY, asset=verified),
        _update_row("eden", READY, asset=unverified),
        _update_row("mgba", CHOOSE, choices=options, message="couldn't tell which"),
        _update_row("cemu", CURRENT),
        _update_row("flycast", NO_BUILD, message="no Linux 64-bit download"),
        _update_row("xemu", ERROR, message="couldn't reach the server"),
    ]
    dialog = UpdateAllDialog(rows, ["org.libretro.RetroArch", "io.mgba.mGBA"])
    text = lambda r, c: dialog.table.item(r, c).text()
    check = lambda r: dialog.table.item(r, 0).checkState()

    assert (text(0, 1), text(0, 2), text(0, 3), text(0, 4), text(0, 5)) == ("PCSX2", "v1", "v2", "pcsx2-v2.AppImage", "will be checked")
    assert text(1, 5) == "none published" and check(0) == check(1) == Qt.CheckState.Checked
    assert dialog.combos[2].count() == 3 and check(2) == Qt.CheckState.Unchecked  # an ambiguous one is not ticked for you
    assert text(3, 4) == "Up to date" and text(4, 4) == "no Linux 64-bit download" and text(5, 4) == "couldn't reach the server"
    assert not (dialog.table.item(3, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable)  # nothing to select on these
    assert [r.spec.id for r, _a in dialog.selection()] == ["pcsx2", "eden"]
    assert dialog.go.text() == "Update 2 emulators and Flatpaks" and dialog.go.isEnabled()

    dialog.combos[2].setCurrentIndex(1)  # choosing a download is saying yes to it
    assert check(2) == Qt.CheckState.Checked and text(2, 5) == "will be checked"
    assert [(r.spec.id, a.name) for r, a in dialog.selection()][-1] == ("mgba", "mgba-v2-a.AppImage")
    dialog.combos[2].setCurrentIndex(2)
    assert text(2, 5) == "none published"
    dialog.combos[2].setCurrentIndex(0)
    assert check(2) == Qt.CheckState.Unchecked and len(dialog.selection()) == 2


def test_the_flatpak_option_is_offered_only_when_there_are_flatpaks(qapp):
    none = UpdateAllDialog([_update_row("pcsx2", READY, asset=Asset("a.AppImage", "https://x/a", 1, ""))], [])
    assert none.flatpak_box.isHidden() and not none.include_flatpak()
    some = UpdateAllDialog([_update_row("pcsx2", CURRENT)], ["io.mgba.mGBA"])
    some.show()
    assert some.include_flatpak() and "io.mgba.mGBA" in some.flatpak_box.text()
    assert some.go.text() == "Update Flatpaks" and some.go.isEnabled()  # nothing local to update, but Flatpaks can be
    some.flatpak_box.setChecked(False)
    assert some.go.text() == "Nothing selected" and not some.go.isEnabled()


def _fake_flatpak(listing="io.mgba.mGBA\norg.libretro.RetroArch\nnet.pcsx2.PCSX2\n", update_rc=0):
    calls = []

    def run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[:2] == ["flatpak", "list"]:
            return _subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        return _subprocess.CompletedProcess(cmd, update_rc, stdout="Updating io.mgba.mGBA\n", stderr="")

    run.calls = calls
    return run


def _accept_update_dialog(monkeypatch):
    monkeypatch.setattr(UpdateAllDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


def _install_v1(dialog, name_v1, spec_id, tag="v1"):
    spec = CATALOG[spec_id]
    publish(dialog.base, dialog.routes, {name_v1: APPIMAGE}, tag=tag, repo=spec.repo)
    release = dialog.installer.latest_release(spec)
    dialog.installer.install(spec, release, release.assets[0])


def test_update_all_updates_every_emulator_and_the_flatpaks(emu_dialog, monkeypatch):
    _accept_update_dialog(monkeypatch)
    shown = {"info": [], "warn": []}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown["info"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown["warn"].append(a[2]))
    _install_v1(emu_dialog, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "pcsx2", "v1")
    _install_v1(emu_dialog, "mGBA-1-appimage-x64.appimage", "mgba", "1")
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE + b"2"}, tag="v2", repo=CATALOG["pcsx2"].repo)
    publish(emu_dialog.base, emu_dialog.routes, {"mGBA-2-appimage-x64.appimage": APPIMAGE + b"2"}, tag="2", repo=CATALOG["mgba"].repo)
    emu_dialog.flatpak_run = _fake_flatpak()
    emu_dialog.flatpak_which = lambda p: "/usr/bin/flatpak"

    emu_dialog.update_all()

    assert emu_dialog.installer.get("pcsx2").version == "v2" and emu_dialog.installer.get("mgba").version == "2"
    assert emu_dialog.changed is True and not shown["warn"]
    summary = shown["info"][-1]
    assert "✓ PCSX2 is now v2" in summary and "✓ mGBA is now 2" in summary and "Flatpak emulators updated" in summary
    update_call = [c for c in emu_dialog.flatpak_run.calls if c[:2] == ["flatpak", "update"]][0]
    # PCSX2 and mGBA now run from Arcadia's folder, so their Flatpaks are no longer in use and aren't touched;
    # RetroArch is still behind other systems, so it's the only one named
    assert update_call == ["flatpak", "update", "-y", "--noninteractive", "org.libretro.RetroArch"]
    assert _row_text(emu_dialog, "pcsx2")[2].startswith("v2")


def _row_text(dialog, emu_id):
    row = [s.id for s in dialog.specs].index(emu_id)
    return [dialog.table.item(row, c).text() for c in range(5)]


def test_a_failure_in_the_batch_is_reported_and_leaves_that_emulator_as_it_was(emu_dialog, monkeypatch):
    _accept_update_dialog(monkeypatch)
    shown = {"info": [], "warn": []}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown["info"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown["warn"].append(a[2]))
    _install_v1(emu_dialog, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "pcsx2", "v1")
    _install_v1(emu_dialog, "mGBA-1-appimage-x64.appimage", "mgba", "1")
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE}, tag="v2", digest="wrong", repo=CATALOG["pcsx2"].repo)
    publish(emu_dialog.base, emu_dialog.routes, {"mGBA-2-appimage-x64.appimage": APPIMAGE}, tag="2", repo=CATALOG["mgba"].repo)
    emu_dialog.flatpak_which = lambda p: None  # no flatpak on this machine

    emu_dialog.update_all()
    assert emu_dialog.installer.get("pcsx2").version == "v1" and emu_dialog.installer.get("mgba").version == "2"
    message = shown["warn"][-1]  # a problem is a warning, not a cheerful "done"
    assert "✗ PCSX2 wasn't updated and still works as before" in message and "checksum" in message and "✓ mGBA is now 2" in message
    assert not shown["info"]


def test_cancelling_the_update_window_changes_nothing(emu_dialog, monkeypatch):
    monkeypatch.setattr(UpdateAllDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    _install_v1(emu_dialog, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "pcsx2", "v1")
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE}, tag="v2", repo=CATALOG["pcsx2"].repo)
    emu_dialog.flatpak_which = lambda p: None
    emu_dialog.update_all()
    assert emu_dialog.installer.get("pcsx2").version == "v1" and not emu_dialog.changed


def test_unticking_the_flatpaks_leaves_them_alone(emu_dialog, monkeypatch):
    def accept_without_flatpaks(self):
        self.flatpak_box.setChecked(False)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(UpdateAllDialog, "exec", accept_without_flatpaks)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    _install_v1(emu_dialog, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "pcsx2", "v1")
    publish(emu_dialog.base, emu_dialog.routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE}, tag="v2", repo=CATALOG["pcsx2"].repo)
    emu_dialog.flatpak_run = _fake_flatpak()
    emu_dialog.flatpak_which = lambda p: "/usr/bin/flatpak"
    emu_dialog.update_all()
    assert emu_dialog.installer.get("pcsx2").version == "v2"
    assert not [c for c in emu_dialog.flatpak_run.calls if c[:2] == ["flatpak", "update"]]  # asked about, never updated


def test_nothing_installed_and_no_flatpak_says_so_without_a_window(emu_dialog, monkeypatch):
    opened = []
    monkeypatch.setattr(UpdateAllDialog, "exec", lambda self: opened.append(1) or QDialog.DialogCode.Rejected)
    emu_dialog.flatpak_which = lambda p: None
    emu_dialog.update_all()
    assert not opened and "Nothing to update" in emu_dialog.status.text()


def test_when_everything_is_current_it_just_says_so(emu_dialog, monkeypatch):
    opened = []
    monkeypatch.setattr(UpdateAllDialog, "exec", lambda self: opened.append(1) or QDialog.DialogCode.Rejected)
    _install_v1(emu_dialog, "pcsx2-linux-appimage-x64-Qt.AppImage", "pcsx2", "v7")
    emu_dialog.flatpak_which = lambda p: None
    emu_dialog.update_all()
    assert not opened and "up to date" in emu_dialog.status.text()


def test_a_failed_lookup_is_explained(emu_dialog, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    monkeypatch.setattr(emulators_dialog, "plan_updates", lambda installer: (_ for _ in ()).throw(RuntimeError("no network")))
    emu_dialog.update_all()
    assert warned and "Couldn't look for updates: no network" in warned[0]


# ---------- the startup check ----------

class SyncDaemon(QObject):
    done = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self):
        try:
            value, error = self._fn(), None
        except Exception as exc:
            value, error = None, exc
        self.done.emit(value, error)


def _startup_window(tmp_path, server, monkeypatch, check):
    base, routes = server
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    config.check_updates = check
    installer = Installer(config.emulators_path, fetcher_for(base))
    publish(base, routes, {"pcsx2-v1-linux-appimage-x64-Qt.AppImage": APPIMAGE}, tag="v1", repo=CATALOG["pcsx2"].repo)
    spec = CATALOG["pcsx2"]
    installer.install(spec, installer.latest_release(spec), installer.latest_release(spec).assets[0])
    monkeypatch.setattr(ui_module, "Installer", lambda path: Installer(path, fetcher_for(base)))
    monkeypatch.setattr(ui_module, "DaemonTask", SyncDaemon)
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    return win, base, routes


def test_the_startup_check_only_mentions_updates_it_does_not_install_them(qapp, tmp_path, server, monkeypatch):
    win, base, routes = _startup_window(tmp_path, server, monkeypatch, check=True)
    try:
        publish(base, routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE + b"2"}, tag="v2", repo=CATALOG["pcsx2"].repo)
        win._startup_update_check()
        assert "1 emulator update available" in win.toast.text() and "Update all" in win.toast.text()
        assert Installer(win.config.emulators_path).get("pcsx2").version == "v1"  # nothing was installed
    finally:
        win.close()


def test_the_startup_check_is_silent_when_there_is_nothing_new(qapp, tmp_path, server, monkeypatch):
    win, base, routes = _startup_window(tmp_path, server, monkeypatch, check=True)
    try:
        win._startup_update_check()  # the latest release is still v1
        assert win.toast.text() == "" or "update" not in win.toast.text()
    finally:
        win.close()


def test_the_startup_check_makes_no_requests_unless_asked(qapp, tmp_path, server, monkeypatch):
    win, base, routes = _startup_window(tmp_path, server, monkeypatch, check=False)
    started = []
    monkeypatch.setattr(SyncDaemon, "start", lambda self: started.append(1))
    try:
        win._startup_update_check()
        assert started == []  # the default: no network at startup
    finally:
        win.close()


def test_the_startup_check_does_nothing_with_no_emulators_installed(qapp, tmp_path, monkeypatch):
    config = Config.new_install(tmp_path / "Arcadia")
    config.check_updates = True
    started = []
    monkeypatch.setattr(ui_module, "DaemonTask", lambda fn, parent=None: started.append(1))
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    try:
        win._startup_update_check()
        assert started == []
    finally:
        win.close()


def test_the_settings_dialog_saves_the_update_check_option(qapp, tmp_path):
    config = Config(data_dir=str(tmp_path / "data"))
    assert config.check_updates is False  # off unless the user turns it on
    dialog = SettingsDialog(config)
    assert not dialog.check_updates.isChecked() and "Eden" in dialog.check_updates.text()
    dialog.check_updates.setChecked(True)
    dialog.apply(config)
    assert config.check_updates is True


def test_a_daemon_task_delivers_its_result_on_the_interface_thread(qapp):
    got = []

    class Receiver(QObject):
        def take(self, value, error):
            got.append((value, error))

    receiver = Receiver()
    task = DaemonTask(lambda: 21 * 2, receiver)
    task.done.connect(receiver.take)
    task.start()
    for _ in range(300):
        qapp.processEvents()
        if got:
            break
        _time.sleep(0.01)
    assert got == [(42, None)]

    failing = DaemonTask(lambda: 1 / 0, receiver)
    failing.done.connect(receiver.take)
    failing.start()
    for _ in range(300):
        qapp.processEvents()
        if len(got) > 1:
            break
        _time.sleep(0.01)
    assert got[1][0] is None and isinstance(got[1][1], ZeroDivisionError)


# ----- automatic save sync -----

def _auto_window(window, monkeypatch, calls, rclone=True):
    import arcadia.ui as ui
    from arcadia import savesync
    from qtutil import SyncTask

    monkeypatch.setattr(ui, "TaskClass", SyncTask)
    monkeypatch.setattr(ui.shutil, "which", lambda _n: "/usr/bin/rclone" if rclone else None)
    monkeypatch.setattr(savesync, "run_sync", lambda cfg, *a, **k: calls.append(cfg) or savesync.SyncReport(pushed=2))
    return window


def test_saves_sync_at_startup_and_after_a_game_closes(window, monkeypatch):
    calls = []
    _auto_window(window, monkeypatch, calls)
    window._auto_sync()
    assert len(calls) == 1 and window._sync_task is None
    window.process = object()  # a game is running: never sync under it
    window._auto_sync()
    assert len(calls) == 1
    window.process = None


def test_auto_sync_stays_quiet_when_it_cannot_or_should_not_run(window, monkeypatch):
    calls = []
    _auto_window(window, monkeypatch, calls, rclone=False)
    window._auto_sync()  # default target is Google Drive but rclone isn't installed
    window.config.sync_remote, window.config.sync_dir = "", ""
    _auto_window(window, monkeypatch, calls)
    window._auto_sync()  # nothing set up
    window.config.sync_remote = "gdrive:Arcadia"
    window.config.auto_sync = False
    window._auto_sync()  # switched off
    assert calls == []


def test_launch_waits_while_saves_are_syncing(window, monkeypatch):
    window._sync_task = object()
    window.launch()
    assert window.process is None
    window._sync_task = None


# ---------- the carousel and the pixel art ----------

def test_carousel_keys_rotate_open_and_jump_by_letter(window):
    ring = window.carousel
    ring.setFocus()
    assert ring.ids() == [VIEW_ALL, "nes", "snes"] and ring.current_id() == "nes"
    QTest.keyClick(ring, Qt.Key.Key_Right)
    assert ring.current_id() == "snes"
    QTest.keyClick(ring, Qt.Key.Key_Right)  # wraps round to the first
    assert ring.current_id() == VIEW_ALL
    QTest.keyClick(ring, Qt.Key.Key_Left)
    assert ring.current_id() == "snes"
    assert ring.jump_to_letter("n") is True and ring.current_id() == "nes"
    assert ring.jump_to_letter("z") is False
    QTest.keyClick(ring, Qt.Key.Key_Return)
    assert window.on_games_page() and window.coverflow.count() == 1


def test_clicking_a_side_console_rotates_to_it_and_the_middle_one_opens(window, qapp):
    from PySide6.QtCore import QPoint

    ring = window.carousel
    window.resize(1280, 800)
    qapp.processEvents()
    side = next(i for i in range(ring.count()) if i != ring.index())
    place = ring._place(side)
    QTest.mouseClick(ring, Qt.MouseButton.LeftButton, pos=QPoint(int(place[0]), int(place[1])))
    assert ring.index() == side and not window.on_games_page()
    mid = ring._place(ring.index())
    QTest.mouseClick(ring, Qt.MouseButton.LeftButton, pos=QPoint(int(mid[0]), int(mid[1])))
    assert window.on_games_page()


def hover(widget, pos):
    """Move the pointer over a widget by delivering the event directly (offscreen cursors are unreliable)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(pos), widget.mapToGlobal(QPointF(pos)), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    widget.mouseMoveEvent(event)


def test_hovering_a_console_makes_it_glow_and_leaving_fades_it(window, qapp):
    from PySide6.QtCore import QPoint

    ring = window.carousel
    window.resize(1280, 800)
    qapp.processEvents()
    side = next(i for i in range(ring.count()) if i != ring.index())
    place = ring._place(side)
    hover(ring, QPoint(int(place[0]), int(place[1])))
    for _ in range(60):
        QTest.qWait(16)
    assert ring._hover == side and ring._glow.get(side, 0) > 0.9
    assert 0.4 < ring._glow.get(ring.index(), 0) < 0.6  # the chosen one glows softly by itself
    hover(ring, QPoint(2, 2))
    ring.leaveEvent(None)
    for _ in range(80):
        QTest.qWait(16)
    assert side not in ring._glow


def test_every_console_has_pixel_art_and_a_glow(qapp):
    from arcadia import pixelart
    from arcadia.config import default_systems

    for system in default_systems():
        assert system.id in pixelart.SPRITES, f"no pixel art for {system.id}"
    for view_id in [*pixelart.SPRITES, "something-the-user-added"]:
        image = pixelart.sprite_image(view_id)
        assert 20 < image.width() <= 160 and 20 < image.height() <= 160  # a tight render of the model
        opaque = sum(image.pixelColor(x, y).alpha() > 0 for x in range(image.width()) for y in range(image.height()))
        assert opaque > 300  # a solid, filled-in shape
        fitted = pixelart.scaled(view_id, 240)
        assert (fitted.width(), fitted.height()) == (240, 180)  # every console is fitted into the same box
        assert pixelart.glow(view_id, 128, "#ff0000").width() > 128
    # 2.5D: the front, top and side of a console are shaded differently
    img = pixelart.sprite_image("gc")
    shades = {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height()) if img.pixelColor(x, y).alpha()}
    assert len(shades) >= 6
