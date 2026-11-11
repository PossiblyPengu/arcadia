from pathlib import Path

import pytest

from arcadia.config import Config, SystemConfig, default_systems
from arcadia.launcher import LaunchError, build_command
from arcadia.library import Library
from arcadia.metadata import load_metadata
from arcadia.savestates import SaveStateError, create_snapshot, list_snapshots, restore_snapshot
from arcadia.scanner import clean_title, scan_system
from arcadia.util import fmt_duration


# ---------- titles ----------

@pytest.mark.parametrize(
    "stem, expected",
    [
        ("Super Mario World (USA)", "Super Mario World"),
        ("Legend of Zelda, The (USA) [!]", "The Legend of Zelda"),
        ("Game   Name  (Europe) (Rev 1)", "Game Name"),
        ("Plain", "Plain"),
        ("(USA)", "(USA)"),  # never returns an empty title
    ],
)
def test_clean_title(stem, expected):
    assert clean_title(stem) == expected


# ---------- scanning ----------

def test_scan_filters_by_extension_and_skips_hidden(tmp_path):
    root = tmp_path / "roms"
    (root / "snes").mkdir(parents=True)
    (root / "snes" / "A Game (USA).sfc").write_text("x")
    (root / "snes" / "B Game.SMC").write_text("x")
    (root / "snes" / "notes.txt").write_text("x")
    (root / "snes" / ".hidden.sfc").write_text("x")
    system = SystemConfig(id="snes", name="SNES", folder="snes", extensions=[".sfc", "smc"])

    games = scan_system(root, system)

    assert [g.title for g in games] == ["A Game", "B Game"]
    assert all(g.system_id == "snes" for g in games)


def test_scan_missing_folder_returns_empty(tmp_path):
    system = SystemConfig(id="nes", name="NES", folder="nes", extensions=[".nes"])
    assert scan_system(tmp_path, system) == []


# ---------- library ----------

def _games(tmp_path):
    root = tmp_path / "roms"
    (root / "nes").mkdir(parents=True)
    (root / "nes" / "One (USA).nes").write_text("x")
    (root / "nes" / "Two.nes").write_text("x")
    system = SystemConfig(id="nes", name="NES", folder="nes", extensions=[".nes"])
    return root, system


def test_library_sync_favorites_and_playtime(tmp_path):
    root, system = _games(tmp_path)
    lib = Library(tmp_path / "lib.db")
    lib.sync(system.id, scan_system(root, system))
    assert lib.count("nes") == 2

    key = str(root / "nes" / "One (USA).nes")
    lib.set_favorite(key, True)
    lib.record_session(key, 1000.0, 90)
    lib.record_session(key, 2000.0, 30)

    row = lib.get(key)
    assert row["favorite"] == 1
    assert row["play_count"] == 2
    assert row["total_seconds"] == 120
    assert row["last_played"] == 2030.0
    assert len(lib.sessions(key)) == 2
    assert [r["title"] for r in lib.games("nes", favorites_only=True)] == ["One"]
    lib.close()


def test_missing_games_keep_their_data(tmp_path):
    root, system = _games(tmp_path)
    lib = Library(tmp_path / "lib.db")
    lib.sync(system.id, scan_system(root, system))
    key = str(root / "nes" / "Two.nes")
    lib.set_favorite(key, True)
    lib.record_session(key, 500.0, 60)

    # Simulate an unplugged drive: nothing found on disk.
    lib.sync(system.id, [])
    assert lib.count("nes") == 0
    assert lib.games("nes") == []

    # Drive comes back: favorite and playtime are still there.
    lib.sync(system.id, scan_system(root, system))
    row = lib.get(key)
    assert row["favorite"] == 1
    assert row["total_seconds"] == 60
    lib.close()


# ---------- launcher ----------

def test_build_command_quotes_rom_path():
    rom = Path("/roms/snes/A Game (USA).sfc")
    args = build_command("retroarch -L /cores/snes9x.so {rom}", rom)
    assert args == ["retroarch", "-L", "/cores/snes9x.so", str(rom)]


def test_build_command_appends_rom_when_placeholder_missing():
    args = build_command("flatpak run org.example.Emu", Path("/roms/x.nes"))
    assert args[-1] == "/roms/x.nes"


