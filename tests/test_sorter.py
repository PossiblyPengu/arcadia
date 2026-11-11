import os
import struct
import zipfile
from pathlib import Path

import pytest

import isoutil

from arcadia.config import Config
from arcadia.sorter import (
    Confidence,
    Journal,
    SortError,
    apply_plan,
    build_plan,
    cue_files,
    hint_systems,
    identify,
    safe_move,
    unique_destination,
)

ALL = {"nes", "snes", "gb", "gbc", "gba", "n64", "genesis", "sms", "gamegear", "psx", "psp"}


# ---------- synthetic ROMs ----------

def nes():
    return b"NES\x1a" + bytes(0x4000)


def gba():
    data = bytearray(0x400)
    data[4:12] = bytes.fromhex("24FFAE51699AA221")
    data[0xB2] = 0x96
    return bytes(data)


def gb(flag=0x00):
    data = bytearray(0x200)
    data[0x104:0x10C] = bytes.fromhex("CEED6666CC0D000B")
    data[0x143] = flag
    return bytes(data)


def n64(magic="80371240"):
    return bytes.fromhex(magic) + bytes(0x100)


def genesis():
    data = bytearray(0x300)
    data[0x100:0x110] = b"SEGA MEGA DRIVE "
    return bytes(data)


def sega8(region_nibble):
    data = bytearray(0x8000)
    data[0x7FF0:0x7FF8] = b"TMR SEGA"
    data[0x7FFF] = region_nibble << 4
    return bytes(data)


def snes(copier=False):
    data = bytearray(0x10000)
    base = 0x7FC0
    data[base + 0x15] = 0x20  # LoROM, slow
    data[base + 0x1C : base + 0x1E] = (0x5432).to_bytes(2, "little")  # complement
    data[base + 0x1E : base + 0x20] = (0xABCD).to_bytes(2, "little")  # checksum (xor == 0xFFFF)
    return (bytes(512) + bytes(data)) if copier else bytes(data)


def psp_iso():
    return bytes(50_000) + b"PSP_GAME" + bytes(1000)


def psx_iso():
    return isoutil.psx_disc()


def pbp(marker: bytes):
    header = bytearray(40)
    header[0:4] = b"\x00PBP"
    struct.pack_into("<I", header, 36, 100)
    return bytes(header) + bytes(60) + marker + bytes(100)


def write(path: Path, data: bytes, age=3600.0):
    path.write_bytes(data)
    stamp = path.stat().st_mtime - age
    os.utime(path, (stamp, stamp))
    return path


# ---------- name hints ----------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Zelda (GBC).zip", ["gbc"]),
        ("Pokemon - Game Boy Advance Collection", ["gba"]),
        ("Super Nintendo roms pack", ["snes"]),
        ("Sonic Mega Drive", ["genesis"]),
        ("PSP games", ["psp"]),
        ("Patapon (USA)", []),
        ("snes9x-setup", []),  # emulator download, not a system hint
    ],
)
def test_hint_systems(name, expected):
    assert hint_systems(name, ALL) == expected


def test_hint_ignores_systems_not_in_setup():
    assert hint_systems("Zelda (GBC)", {"nes"}) == []


# ---------- header detection, certain ----------

@pytest.mark.parametrize(
    "filename, data, system",
    [
        ("Contra.nes", nes(), "nes"),
        ("Metroid Fusion.gba", gba(), "gba"),
        ("Tetris.gb", gb(0x00), "gb"),
        ("Zelda DX.gbc", gb(0x80), "gbc"),
        ("Pokemon Crystal.gbc", gb(0xC0), "gbc"),
        ("Mario 64.z64", n64("80371240"), "n64"),
        ("Mario 64.v64", n64("37804012"), "n64"),
        ("Mario 64.n64", n64("40123780"), "n64"),
        ("Sonic.md", genesis(), "genesis"),
        ("Alex Kidd.sms", sega8(4), "sms"),
        ("Sonic GG.gg", sega8(7), "gamegear"),
        ("Chrono Trigger.sfc", snes(), "snes"),
        ("Chrono Trigger.smc", snes(copier=True), "snes"),
        ("Patapon.iso", psp_iso(), "psp"),
        ("Crash.iso", psx_iso(), "psx"),
        ("Game.cso", isoutil.cso(isoutil.psp_disc()), "psp"),
        ("Crash.pbp", pbp(b"PSISOIMG0000"), "psx"),
        ("Lumines.pbp", pbp(b"NPUMDIMG0000"), "psp"),
    ],
)
def test_header_identifies_system_with_certainty(tmp_path, filename, data, system):
    path = write(tmp_path / filename, data)
    ident = identify(path, ALL)
    assert ident is not None
    assert (ident.system_id, ident.confidence) == (system, Confidence.CERTAIN), ident.reason


