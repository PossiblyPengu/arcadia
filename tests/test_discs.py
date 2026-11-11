import struct

import pytest

import isoutil
from arcadia.discs import (
    DiscGuess,
    buffer_reader,
    classify_iso,
    cso_reader,
    iso_root,
    read_iso_file,
    sniff_chd,
    sniff_disc_image,
)


# ---------- the ISO reader itself ----------

def test_iso_root_lists_entries_and_files_can_be_read():
    image = isoutil.iso({"SYSTEM.CNF;1": b"BOOT = cdrom:\\X;1", "BIG.DAT;1": b"z" * 5000}, dirs=["DIR"])
    pvd, entries = iso_root(buffer_reader(image, (2048, 0)))
    assert set(entries) >= {"SYSTEM.CNF;1", "BIG.DAT;1", "DIR"}
    get = buffer_reader(image, (2048, 0))
    assert read_iso_file(get, *entries["SYSTEM.CNF;1"]) == b"BOOT = cdrom:\\X;1"
    assert read_iso_file(get, *entries["BIG.DAT;1"], limit=4096) == b"z" * 4096


def test_iso_root_rejects_non_iso_data():
    assert iso_root(buffer_reader(bytes(100_000), (2048, 0))) is None
    assert iso_root(buffer_reader(b"", (2048, 0))) is None


def test_read_iso_file_outside_the_buffer_is_none():
    image = isoutil.iso({"BIG.DAT;1": b"z" * 5000})
    get = buffer_reader(image[: 21 * 2048], (2048, 0))  # the root directory (sector 20) is there, the file's data isn't
    pvd, entries = iso_root(get)
    assert "BIG.DAT;1" in entries
    assert read_iso_file(get, *entries["BIG.DAT;1"]) is None


# ---------- PlayStation: the case that used to be wrong ----------

@pytest.mark.parametrize("layout", [(2048, 0), (2352, 16), (2352, 24)])
def test_ps1_and_ps2_are_told_apart_in_every_sector_layout(layout):
    ps1 = sniff_disc_image(isoutil.psx_disc(layout))
    ps2 = sniff_disc_image(isoutil.ps2_disc(layout))
    assert (ps1.system, ps2.system) == ("psx", "ps2")
    assert "BOOT2" in ps2.detail and "BOOT)" in ps1.detail


def test_a_playstation_disc_without_readable_system_cnf_is_ambiguous_not_ps1():
    guess = sniff_disc_image(isoutil.iso({}, system_id=b"PLAYSTATION"))  # marker only, nothing to boot from
    assert guess.system is None and guess.candidates == ["psx", "ps2"]


def test_psp_and_ps3_discs():
    assert sniff_disc_image(isoutil.psp_disc()).system == "psp"
    assert sniff_disc_image(isoutil.ps3_disc()).system == "ps3"


def test_an_iso_we_do_not_recognise_stays_unknown():
    guess = sniff_disc_image(isoutil.iso({"README.TXT;1": b"hi"}, system_id=b"SOMETHING ELSE"))
    assert guess == DiscGuess()
    assert sniff_disc_image(bytes(50_000)) == DiscGuess()


# ---------- PSP compressed images ----------

@pytest.mark.parametrize("compress", [True, False])
@pytest.mark.parametrize("align", [0, 2])
def test_cso_images_are_read_through_the_compression(compress, align):
    image = isoutil.psp_disc()
    cso = isoutil.cso(image, compress=compress, align=align)
    get = cso_reader(isoutil.read_at_for(cso))
    assert get(16) == image[16 * 2048 : 17 * 2048]
    guess = sniff_disc_image(cso[:0x100000], ".cso", isoutil.read_at_for(cso))
    assert guess.system == "psp"


def test_a_ps2_game_in_a_cso_is_not_mistaken_for_psp():
    cso = isoutil.cso(isoutil.ps2_disc())
    assert sniff_disc_image(cso, ".cso", isoutil.read_at_for(cso)).system == "ps2"


def test_a_cso_we_cannot_classify_asks_instead_of_guessing():
    cso = isoutil.cso(isoutil.iso({"X.TXT;1": b"x"}, system_id=b"DATA"))
    guess = sniff_disc_image(cso, ".cso", isoutil.read_at_for(cso))
    assert guess.system is None and guess.candidates == []


def test_cso_reader_rejects_other_data():
    assert cso_reader(isoutil.read_at_for(b"NOPE" + bytes(100))) is None
    assert cso_reader(isoutil.read_at_for(b"")) is None


# ---------- Nintendo ----------

