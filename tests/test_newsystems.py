"""The extra systems: disc disambiguation, new header checks, folder games, presets."""

import os
import shutil
import struct
import time
from pathlib import Path

import pytest

import isoutil
import arcadia.sorter as sorter
from arcadia.config import Config, SystemConfig, default_systems
from arcadia.folders import find_game_folder, parse_meta_title, parse_sfo_title
from arcadia.launcher import build_command
from arcadia.library import Library
from arcadia.presets import PRESETS, RETROARCH_CORES
from arcadia.scanner import scan_system
from arcadia.sorter import Confidence, Journal, apply_plan, build_plan, hint_systems, identify

ALL = {s.id for s in default_systems()}


def put(path: Path, data: bytes = b"x", age=3600.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def config(tmp_path):
    return Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"), inbox_dir=str(tmp_path / "inbox"))


def system_of(path, known=ALL):
    ident = identify(path, known)
    return (ident.system_id, ident.confidence) if ident else None


# ======================= PlayStation: the original bug =======================

def test_a_ps2_iso_is_never_called_ps1(tmp_path):
    assert system_of(put(tmp_path / "Gran Turismo 4.iso", isoutil.ps2_disc())) == ("ps2", Confidence.CERTAIN)
    assert system_of(put(tmp_path / "Crash.iso", isoutil.psx_disc())) == ("psx", Confidence.CERTAIN)


def test_a_bare_playstation_marker_is_no_longer_certain(tmp_path):
    ident = identify(put(tmp_path / "Mystery.iso", isoutil.iso({}, system_id=b"PLAYSTATION")), ALL)
    assert ident.confidence is Confidence.UNSURE
    assert {ident.system_id, *ident.alternatives} >= {"psx", "ps2"}


def test_ps2_iso_is_not_mislabelled_when_the_user_has_no_ps2_setup(tmp_path):
    known = ALL - {"ps2"}
    assert identify(put(tmp_path / "GT4.iso", isoutil.ps2_disc()), known) is None  # left alone, not sent to PS1


def test_an_unrecognised_iso_asks_with_a_sensible_default(tmp_path):
    ident = identify(put(tmp_path / "data.iso", isoutil.iso({"X.TXT;1": b"x"}, system_id=b"DATA")), ALL)
    assert ident.confidence is Confidence.UNSURE and ident.system_id == "ps2"
    assert {ident.system_id, *ident.alternatives} == {"ps2", "psx", "psp", "gc", "wii", "xbox", "ps3", "saturn", "segacd"}


def test_the_name_picks_the_default_for_an_unrecognised_iso(tmp_path):
    ident = identify(put(tmp_path / "Zelda (Wii).iso", isoutil.iso({"X;1": b"x"}, system_id=b"DATA")), ALL)
    assert ident.system_id == "wii"


@pytest.mark.parametrize(
    "name, data, system",
    [
        ("PS3 Game.iso", isoutil.ps3_disc(), "ps3"),
        ("PSP Game.iso", isoutil.psp_disc(), "psp"),
        ("Halo.iso", bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA" + bytes(100), "xbox"),
        ("Melee.iso", bytes(0x1C) + bytes.fromhex("C2339F3D") + bytes(0x100), "gc"),
        ("Brawl.iso", bytes(0x18) + bytes.fromhex("5D1C9EA3") + bytes(0x104), "wii"),
        ("Brawl.wbfs", b"WBFS" + bytes(100), "wii"),
        ("PSP Game.cso", isoutil.cso(isoutil.psp_disc()), "psp"),
        ("GT4.cso", isoutil.cso(isoutil.ps2_disc()), "ps2"),
        ("Saturn Game.iso", isoutil.iso(sector0=b"SEGA SEGASATURN " + bytes(60), system_id=b"SEGA"), "saturn"),
    ],
)
def test_disc_images_are_identified_with_certainty(tmp_path, name, data, system):
    assert system_of(put(tmp_path / name, data)) == (system, Confidence.CERTAIN)


def test_rvz_and_wia_are_read_through_their_wrapper(tmp_path):
    gc = b"RVZ\x01" + bytes(0x54) + bytes(0x1C) + bytes.fromhex("C2339F3D") + bytes(0x100)
    assert system_of(put(tmp_path / "Melee.rvz", gc)) == ("gc", Confidence.CERTAIN)
    ident = identify(put(tmp_path / "Mystery.rvz", b"RVZ\x01" + bytes(0x200)), ALL)
    assert ident.confidence is Confidence.UNSURE and {ident.system_id, *ident.alternatives} == {"gc", "wii"}


def test_bare_cso_and_zso(tmp_path):
    ident = identify(put(tmp_path / "Unreadable.cso", b"CISO" + bytes(100)), ALL)
    assert ident.confidence is Confidence.UNSURE and ident.system_id == "psp"
    assert ident.alternatives == ["ps2"]
    assert system_of(put(tmp_path / "Game.zso", b"ZISO" + bytes(100))) == ("ps2", Confidence.LIKELY)


# ======================= new cartridge and file headers =======================

def nds():
    data = bytearray(0x200)
    data[0x15C:0x15E] = b"\x56\xcf"
    return bytes(data)


@pytest.mark.parametrize(
    "name, data, system",
    [
        ("Mario.nds", nds(), "nds"),
        ("Zelda.3ds", bytes(0x100) + b"NCSD" + bytes(100), "n3ds"),
        ("Zelda.cxi", bytes(0x100) + b"NCCH" + bytes(100), "n3ds"),
        ("Zelda.cia", bytes.fromhex("2020000000000000") + bytes(100), "n3ds"),
        ("Homebrew.3dsx", b"3DSX" + bytes(100), "n3ds"),
        ("Mario Kart.wux", b"WUX0" + bytes(100), "wiiu"),
        ("Mario Kart.wud", b"WUP-P-AXXX" + bytes(100), "wiiu"),
        ("Pitfall.a78", b"\x01ATARI7800" + bytes(100), "atari7800"),
        ("Gauntlet.lnx", b"LYNX" + bytes(100), "lynx"),
        ("Sonic.ngp", b"COPYRIGHT BY SNK CORPORATION" + bytes(100), "ngp"),
        ("Pocket.ngc", b"LICENSED BY SNK CORPORATION" + bytes(100), "ngp"),
    ],
)
def test_new_headers_identify_with_certainty(tmp_path, name, data, system):
    assert system_of(put(tmp_path / name, data)) == (system, Confidence.CERTAIN)


@pytest.mark.parametrize(
    "name, system",
    [("Game.wua", "wiiu"), ("Game.pce", "pcengine"), ("Game.a26", "atari2600"), ("Game.ws", "wonderswan"),
     ("Game.vb", "virtualboy"), ("Game.neo", "neogeo"), ("Game.adf", "amiga"), ("Game.cdi", "dreamcast"),
     ("Game.mx1", "msx"), ("Game.xiso", "xbox")],
)
def test_unique_extensions_are_likely_when_nothing_can_be_checked(tmp_path, name, system):
    assert system_of(put(tmp_path / name, b"unverifiable")) == (system, Confidence.LIKELY)


def test_rom_and_other_shared_extensions_need_the_name_to_say_so(tmp_path):
    assert identify(put(tmp_path / "BIOS.rom", bytes(100)), ALL) is None
    assert identify(put(tmp_path / "disk.dsk", bytes(100)), ALL) is None
    ident = identify(put(tmp_path / "Nemesis (MSX).rom", bytes(100)), ALL)
    assert (ident.system_id, ident.confidence) == ("msx", Confidence.UNSURE)


# ======================= CHD =======================

def chd(tag):
    head = bytearray(0x80)
    head[:8] = b"MComprHD"
    head[8:12] = struct.pack(">I", 124)
    head[12:16] = struct.pack(">I", 5)
    head[0x30:0x38] = struct.pack(">Q", 0x80)
    return bytes(head) + tag + bytes(12)


def test_chd_kind_narrows_the_choices(tmp_path):
    gd = identify(put(tmp_path / "Shenmue.chd", chd(b"CHGD")), ALL)
    assert (gd.system_id, gd.confidence) == ("dreamcast", Confidence.LIKELY)
    cd = identify(put(tmp_path / "Game.chd", chd(b"CHT2")), ALL)
    assert cd.confidence is Confidence.UNSURE and {cd.system_id, *cd.alternatives} == {"psx", "ps2", "saturn", "segacd", "pcengine"}
    dvd = identify(put(tmp_path / "Dvd.chd", chd(b"DVD ")), ALL)
    assert {dvd.system_id, *dvd.alternatives} == {"ps2", "psp"}  # Dolphin and xemu can't open CHD files
    named = identify(put(tmp_path / "Virtua Fighter (Saturn).chd", chd(b"CHT2")), ALL)
    assert named.system_id == "saturn"  # the name picks the default among the candidates


# ======================= cue and gdi sheets =======================

def put_cue(folder, name, image):
    put(folder / f"{name}.cue", f'FILE "{name}.bin" BINARY\n'.encode())
    put(folder / f"{name}.bin", image)


def test_cue_images_are_identified_by_their_data_track(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_cue(inbox, "Gran Turismo 3", isoutil.ps2_disc())
    put_cue(inbox, "Crash", isoutil.psx_disc((2352, 24)))
    put_cue(inbox, "Panzer Dragoon", isoutil.iso(sector0=b"SEGA SEGASATURN " + bytes(60), layout=(2352, 16)))
    put_cue(inbox, "Mystery", isoutil.iso({"X;1": b"x"}, system_id=b"DATA"))
    items = {i.source.stem: i for i in build_plan(inbox, config).items}
    assert [(items[n].system_id, items[n].confidence) for n in ("Gran Turismo 3", "Crash", "Panzer Dragoon")] == [
        ("ps2", Confidence.CERTAIN), ("psx", Confidence.CERTAIN), ("saturn", Confidence.CERTAIN)
    ]
    assert items["Mystery"].confidence is Confidence.UNSURE


def make_gdi(folder, name, with_ip_bin):
    put(folder / f"{name}.gdi", f'3\n1 0 4 2352 track01.bin 0\n2 600 0 2352 "track02.raw" 0\n3 45000 4 2352 track03.bin 0\n'.encode())
    put(folder / "track01.bin", bytes(0x10000))
    put(folder / "track02.raw", bytes(0x10000))
    ip = isoutil.iso(sector0=b"SEGA SEGAKATANA SEGA ENTERPRISES" + bytes(50), layout=(2352, 16)) if with_ip_bin else bytes(0x10000)
    put(folder / "track03.bin", ip)


def test_gdi_sheet_moves_with_its_tracks_and_dreamcast_is_confirmed(tmp_path, config):
    inbox = tmp_path / "inbox"
    make_gdi(inbox, "Sonic Adventure", with_ip_bin=True)
    plan = build_plan(inbox, config)
    (item,) = plan.items  # the track files are not offered on their own
    assert (item.system_id, item.confidence) == ("dreamcast", Confidence.CERTAIN)
    assert sorted(c.name for c in item.companions) == ["track01.bin", "track02.raw", "track03.bin"]

    apply_plan(plan.items, Journal(config.journal_path))
    moved = sorted(p.name for p in (tmp_path / "roms" / "dreamcast").iterdir())
    assert moved == ["Sonic Adventure.gdi", "track01.bin", "track02.raw", "track03.bin"]
    assert list(inbox.iterdir()) == []


def test_gdi_without_a_verifiable_data_track_is_likely_and_missing_tracks_ask(tmp_path, config):
    inbox = tmp_path / "inbox"
    make_gdi(inbox, "Unverified", with_ip_bin=False)
    (item,) = build_plan(inbox, config).items
    assert (item.system_id, item.confidence) == ("dreamcast", Confidence.LIKELY)
    (inbox / "track03.bin").unlink()
    (item,) = build_plan(inbox, config).items
    assert item.confidence is Confidence.UNSURE and "track03.bin" in item.reason


# ======================= zips and names =======================

def test_an_arcade_zip_is_recognised_only_by_name(tmp_path):
    import zipfile

    z = tmp_path / "mame roms.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.bin", b"x")
        zf.writestr("b.bin", b"y")
    ident = identify(z, ALL)
    assert (ident.system_id, ident.confidence) == ("arcade", Confidence.UNSURE)
    plain = tmp_path / "stuff.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("a.bin", b"x")
    assert identify(plain, ALL) is None


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Zelda (Wii U)", ["wiiu"]),
        ("Zelda (Wii)", ["wii"]),
        ("Zelda GameCube", ["gc"]),
        ("Pokemon 3DS", ["n3ds"]),
        ("Pokemon Nintendo DS", ["nds"]),
        ("GT4 (PS2)", ["ps2"]),
        ("TLOU PS3", ["ps3"]),
        ("Samba de Amigo Dreamcast", ["dreamcast"]),
        ("Sega Saturn Collection", ["saturn"]),
        ("Neo Geo Pocket Color Pack", ["ngp"]),
        ("Metal Slug Neo Geo", ["neogeo"]),
        ("Xenon 2 Amiga", ["amiga"]),
        ("Gradius MSX", ["msx"]),
        ("PC Engine Games", ["pcengine"]),
    ],
)
def test_new_name_hints(name, expected):
    assert hint_systems(name, ALL) == expected