def test_build_command_rejects_empty_template():
    with pytest.raises(LaunchError):
        build_command("   ", Path("/roms/x.nes"))


def test_build_command_rejects_unbalanced_quotes():
    with pytest.raises(LaunchError):
        build_command('emu "unclosed {rom}', Path("/roms/x.nes"))


# ---------- save states ----------

def test_snapshot_round_trip(tmp_path):
    rom = tmp_path / "roms" / "Game.sfc"
    rom.parent.mkdir()
    rom.write_text("rom")
    saves = tmp_path / "saves"
    saves.mkdir()
    (saves / "Game.srm").write_text("save-v1")
    (saves / "Game.state1").write_text("state-v1")
    (saves / "GameOther.srm").write_text("unrelated")
    states = tmp_path / "states"

    snap = create_snapshot(saves, rom, states)
    assert sorted(p.name for p in snap.iterdir()) == ["Game.srm", "Game.state1"]

    (saves / "Game.srm").write_text("save-v2")
    restore_snapshot(snap, saves, rom, states)
    assert (saves / "Game.srm").read_text() == "save-v1"
    # Restoring created an automatic backup of the newer state.
    assert len(list_snapshots(states, rom)) == 2
    assert (saves / "GameOther.srm").read_text() == "unrelated"


def test_snapshot_without_saves_raises(tmp_path):
    rom = tmp_path / "Game.sfc"
    with pytest.raises(SaveStateError):
        create_snapshot(tmp_path / "empty", rom, tmp_path / "states")


# ---------- metadata ----------

def test_metadata_sidecar_and_cover(tmp_path):
    media = tmp_path / "media" / "snes"
    media.mkdir(parents=True)
    (media / "Game.json").write_text('{"title": "Game Deluxe", "year": 1994, "genre": "RPG"}')
    (media / "Game.png").write_bytes(b"png")
    meta = load_metadata(tmp_path / "media", "snes", Path("/roms/Game.sfc"))
    assert meta.title == "Game Deluxe"
    assert meta.year == "1994"
    assert meta.genre == "RPG"
    assert meta.cover == media / "Game.png"


def test_metadata_bad_json_is_ignored(tmp_path):
    media = tmp_path / "snes"
    media.mkdir()
    (media / "Game.json").write_text("{not json")
    meta = load_metadata(tmp_path, "snes", Path("/roms/Game.sfc"))
    assert meta.title == "" and meta.cover is None


# ---------- config & util ----------

def test_config_round_trip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(rom_root="/games", systems=[SystemConfig("nes", "NES", "nes", [".nes"], command="emu {rom}")])
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.rom_root == "/games"
    assert loaded.system("nes").command == "emu {rom}"


def test_config_missing_file_gives_defaults(tmp_path):
    cfg = Config.load(tmp_path / "nope.json")
    assert [s.id for s in cfg.systems] == [s.id for s in default_systems()]


def test_default_systems_include_sega_and_psp_with_presets():
    systems = {s.id: s for s in default_systems()}
    for sid in ["nes", "snes", "gb", "gbc", "gba", "n64", "genesis", "sms", "gamegear", "psx", "psp"]:
        assert sid in systems, sid
        assert systems[sid].command, f"{sid} has no launch preset"
        build_command(systems[sid].command, Path("/roms/x.bin"))  # every preset parses


def test_load_adds_newly_defined_systems_to_old_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"rom_root": "/games", "systems": [{"id": "nes", "name": "NES", "folder": "nes", "extensions": [".nes"], "command": "emu {rom}", "save_dir": ""}]}')
    cfg = Config.load(path)
    ids = [s.id for s in cfg.systems]
    assert ids[0] == "nes"
    assert cfg.system("nes").command == "emu {rom}"  # user's command kept
    assert "psp" in ids and "sms" in ids


def test_build_command_expands_home_in_arguments():
    args = build_command("retroarch -L ~/cores/x.so {rom}", Path("/roms/x.nes"))
    assert args[2].startswith("/") and "~" not in args[2]


@pytest.mark.parametrize("seconds, expected", [(5, "5s"), (125, "2m"), (3725, "1h 02m")])
def test_fmt_duration(seconds, expected):
    assert fmt_duration(seconds) == expected
