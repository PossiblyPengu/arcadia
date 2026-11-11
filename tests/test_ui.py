"""Smoke tests for the Qt window. Skipped automatically where Qt can't load."""

import os

import pytest

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