# ======================= playlists only where the emulator can use them =======================

def put_iso_disc(folder, name):
    put(folder / f"{name}.iso", isoutil.ps2_disc())


def test_ps2_discs_are_not_joined_into_a_playlist_pcsx2_cannot_open(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_iso_disc(inbox, "Final Fantasy X-2 (Disc 1)")
    put_iso_disc(inbox, "Final Fantasy X-2 (Disc 2)")
    plan = build_plan(inbox, config)
    assert [i.kind for i in plan.items] == ["single", "single"] and all(i.system_id == "ps2" for i in plan.items)
    assert all(i.confidence is Confidence.CERTAIN for i in plan.items)  # no "lone disc" warning either


def test_saturn_discs_are_joined(tmp_path, config):
    inbox = tmp_path / "inbox"
    for n in (1, 2):
        put_cue(inbox, f"Panzer Dragoon Saga (Disc {n})", isoutil.iso(sector0=b"SEGA SEGASATURN " + bytes(60)))
    (item,) = build_plan(inbox, config).items
    assert item.kind == "disc_set" and item.system_id == "saturn" and item.detail == "2 discs"


# ======================= folder games =======================

def build_sfo(title: str) -> bytes:
    key = b"TITLE\x00"
    value = title.encode().ljust(64, b"\x00")
    key_table = 20 + 16
    data_table = key_table + len(key)
    header = struct.pack("<4sIIII", b"\x00PSF", 0x101, key_table, data_table, 1)
    entry = struct.pack("<HHIII", 0, 0x0204, len(title.encode()) + 1, 64, 0)
    return header + entry + key + value


def age_tree(folder: Path, age=3600.0):
    """Make a folder and everything in it look like it was finished a while ago."""
    stamp = time.time() - age
    for dirpath, dirnames, filenames in os.walk(folder, topdown=False):
        for name in filenames + dirnames:
            os.utime(os.path.join(dirpath, name), (stamp, stamp))
        os.utime(dirpath, (stamp, stamp))


def make_ps3_game(folder: Path, title="Demon's Souls", sfo=True):
    put(folder / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", b"\x7fSELF" + bytes(1000))
    put(folder / "PS3_GAME" / "USRDIR" / "data.pkg", bytes(5000))
    if sfo:
        put(folder / "PS3_GAME" / "PARAM.SFO", build_sfo(title))
    age_tree(folder)


def make_wiiu_game(folder: Path, title="Super Mario 3D World"):
    put(folder / "code" / "game.rpx", b"\x7fELF" + bytes(500))
    put(folder / "content" / "a.bin", bytes(2000))
    put(folder / "meta" / "meta.xml", f'<menu><longname_en type="string">{title}\n&amp; Bowser</longname_en></menu>'.encode())
    age_tree(folder)


def test_titles_come_from_the_games_own_metadata(tmp_path):
    ps3 = tmp_path / "BLUS30443"
    make_ps3_game(ps3)
    marker, title = find_game_folder(ps3, "ps3")
    assert marker == ps3 / "PS3_GAME" / "USRDIR" / "EBOOT.BIN" and title == "Demon's Souls"

    wiiu = tmp_path / "AMKE01"
    make_wiiu_game(wiiu)
    marker, title = find_game_folder(wiiu, "wiiu")
    assert marker == wiiu / "code" / "game.rpx" and title == "Super Mario 3D World & Bowser"


def test_the_folder_name_is_the_fallback_title(tmp_path):
    ps3 = tmp_path / "BLUS12345"
    make_ps3_game(ps3, sfo=False)
    assert find_game_folder(ps3, "ps3")[1] == "BLUS12345"
    (ps3 / "PS3_GAME" / "PARAM.SFO").write_bytes(b"garbage")
    assert find_game_folder(ps3, "ps3")[1] == "BLUS12345"


def test_sfo_and_meta_parsers_handle_bad_input(tmp_path):
    assert parse_sfo_title(tmp_path / "missing.sfo") is None
    assert parse_sfo_title(put(tmp_path / "a.sfo", b"\x00PSF")) is None
    assert parse_meta_title(tmp_path / "missing.xml") is None
    assert parse_meta_title(put(tmp_path / "b.xml", b"<menu></menu>")) is None
    assert parse_meta_title(put(tmp_path / "c.xml", b"<shortname_en>Short</shortname_en>")) == "Short"


def test_folders_that_are_not_games_are_not_games(tmp_path):
    (tmp_path / "Photos").mkdir()
    put(tmp_path / "Photos" / "a.jpg")
    assert find_game_folder(tmp_path / "Photos", "ps3") is None
    assert find_game_folder(tmp_path / "Photos", "switch") is None  # no folder rule for this system
    assert find_game_folder(tmp_path / "nope", "ps3") is None


def test_scanner_treats_a_whole_folder_as_one_game(tmp_path, config):
    ps3 = tmp_path / "roms" / "ps3"
    make_ps3_game(ps3 / "BLUS30443")
    make_ps3_game(ps3 / "Category" / "BCES00001", title="Uncharted")  # nested one level down
    put(ps3 / "Disc Game.iso", isoutil.ps3_disc())
    games = scan_system(tmp_path / "roms", config.system("ps3"))
    assert sorted(g.title for g in games) == ["Demon's Souls", "Disc Game", "Uncharted"]  # no entries for the files inside
    launch = {g.title: g.path for g in games}
    assert launch["Demon's Souls"].name == "EBOOT.BIN"

    lib = Library(tmp_path / "lib.db")
    lib.sync("ps3", games)
    assert lib.count("ps3") == 3
    lib.close()


def test_scanner_finds_wiiu_loadiine_folders_next_to_wua_files(tmp_path, config):
    wiiu = tmp_path / "roms" / "wiiu"
    make_wiiu_game(wiiu / "AMKE01")
    put(wiiu / "Bayonetta 2.wua", b"zarchive")
    games = {g.title: g for g in scan_system(tmp_path / "roms", config.system("wiiu"))}
    assert set(games) == {"Super Mario 3D World & Bowser", "Bayonetta 2"}
    assert games["Super Mario 3D World & Bowser"].path.suffix == ".rpx"


def test_a_ps3_folder_in_downloads_is_one_certain_item_and_moves_whole(tmp_path, config):
    inbox = tmp_path / "inbox"
    make_ps3_game(inbox / "BLUS30443")
    (inbox / "Holiday Photos").mkdir()
    put(inbox / "Holiday Photos" / "a.jpg")

    plan = build_plan(inbox, config)
    (item,) = plan.items  # the photo folder isn't mentioned at all
    assert (item.system_id, item.confidence, item.detail) == ("ps3", Confidence.CERTAIN, "game folder")
    assert item.source.name == "BLUS30443" and item.dest_label() == "ps3/"
    assert plan.ignored == []

    journal = Journal(config.journal_path)
    result = apply_plan(plan.items, journal)
    assert len(result.moved) == 1
    moved = tmp_path / "roms" / "ps3" / "BLUS30443"
    assert (moved / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").exists() and not (inbox / "BLUS30443").exists()
    assert (inbox / "Holiday Photos").exists()

    restored, problems = journal.undo_last()
    assert problems == [] and (inbox / "BLUS30443" / "PS3_GAME" / "PARAM.SFO").exists() and not moved.exists()


def test_a_folder_still_being_copied_is_left_alone(tmp_path, config):
    inbox = tmp_path / "inbox"
    make_ps3_game(inbox / "BLUS30443")
    put(inbox / "BLUS30443" / "PS3_GAME" / "USRDIR" / "big.bin", bytes(10), age=0)  # a file just written (also touches the folder)
    plan = build_plan(inbox, config)
    assert plan.items == [] and [p.name for p in plan.waiting] == ["BLUS30443"]


def test_a_folder_that_already_exists_in_the_library_is_not_overwritten(tmp_path, config):
    inbox = tmp_path / "inbox"
    make_ps3_game(inbox / "BLUS30443")
    existing = tmp_path / "roms" / "ps3" / "BLUS30443"
    put(existing / "keep.txt", b"precious")
    plan = build_plan(inbox, config)
    assert plan.items[0].exists is True
    result = apply_plan(plan.items, Journal(config.journal_path))
    assert result.moved == [] and (existing / "keep.txt").read_bytes() == b"precious" and (inbox / "BLUS30443").exists()


def test_moving_a_folder_across_drives_copies_verifies_then_removes(tmp_path, monkeypatch):
    src = tmp_path / "src" / "Game"
    make_ps3_game(src)
    real = os.rename
    monkeypatch.setattr(os, "rename", lambda a, b: (_ for _ in ()).throw(OSError(18, "Invalid cross-device link")))
    dst = tmp_path / "dst" / "Game"
    sorter.safe_move(src, dst)
    monkeypatch.setattr(os, "rename", real)
    assert (dst / "PS3_GAME" / "USRDIR" / "data.pkg").stat().st_size == 5000
    assert not src.exists()
    assert not list((tmp_path / "dst").glob("*.arcadia-part"))


def test_an_incomplete_cross_drive_copy_keeps_the_original(tmp_path, monkeypatch):
    src = tmp_path / "src" / "Game"
    make_ps3_game(src)
    monkeypatch.setattr(os, "rename", lambda a, b: (_ for _ in ()).throw(OSError(18, "xdev")))

    def lossy_copy(s, d, symlinks=False):
        os.makedirs(d)
        Path(d, "only.txt").write_bytes(b"1")  # most of the game is missing

    monkeypatch.setattr(shutil, "copytree", lossy_copy)
    with pytest.raises(sorter.SortError):
        sorter.safe_move(src, tmp_path / "dst" / "Game")
    assert (src / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").exists()  # nothing was deleted
    assert not (tmp_path / "dst" / "Game").exists()
    assert not list((tmp_path / "dst").glob("*.arcadia-part"))


# ======================= launch placeholders =======================

def test_stem_and_dir_placeholders_for_mame():
    args = build_command(PRESETS["arcade"].command.replace("flatpak run org.mamedev.MAME", "mame"), Path("/roms/arcade/Street Fighter II.zip"))
    assert args == ["mame", "-rompath", "/roms/arcade", "Street Fighter II"]  # the path is not appended a second time


def test_a_template_with_only_rom_still_works_and_stem_alone_does_not_append():
    assert build_command("emu {rom}", Path("/r/A B.nes")) == ["emu", "/r/A B.nes"]
    assert build_command("emu --name {stem}", Path("/r/A B.nes")) == ["emu", "--name", "A B"]
    assert build_command("emu", Path("/r/A.nes")) == ["emu", "/r/A.nes"]


# ======================= the system and preset tables =======================

def test_every_system_has_a_preset_and_every_preset_a_system():
    systems = {s.id for s in default_systems()}
    assert systems == set(PRESETS)
    assert len(systems) == 34


def test_every_preset_command_parses_and_launches_something():
    for system in default_systems():
        args = build_command(system.command, Path(f"/roms/{system.folder}/Game Name.ext"))
        assert args[0] in ("flatpak",), (system.id, args)
        assert "Game Name" in " ".join(args), system.id


def test_retroarch_presets_name_real_core_files():
    for sid, preset in PRESETS.items():
        if preset.label.startswith("RetroArch"):
            core = preset.command.split(RETROARCH_CORES + "/")[1].split()[0]
            assert core.endswith("_libretro.so"), sid


def test_system_folders_and_ids_are_unique():
    systems = default_systems()
    assert len({s.id for s in systems}) == len(systems)
    assert len({s.folder for s in systems}) == len(systems)


def test_old_configs_gain_every_new_system_without_losing_edits(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"rom_root": "/games", "systems": [{"id": "psx", "name": "PS1", "folder": "ps1", "extensions": [".cue"], "command": "my-duck {rom}", "save_dir": ""}]}')
    cfg = Config.load(path)
    ids = [s.id for s in cfg.systems]
    assert ids[0] == "psx" and len(ids) == 34
    assert cfg.system("psx").command == "my-duck {rom}" and cfg.system("psx").folder == "ps1"
    assert {"gc", "wii", "ps2", "ps3", "dreamcast", "n3ds", "nds", "wiiu", "xbox", "arcade"} <= set(ids)
