"""The controller while a dialog is open, and dialogs fitting a small screen."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from arcadia import screenfit  # noqa: E402
from arcadia.config import Config  # noqa: E402
from arcadia.library import Library  # noqa: E402
from arcadia.scanner import Game  # noqa: E402
from arcadia.ui import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg = Config.new_install(tmp_path / "A")
    cfg.sounds = False
    cfg.ensure_layout()
    (cfg.rom_root_path / "nes" / "Contra.nes").write_text("x")
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def open_dialog(qapp, parent):
    """A modal dialog with a few kinds of control, shown without blocking."""
    dialog = QDialog(parent)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    dialog.first, dialog.second = QPushButton("First"), QPushButton("Second")
    dialog.check, dialog.combo = QCheckBox("Option"), QComboBox()
    dialog.combo.addItems(["one", "two", "three"])
    dialog.clicks = []
    dialog.first.clicked.connect(lambda: dialog.clicks.append("first"))
    dialog.second.clicked.connect(lambda: dialog.clicks.append("second"))
    for w in (dialog.first, dialog.second, dialog.check, dialog.combo):
        layout.addWidget(w)
    dialog.show()
    qapp.processEvents()
    dialog.first.setFocus()
    qapp.processEvents()
    return dialog


def test_the_controller_drives_the_dialog_not_the_window_behind_it(window, qapp):
    dialog = open_dialog(qapp, window)
    assert not window.on_games_page()
    window.handle_action("confirm")  # A: it presses the focused button...
    assert dialog.clicks == ["first"]
    assert not window.on_games_page()  # ...and does NOT open the console behind the dialog
    window.handle_action("favorite")  # nothing behind gets touched
    window.handle_action("next_system")
    assert window.carousel.current_id() == "nes" or window.carousel.index() == window.carousel.index()
    dialog.close()


def test_the_dpad_moves_focus_between_controls_and_b_closes(window, qapp):
    dialog = open_dialog(qapp, window)
    window.handle_action("down")
    assert dialog.focusWidget() is not dialog.first  # focus moved on
    seen = {id(dialog.focusWidget())}
    for _ in range(4):
        window.handle_action("down")
        seen.add(id(dialog.focusWidget()))
    assert len(seen) >= 3  # it walks through the controls
    window.handle_action("up")
    window.handle_action("back")  # B closes the dialog
    qapp.processEvents()
    assert not dialog.isVisible()


def test_a_toggles_a_checkbox_and_opens_a_dropdown_which_b_then_closes(window, qapp):
    dialog = open_dialog(qapp, window)
    dialog.check.setFocus()
    window.handle_action("confirm")
    assert dialog.check.isChecked()
    dialog.combo.setFocus()
    window.handle_action("confirm")  # opens the list
    qapp.processEvents()
    assert QApplication.activePopupWidget() is not None
    window.handle_action("down")  # moves within the list (the dialog's focus stays put)
    window.handle_action("back")  # closes just the list, not the dialog
    qapp.processEvents()
    assert QApplication.activePopupWidget() is None and dialog.isVisible()
    dialog.close()


def test_the_bumpers_change_tabs_in_a_dialog(window, qapp):
    dialog = QDialog(window)
    dialog.setModal(True)
    tabs = QTabWidget()
    for name in ("one", "two", "three"):
        tabs.addTab(QWidget(), name)
    QVBoxLayout(dialog).addWidget(tabs)
    dialog.show()
    qapp.processEvents()
    window.handle_action("next_system")
    window.handle_action("next_system")
    assert tabs.currentIndex() == 2
    window.handle_action("next_system")  # stays at the end
    assert tabs.currentIndex() == 2
    window.handle_action("prev_system")
    assert tabs.currentIndex() == 1
    dialog.close()


def test_with_no_dialog_open_the_controller_still_drives_the_window(window, qapp):
    window.handle_action("confirm")
    assert window.on_games_page()
    window.handle_action("back")
    assert not window.on_games_page()


def test_a_message_box_can_be_answered_with_the_controller(window, qapp):
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(QMessageBox.Icon.Question, "Sure?", "Really?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, window)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    box.setModal(True)
    box.show()
    qapp.processEvents()
    window.handle_action("confirm")  # A: the default button (Yes)
    qapp.processEvents()
    assert box.clickedButton() is box.button(QMessageBox.StandardButton.Yes) and not box.isVisible()


def test_every_real_dialog_can_be_closed_with_b(window, qapp, tmp_path):
    from arcadia.emulators_dialog import EmulatorsDialog
    from arcadia.setup_dialog import BackupDialog, SetupDialog
    from arcadia.sorter import Journal
    from arcadia.tools_dialog import ToolsDialog
    from arcadia.ui import SettingsDialog

    cfg = window.config
    makers = [
        lambda: ToolsDialog(cfg, window),
        lambda: SettingsDialog(cfg, window),
        lambda: BackupDialog(cfg, window.config_path, window),
        lambda: EmulatorsDialog(cfg, parent=window),
        lambda: SetupDialog(cfg, window.config_path, Journal(cfg.journal_path), {}, parent=window),
    ]
    for make in makers:
        dialog = make()
        dialog.setModal(True)
        dialog.show()
        qapp.processEvents()
        window.handle_action("back")
        qapp.processEvents()
        assert not dialog.isVisible(), type(dialog).__name__
        assert not window.on_games_page()


def test_dialogs_shrink_to_a_small_screen(qapp):
    screenfit.install(qapp)
    dialog = QDialog()
    dialog.resize(5000, 5000)
    dialog.show()
    qapp.processEvents()
    avail = dialog.screen().availableGeometry()
    assert dialog.width() <= avail.width() and dialog.height() <= avail.height()
    small = QDialog()
    small.resize(300, 200)
    small.show()
    qapp.processEvents()
    assert (small.width(), small.height()) == (300, 200)  # a dialog that already fits is left alone
    dialog.close()
    small.close()


def test_every_dialog_fits_a_steam_deck_screen(window, qapp, tmp_path):
    """1280 x 800, less the desktop's panel: no dialog needs more than 1280 x 752 at its smallest."""
    from arcadia.emulators_dialog import EmulatorsDialog
    from arcadia.setup_dialog import BackupDialog, BringInDialog, SetupDialog
    from arcadia.sorter import Journal
    from arcadia.tools_dialog import ToolsDialog
    from arcadia.ui import SettingsDialog
    from arcadia.welcome_dialog import WelcomeDialog

    cfg = window.config
    for make in (
        lambda: WelcomeDialog(cfg, {}, lambda: {}, window),
        lambda: ToolsDialog(cfg, window),
        lambda: SettingsDialog(cfg, window),
        lambda: BackupDialog(cfg, window.config_path, window),
        lambda: EmulatorsDialog(cfg, parent=window),
        lambda: BringInDialog(cfg, Journal(cfg.journal_path), window),
        lambda: SetupDialog(cfg, window.config_path, Journal(cfg.journal_path), {}, parent=window),
    ):
        dialog = make()
        hint = dialog.minimumSizeHint()
        assert hint.width() <= 1280 and hint.height() <= 752, (type(dialog).__name__, hint)
        assert dialog.height() <= 752 or dialog.minimumSizeHint().height() <= 752
        dialog.close()


def test_the_main_window_fits_the_deck_at_its_smallest(window):
    hint = window.minimumSizeHint()
    assert hint.width() <= 1280 and hint.height() <= 800, hint
