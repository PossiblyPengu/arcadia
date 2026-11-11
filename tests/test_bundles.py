import pytest

from arcadia.bundles import SwitchInfo, merge_m3u_lines, parse_disc, parse_switch, read_m3u, write_m3u


# ---------- disc names ----------

@pytest.mark.parametrize(
    "stem, base, number, total",
    [
        ("Final Fantasy VII (USA) (Disc 1)", "Final Fantasy VII (USA)", 1, None),
        ("Final Fantasy VII (USA) (Disc 3)", "Final Fantasy VII (USA)", 3, None),
        ("Metal Gear Solid (Disc 2 of 2)", "Metal Gear Solid", 2, 2),
        ("Metal Gear Solid [Disc 1]", "Metal Gear Solid", 1, None),
        ("Xenogears (Disk 2)", "Xenogears", 2, None),
        ("Parasite Eve (CD2)", "Parasite Eve", 2, None),
        ("Resident Evil 2 (Disc A)", "Resident Evil 2", 1, None),
        ("Resident Evil 2 (Disc B)", "Resident Evil 2", 2, None),
        ("Chrono Cross (USA) (Disc 2) (Rev 1)", "Chrono Cross (USA) (Rev 1)", 2, None),
        ("Legend of Dragoon Disc 4", "Legend of Dragoon", 4, None),
        ("Vagrant_Story_CD1", "Vagrant_Story", 1, None),
    ],
)
def test_parse_disc(stem, base, number, total):
    info = parse_disc(stem)
    assert (info.base, info.number, info.total) == (base, number, total)


@pytest.mark.parametrize(
    "stem",
    ["Crash Bandicoot (USA)", "Disco Elysium", "Discworld", "CD-i Games", "Cdr Test", "Disc 1", "Game (Disc 0)"],
)
def test_parse_disc_ignores_non_disc_names(stem):
    assert parse_disc(stem) is None


# ---------- playlists ----------

def test_m3u_round_trip_resolves_relative_entries(tmp_path):
    m3u = tmp_path / "Game.m3u"
    write_m3u(m3u, ["Game/Game (Disc 1).cue", "Game/Game (Disc 2).cue"])
    assert m3u.read_text() == "Game/Game (Disc 1).cue\nGame/Game (Disc 2).cue\n"
    assert read_m3u(m3u) == [tmp_path / "Game/Game (Disc 1).cue", tmp_path / "Game/Game (Disc 2).cue"]


def test_read_m3u_skips_comments_blanks_and_handles_bom(tmp_path):
    m3u = tmp_path / "x.m3u"
    m3u.write_bytes(b"\xef\xbb\xbf#EXTM3U\n\n  Disc 1.cue  \n# note\n/abs/Disc 2.cue\n")
    assert read_m3u(m3u) == [tmp_path / "Disc 1.cue", __import__("pathlib").Path("/abs/Disc 2.cue")]


def test_read_m3u_missing_file_is_empty(tmp_path):
    assert read_m3u(tmp_path / "nope.m3u") == []


def test_merge_m3u_orders_by_disc_number_and_drops_duplicates():
    merged = merge_m3u_lines(
        ["G/G (Disc 1).cue", "G/G (Disc 3).cue"],
        ["G/G (Disc 2).cue", "G/G (Disc 3).cue"],
    )
    assert merged == ["G/G (Disc 1).cue", "G/G (Disc 2).cue", "G/G (Disc 3).cue"]


def test_merge_m3u_keeps_unnumbered_entries_after_numbered():
    merged = merge_m3u_lines(["bonus.cue"], ["G (Disc 2).cue", "G (Disc 1).cue"])
    assert merged == ["G (Disc 1).cue", "G (Disc 2).cue", "bonus.cue"]


# ---------- Switch title IDs ----------

def test_switch_base_update_and_dlc_share_a_group():
    base = parse_switch("Super Game [0100ABCD00012000][v0].nsp")
    update = parse_switch("Super Game [0100ABCD00012800][v65536].nsp")
    dlc1 = parse_switch("Super Game DLC 1 [0100ABCD00013001][v0].nsp")
    dlc2 = parse_switch("Super Game DLC 2 [0100ABCD00013002][v0].nsp")
    other = parse_switch("Another Game [0100FFFF00020000][v0].nsp")
    assert [i.role for i in (base, update, dlc1, dlc2)] == ["base", "update", "dlc", "dlc"]
    assert len({base.group, update.group, dlc1.group, dlc2.group}) == 1
    assert other.group != base.group


def test_switch_versions_in_both_styles():
    assert parse_switch("G [0100ABCD00012800][v131072].nsp").version == "v131072"
    assert parse_switch("G (v1.2.0) [0100ABCD00012800].nsp").version == "v1.2.0"
    assert parse_switch("G [0100ABCD00012000].nsp").version == ""


def test_switch_title_id_is_normalised():
    info = parse_switch("g [0100abcd00012000].nsp")
    assert info == SwitchInfo("0100ABCD00012000", "base", 0x0100ABCD00012, "")


@pytest.mark.parametrize("name", ["Game.nsp", "Game [v0].nsp", "Game [0200ABCD00012000].nsp", "Game [01ABC].nsp"])
def test_names_without_a_switch_title_id_are_not_parsed(name):
    assert parse_switch(name) is None