def test_hybrid_game_boy_cart_follows_extension(tmp_path):
    hybrid = gb(0x80)  # works on both Game Boy and Game Boy Color
    assert identify(write(tmp_path / "A.gb", hybrid), ALL).system_id == "gb"
    assert identify(write(tmp_path / "B.gbc", hybrid), ALL).system_id == "gbc"


def test_header_beats_misleading_name(tmp_path):
    path = write(tmp_path / "Game Boy Wars (GBA).gb", gb(0x00))
    ident = identify(path, ALL)
    assert (ident.system_id, ident.confidence) == ("gb", Confidence.CERTAIN)


# ---------- contradictions and uncertainty ask the user ----------

def test_extension_header_mismatch_is_unsure(tmp_path):
    path = write(tmp_path / "Mislabelled.gbc", gb(0x00))  # DMG header in a .gbc file
    ident = identify(path, ALL)
    assert ident.confidence is Confidence.UNSURE
    assert ident.system_id == "gb" and ident.alternatives == ["gbc"]


def test_rom_with_wrong_extension_is_flagged_not_trusted(tmp_path):
    path = write(tmp_path / "Game.nes", gba())
    ident = identify(path, ALL)
    assert ident.confidence is Confidence.UNSURE and ident.system_id == "gba"


def test_unverifiable_rom_is_likely_not_certain(tmp_path):
    path = write(tmp_path / "Weird.nes", b"not a real header")
    ident = identify(path, ALL)
    assert (ident.system_id, ident.confidence) == ("nes", Confidence.LIKELY)


def test_name_disagreeing_with_extension_is_unsure(tmp_path):
    path = write(tmp_path / "Pokemon (GBA).nes", b"junk")
    ident = identify(path, ALL)
    assert ident.confidence is Confidence.UNSURE and ident.alternatives == ["gba"]


def test_chd_is_ambiguous_but_name_picks_the_default(tmp_path):
    ident = identify(write(tmp_path / "Game (PSP).chd", b"MComprHD"), ALL)
    assert ident.confidence is Confidence.UNSURE and ident.system_id == "psp"
    ident = identify(write(tmp_path / "Other.chd", b"MComprHD"), ALL)
    assert ident.confidence is Confidence.UNSURE and ident.system_id == "psx"


def test_plain_bin_is_ignored_unless_it_is_a_sega_rom(tmp_path):
    assert identify(write(tmp_path / "firmware.bin", bytes(5000)), ALL) is None
    assert identify(write(tmp_path / "Sonic.bin", genesis()), ALL).system_id == "genesis"


def test_unknown_and_partial_files_are_ignored(tmp_path):
    assert identify(write(tmp_path / "photo.jpg", b"x"), ALL) is None
    assert identify(write(tmp_path / "Game.nes.crdownload", nes()), ALL) is None


def test_system_removed_from_setup_is_not_offered(tmp_path):
    path = write(tmp_path / "Contra.nes", nes())
    assert identify(path, ALL - {"nes"}) is None


# ---------- archives ----------

