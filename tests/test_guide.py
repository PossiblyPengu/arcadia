"""The Get started checklist and the empty-shelf messages."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

import arcadia.setup_dialog as setup_dialog  # noqa: E402
import arcadia.welcome_dialog as welcome_dialog  # noqa: E402
from arcadia import guide  # noqa: E402
from arcadia.config import Config  # noqa: E402
from arcadia.library import Library  # noqa: E402
from arcadia.ui import MainWindow  # noqa: E402
from arcadia.welcome_dialog import WelcomeDialog  # noqa: E402
from qtutil import SyncTask  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def facts(**kw):
    base = dict(games=0, local_emulators=0, flatpak_emulators=0, systems_missing_bios=0, rclone=False, remotes=())
    base.update(kw)
    return guide.Facts(**base)


def steps(config, **kw):
    return {s.key: s for s in guide.build_steps(config, facts(**kw))}


def test_a_new_setup_needs_games_and_emulators(tmp_path):
    config = Config.new_install(tmp_path / "A")
    s = steps(config)
    assert s["folder"].done and not s["games"].done and not s["emulators"].done
    assert not guide.required_done(list(s.values()))
    assert s["bios"].optional and s["sync"].optional
    assert "Check this once your games are in" in s["bios"].detail


def test_progress_is_read_from_the_facts(tmp_path):
    config = Config.new_install(tmp_path / "A")
    s = steps(config, games=3, local_emulators=1, flatpak_emulators=2)
    assert s["games"].done and "3 games" in s["games"].detail
    assert s["emulators"].done and "1 emulator installed" in s["emulators"].detail and "2 Flatpak emulators" in s["emulators"].detail
    assert guide.required_done(list(s.values()))
    assert steps(config, games=1)["games"].detail == "1 game in your library."


def test_bios_step_only_counts_systems_you_have_games_for(tmp_path):
    config = Config.new_install(tmp_path / "A")
    assert not steps(config, games=5, systems_missing_bios=2)["bios"].done
    assert "2 systems" in steps(config, games=5, systems_missing_bios=2)["bios"].detail
    assert steps(config, games=5)["bios"].done


def test_sync_step_explains_each_situation(tmp_path):
    config = Config.new_install(tmp_path / "A")  # default remote gdrive:Arcadia
    assert "install rclone" in steps(config)["sync"].detail
    assert "rclone config" in steps(config, rclone=True)["sync"].detail
    odd = steps(config, rclone=True, remotes=("dropbox:",))["sync"]
    assert not odd.done and "no remote called “gdrive”" in odd.detail and "dropbox:" in odd.detail
    ok = steps(config, rclone=True, remotes=("gdrive:",))["sync"]
    assert ok.done and "gdrive:Arcadia" in ok.detail


def test_gather_reads_real_state(tmp_path, monkeypatch):
    config = Config.new_install(tmp_path / "A")
    config.ensure_layout()
    monkeypatch.setattr(guide, "installed_flatpaks", lambda: {"org.DolphinEmu.dolphin-emu"})
    monkeypatch.setattr(guide.shutil, "which", lambda _n: None)
    f = guide.gather(config, {"psx": 4, "gc": 1})
    assert f.games == 5 and f.flatpak_emulators == 1 and f.local_emulators == 0
    assert f.systems_missing_bios == 1 and not f.rclone  # PlayStation has games and no BIOS; GameCube needs none


# ----- the window -----

@pytest.fixture
def dialog(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(setup_dialog, "TaskClass", SyncTask)
    monkeypatch.setattr(guide, "installed_flatpaks", lambda: set())
    monkeypatch.setattr(guide.shutil, "which", lambda _n: None)
    config = Config.new_install(tmp_path / "A")
    config.ensure_layout()
    calls = []
    counts = {"games": 0}
    d = WelcomeDialog(config, {k: (lambda k=k: calls.append(k)) for k in ("folder", "games", "emulators", "bios", "sync")}, lambda: {"nes": counts["games"]})
    d.calls, d.counts_box = calls, counts
    return d


def test_checklist_shows_state_and_buttons_run_their_action_then_recheck(dialog):
    assert dialog.cards["folder"][0].text() == "✓" and dialog.cards["games"][0].text() == "•"
    assert "add your games" in dialog.summary.text()
    dialog.counts_box["games"] = 2  # what the "add games" action will have achieved
    dialog.cards["games"][3].click()
    assert dialog.calls == ["games"]
    assert dialog.cards["games"][0].text() == "✓" and "2 games" in dialog.cards["games"][2].text()


# ----- empty shelf -----

@pytest.fixture
def window(qapp, tmp_path):
    config = Config.new_install(tmp_path / "A")
    config.ensure_layout()
    win = MainWindow(config, tmp_path / "config.json", Library(config.db_path))
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_an_empty_library_welcomes_and_offers_the_checklist(window):
    assert window.console_empty.isVisible() and not window.grid_holder.isVisible()
    assert window.console_empty.title.text() == "Welcome to Arcadia"
    assert [b.text() for b in window.console_empty.buttons] == ["Get started", "Import ROMs…"]


def test_an_empty_system_or_search_says_why(window, tmp_path):
    rom = window.config.rom_root_path / "nes" / "Contra.nes"
    rom.write_text("x")
    window.rescan()
    window.show_games()
    window.search.setText("zzz")
    assert window.empty.isVisible() and "zzz" in window.empty.title.text()
    assert [b.text() for b in window.empty.buttons] == ["Clear search"]
    window.empty.buttons[0].click()
    assert window.coverflow.isVisible() and not window.empty.isVisible()


def test_favorites_and_recent_have_their_own_messages(window):
    from arcadia.ui import VIEW_FAVORITES, VIEW_RECENT

    (window.config.rom_root_path / "nes" / "Contra.nes").write_text("x")
    window.rescan()  # a library with a game in it, so the welcome message isn't what's shown
    window._update_empty_state(VIEW_FAVORITES, False)
    assert window.empty.title.text() == "No favorites yet"
    window._update_empty_state(VIEW_RECENT, False)
    assert window.empty.title.text() == "Nothing played yet"
    window._update_empty_state("nes", True)
    assert not window.empty.isVisible()