def _gc_header():
    return bytes(0x1C) + bytes.fromhex("C2339F3D") + bytes(0x100)


def _wii_header():
    return bytes(0x18) + bytes.fromhex("5D1C9EA3") + bytes(0x104)


def test_gamecube_and_wii_discs_are_told_apart():
    assert sniff_disc_image(_gc_header(), ".iso").system == "gc"
    assert sniff_disc_image(_wii_header(), ".iso").system == "wii"


def test_wbfs_is_wii_and_rvz_wia_are_read_through_their_wrapper():
    assert sniff_disc_image(b"WBFS" + bytes(100), ".wbfs").system == "wii"
    rvz_gc = b"RVZ\x01" + bytes(0x54) + _gc_header()
    rvz_wii = b"WIA\x01" + bytes(0x54) + _wii_header()
    assert sniff_disc_image(rvz_gc, ".rvz").system == "gc"
    assert sniff_disc_image(rvz_wii, ".wia").system == "wii"
    unreadable = b"RVZ\x01" + bytes(0x200)
    guess = sniff_disc_image(unreadable, ".rvz")
    assert guess.system is None and guess.candidates == ["gc", "wii"]


def test_gcz_and_ciso_are_ambiguous_for_dolphin():
    assert sniff_disc_image(b"\x01\xc0\x0b\xb1" + bytes(64), ".gcz").candidates == ["gc", "wii"]
    assert sniff_disc_image(b"CISO" + bytes(64), ".ciso").candidates == ["gc", "wii"]


# ---------- other consoles ----------

def test_xbox_saturn_segacd_and_dreamcast():
    assert sniff_disc_image(bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA" + bytes(100), ".iso").system == "xbox"
    saturn = isoutil.iso(sector0=b"SEGA SEGASATURN " + bytes(100), system_id=b"SEGA SEGASATURN")
    assert sniff_disc_image(saturn).system == "saturn"
    segacd = isoutil.iso(sector0=b"SEGADISCSYSTEM  " + bytes(100), system_id=b"SEGA")
    assert sniff_disc_image(segacd).system == "segacd"
    raw_dc = isoutil.iso(sector0=b"SEGA SEGAKATANA SEGA ENTERPRISES" + bytes(100), layout=(2352, 16))
    assert sniff_disc_image(raw_dc).system == "dreamcast"


# ---------- PBP ----------

def _pbp(marker: bytes):
    header = bytearray(40)
    header[0:4] = b"\x00PBP"
    struct.pack_into("<I", header, 36, 100)
    return bytes(header) + bytes(60) + marker + bytes(100)


def test_pbp_contents_decide_psp_or_playstation():
    for marker, system in ((b"PSISOIMG0000", "psx"), (b"NPUMDIMG0000", "psp")):
        data = _pbp(marker)
        assert sniff_disc_image(data, ".pbp", isoutil.read_at_for(data)).system == system
    data = _pbp(b"WHATEVER0000")
    assert sniff_disc_image(data, ".pbp", isoutil.read_at_for(data)) == DiscGuess()
    assert sniff_disc_image(data, ".pbp", None).candidates == ["psp", "psx"]  # e.g. inside a zip


# ---------- CHD ----------

def _chd(tag: bytes, version: int = 5):
    head = bytearray(0x80)
    head[:8] = b"MComprHD"
    head[8:12] = struct.pack(">I", 124)
    head[12:16] = struct.pack(">I", version)
    head[0x30:0x38] = struct.pack(">Q", 0x80)
    return bytes(head) + tag + bytes(12)


@pytest.mark.parametrize(
    "tag, expected",
    [
        (b"CHGD", ["dreamcast"]),
        (b"CHT2", ["psx", "ps2", "saturn", "segacd", "pcengine"]),
        (b"DVD ", ["ps2", "gc", "wii", "xbox", "psp"]),
        (b"ZZZZ", []),
    ],
)
def test_chd_metadata_narrows_the_candidates(tag, expected):
    data = _chd(tag)
    guess = sniff_chd(lambda n: data[:n], isoutil.read_at_for(data))
    assert guess.system is None and guess.candidates == expected


def test_chd_oddities_are_harmless():
    old = _chd(b"CHT2", version=4)
    assert sniff_chd(lambda n: old[:n], isoutil.read_at_for(old)).candidates == []
    assert sniff_chd(lambda n: b"", None) == DiscGuess()
    plain = _chd(b"CHT2")
    assert sniff_chd(lambda n: plain[:n], None).candidates == []  # no random access (inside a zip)