def make_zip(path: Path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_zip_is_identified_by_the_rom_inside(tmp_path):
    z = make_zip(tmp_path / "download123.zip", {"Contra.nes": nes(), "readme.txt": b"hi"})
    ident = identify(z, ALL)
    assert (ident.system_id, ident.confidence) == ("nes", Confidence.CERTAIN)
    assert "Contra.nes" in ident.reason


def test_zip_with_several_roms_asks(tmp_path):
    z = make_zip(tmp_path / "pack.zip", {"A.nes": nes(), "B.nes": nes()})
    ident = identify(z, ALL)
    assert ident.confidence is Confidence.UNSURE and "2 ROMs" in ident.reason


def test_zip_with_roms_for_several_systems_asks(tmp_path):
    z = make_zip(tmp_path / "mixed.zip", {"A.nes": nes(), "B.gba": gba()})
    ident = identify(z, ALL)
    assert ident.confidence is Confidence.UNSURE and set([ident.system_id, *ident.alternatives]) == {"nes", "gba"}


def test_zip_without_roms_and_corrupt_zip_are_ignored(tmp_path):
    assert identify(make_zip(tmp_path / "docs.zip", {"notes.txt": b"x"}), ALL) is None
    assert identify(write(tmp_path / "broken.zip", b"not a zip"), ALL) is None


def test_7z_needs_a_name_hint_and_is_never_certain(tmp_path):
    assert identify(write(tmp_path / "backup.7z", b"7z"), ALL) is None
    ident = identify(write(tmp_path / "SNES collection.7z", b"7z"), ALL)
    assert ident.system_id == "snes" and ident.confidence is Confidence.UNSURE


# ---------- plans ----------

@pytest.fixture
def config(tmp_path):
    return Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"), inbox_dir=str(tmp_path / "inbox"))


def test_plan_sorts_certain_and_unsure_and_ignores_the_rest(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    write(inbox / "Mislabelled.gbc", gb(0x00))
    write(inbox / "holiday.jpg", b"jpg")
    write(inbox / ".hidden.nes", nes())
    plan = build_plan(inbox, config)
    by_name = {i.source.name: i for i in plan.items}
    assert set(by_name) == {"Contra.nes", "Mislabelled.gbc"}
    assert by_name["Contra.nes"].destination == tmp_path / "roms" / "nes" / "Contra.nes"
    assert by_name["Contra.nes"].confidence is Confidence.CERTAIN
    assert by_name["Mislabelled.gbc"].confidence is Confidence.UNSURE
    assert [p.name for p in plan.ignored] == ["holiday.jpg"]


def test_destination_uses_the_configured_folder_name(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Alex Kidd.sms", sega8(4))
    (item,) = build_plan(inbox, config).items
    assert item.destination == tmp_path / "roms" / "mastersystem" / "Alex Kidd.sms"


def test_files_still_downloading_are_left_alone(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Fresh.nes", nes(), age=0)
    write(inbox / "Old.nes", nes(), age=3600)
    plan = build_plan(inbox, config)
    assert [i.source.name for i in plan.items] == ["Old.nes"]
    assert [p.name for p in plan.waiting] == ["Fresh.nes"]


def test_existing_library_file_is_flagged(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    (tmp_path / "roms" / "nes").mkdir(parents=True)
    write(tmp_path / "roms" / "nes" / "Contra.nes", b"existing")
    (item,) = build_plan(inbox, config).items
    assert item.exists is True


def test_missing_inbox_gives_empty_plan(tmp_path, config):
    assert build_plan(tmp_path / "nope", config).items == []


def test_retarget_recomputes_destination_and_conflict(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Weird.nes", b"junk")
    (item,) = build_plan(inbox, config).items
    item.retarget(config, "gba")
    assert item.system_id == "gba" and item.destination.parent.name == "gba"


# ---------- cue / bin sets ----------

def test_cue_files_parses_quoted_and_bare_names(tmp_path):
    cue = tmp_path / "Game.cue"
    cue.write_text('FILE "Game (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE Track2.bin BINARY\n')
    assert [p.name for p in cue_files(cue)] == ["Game (Track 1).bin", "Track2.bin"]


def test_cue_and_tracks_move_together_as_one_item(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Crash.cue", b'FILE "Crash.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    write(inbox / "Crash.bin", psx_iso())
    plan = build_plan(inbox, config)
    assert len(plan.items) == 1  # the .bin is not offered on its own
    item = plan.items[0]
    assert item.system_id == "psx" and item.confidence is Confidence.CERTAIN
    assert [c.name for c in item.companions] == ["Crash.bin"]

    result = apply_plan([item], Journal(tmp_path / "j.json"))
    assert len(result.moved) == 1
    assert (tmp_path / "roms" / "psx" / "Crash.cue").exists()
    assert (tmp_path / "roms" / "psx" / "Crash.bin").exists()
    assert not (inbox / "Crash.bin").exists()


def test_cue_with_missing_track_asks(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Lost.cue", b'FILE "Lost.bin" BINARY\n')
    (item,) = build_plan(inbox, config).items
    assert item.confidence is Confidence.UNSURE and "Lost.bin" in item.reason


# ---------- moving ----------

def test_apply_moves_files_and_journals_them(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    plan = build_plan(inbox, config)
    journal = Journal(config.journal_path)
    result = apply_plan(plan.items, journal)
    assert [i.source.name for i in result.moved] == ["Contra.nes"]
    assert (tmp_path / "roms" / "nes" / "Contra.nes").read_bytes() == nes()
    assert not (inbox / "Contra.nes").exists()
    assert journal.can_undo() and journal.last_count() == 1


def test_apply_never_overwrites(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    dest = tmp_path / "roms" / "nes"
    dest.mkdir(parents=True)
    (dest / "Contra.nes").write_bytes(b"precious")
    plan = build_plan(inbox, config)
    result = apply_plan(plan.items, Journal(config.journal_path))
    assert result.moved == [] and len(result.skipped) == 1
    assert (dest / "Contra.nes").read_bytes() == b"precious"
    assert (inbox / "Contra.nes").exists()  # download left in place


def test_keep_both_renames_the_incoming_file(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    dest = tmp_path / "roms" / "nes"
    dest.mkdir(parents=True)
    (dest / "Contra.nes").write_bytes(b"precious")
    result = apply_plan(build_plan(inbox, config).items, Journal(config.journal_path), keep_both=True)
    assert len(result.moved) == 1
    assert (dest / "Contra.nes").read_bytes() == b"precious"
    assert (dest / "Contra (2).nes").read_bytes() == nes()


def test_unique_destination_skips_taken_names(tmp_path):
    (tmp_path / "A.nes").write_text("1")
    (tmp_path / "A (2).nes").write_text("2")
    assert unique_destination(tmp_path / "A.nes") == tmp_path / "A (3).nes"


def test_undo_restores_files_to_the_inbox(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    write(inbox / "Tetris.gb", gb())
    journal = Journal(config.journal_path)
    apply_plan(build_plan(inbox, config).items, journal)
    assert not (inbox / "Contra.nes").exists()

    restored, problems = journal.undo_last()
    assert (restored, problems) == (2, [])
    assert (inbox / "Contra.nes").exists() and (inbox / "Tetris.gb").exists()
    assert not (tmp_path / "roms" / "nes" / "Contra.nes").exists()
    assert journal.can_undo() is False


def test_undo_reports_files_that_are_gone(tmp_path, config):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write(inbox / "Contra.nes", nes())
    journal = Journal(config.journal_path)
    apply_plan(build_plan(inbox, config).items, journal)
    (tmp_path / "roms" / "nes" / "Contra.nes").unlink()
    restored, problems = journal.undo_last()
    assert restored == 0 and "no longer in the library" in problems[0]


def test_safe_move_refuses_to_overwrite(tmp_path):
    (tmp_path / "a").write_text("a")
    (tmp_path / "b").write_text("b")
    with pytest.raises(SortError):
        safe_move(tmp_path / "a", tmp_path / "b")
    assert (tmp_path / "b").read_text() == "b"


def test_safe_move_across_filesystems_copies_verifies_then_removes(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 5000)
    real_rename = os.rename

    def cross_device(a, b):
        raise OSError(18, "Invalid cross-device link")  # EXDEV

    monkeypatch.setattr(os, "rename", cross_device)
    dst = tmp_path / "out" / "dst.bin"
    safe_move(src, dst)
    monkeypatch.setattr(os, "rename", real_rename)
    assert dst.read_bytes() == b"x" * 5000
    assert not src.exists()
    assert not list((tmp_path / "out").glob("*.arcadia-part"))


def test_failed_cross_device_copy_leaves_the_original(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 100)
    monkeypatch.setattr(os, "rename", lambda a, b: (_ for _ in ()).throw(OSError(18, "xdev")))
    import shutil as _shutil

    def short_copy(s, d):
        Path(d).write_bytes(b"x" * 10)  # truncated copy

    monkeypatch.setattr(_shutil, "copy2", short_copy)
    with pytest.raises(SortError):
        safe_move(src, tmp_path / "out" / "dst.bin")
    assert src.read_bytes() == b"x" * 100
    assert not (tmp_path / "out" / "dst.bin").exists()
    assert not list((tmp_path / "out").glob("*.arcadia-part"))
