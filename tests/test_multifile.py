"""Multi-disc games and games with updates / DLC."""

import os
import sqlite3
import time
from pathlib import Path

import pytest

import arcadia.sorter as sorter
from arcadia.bundles import write_m3u
from arcadia.config import Config, SystemConfig, default_systems
from arcadia.launcher import build_command
from arcadia.library import Library
from arcadia.scanner import scan_system
from arcadia.sorter import Confidence, Journal, apply_plan, build_plan, identify

ALL = {s.id for s in default_systems()}
TID = "0100ABCD0001"  # first 12 hex digits of a made-up title ID block


def psx_bin():
    data = bytearray(0x10000)
    data[0x8000:0x8006] = b"\x01CD001"
    data[0x8008:0x8013] = b"PLAYSTATION"
    return bytes(data)


def nsp():
    return b"PFS0" + bytes(0x400)


def xci():
    return bytes(0x100) + b"HEAD" + bytes(0x400)


def put(path: Path, data: bytes = b"x", age=3600.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def put_disc(folder: Path, name: str):
    """A PlayStation disc as a .cue + .bin pair."""
    put(folder / f"{name}.cue", f'FILE "{name}.bin" BINARY\n  TRACK 01 MODE2/2352\n'.encode())
    put(folder / f"{name}.bin", psx_bin())


@pytest.fixture
def config(tmp_path):
    return Config(rom_root=str(tmp_path / "roms"), data_dir=str(tmp_path / "data"), inbox_dir=str(tmp_path / "inbox"))


def system(config, sid):
    return config.system(sid)


# ======================= scanner: multi-disc =======================

def test_playlist_is_the_game_and_its_discs_are_hidden_children(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game" / "Game (Disc 1).cue")
    put(psx / "Game" / "Game (Disc 2).cue")
    write_m3u(psx / "Game.m3u", ["Game/Game (Disc 1).cue", "Game/Game (Disc 2).cue"])

    games = {g.path.name: g for g in scan_system(tmp_path / "roms", system(config, "psx"))}
    playlist = games["Game.m3u"]
    assert playlist.parent_key is None and playlist.kind == "game" and playlist.title == "Game"
    for disc in ("Game (Disc 1).cue", "Game (Disc 2).cue"):
        assert games[disc].parent_key == playlist.key and games[disc].kind == "disc"


def test_discs_without_a_playlist_stay_separate_games(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game (Disc 1).cue")
    put(psx / "Game (Disc 2).cue")
    games = scan_system(tmp_path / "roms", system(config, "psx"))
    assert [g.parent_key for g in games] == [None, None]


def test_playlist_works_even_if_the_system_does_not_list_m3u(tmp_path):
    folder = tmp_path / "roms" / "x"
    put(folder / "A.cue")
    write_m3u(folder / "A.m3u", ["A.cue"])
    sysconf = SystemConfig(id="x", name="X", folder="x", extensions=[".cue"])
    games = {g.path.name: g for g in scan_system(tmp_path / "roms", sysconf)}
    assert games["A.m3u"].parent_key is None and games["A.cue"].parent_key == games["A.m3u"].key


def test_playlist_listing_a_missing_file_is_harmless(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game (Disc 1).cue")
    write_m3u(psx / "Game.m3u", ["Game (Disc 1).cue", "Game (Disc 2).cue"])  # disc 2 isn't there
    games = {g.path.name: g for g in scan_system(tmp_path / "roms", system(config, "psx"))}
    assert set(games) == {"Game.m3u", "Game (Disc 1).cue"}
    assert games["Game (Disc 1).cue"].kind == "disc"


# ======================= scanner: Switch updates and DLC =======================

def test_switch_updates_and_dlc_attach_to_their_base_game(tmp_path, config):
    sw = tmp_path / "roms" / "switch"
    put(sw / f"Super Game [{TID}2000][v0].nsp")
    put(sw / f"Super Game [{TID}2800][v65536].nsp")
    put(sw / f"Super Game DLC Pack 1 [{TID}3001][v0].nsp")
    put(sw / f"Super Game DLC Pack 2 [{TID}3002][v0].nsp")
    put(sw / "Other Game [0100FFFF00020000][v0].nsp")
    put(sw / "Homebrew.nsp")  # no title ID: just a game

    games = scan_system(tmp_path / "roms", system(config, "switch"))
    by_kind = {}
    for g in games:
        by_kind.setdefault(g.kind, []).append(g)
    base = next(g for g in by_kind["game"] if g.title == "Super Game")
    assert sorted(g.title for g in by_kind["game"]) == ["Homebrew", "Other Game", "Super Game"]
    assert len(by_kind["update"]) == 1 and by_kind["update"][0].parent_key == base.key
    assert len(by_kind["dlc"]) == 2 and all(g.parent_key == base.key for g in by_kind["dlc"])


def test_update_without_its_base_game_is_labelled_not_hidden(tmp_path, config):
    sw = tmp_path / "roms" / "switch"
    put(sw / f"Lonely Game [{TID}2800][v131072].nsp")
    put(sw / f"Lonely Game DLC [{TID}3001].nsp")
    games = {g.kind: g for g in scan_system(tmp_path / "roms", system(config, "switch"))}
    assert games["update"].parent_key is None and games["update"].title == "Lonely Game (update)"
    assert games["dlc"].parent_key is None and games["dlc"].title == "Lonely Game DLC (DLC)"


# ======================= library =======================

def test_children_are_listed_but_not_counted_or_shown(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game" / "Game (Disc 1).cue")
    put(psx / "Game" / "Game (Disc 2).cue")
    write_m3u(psx / "Game.m3u", ["Game/Game (Disc 1).cue", "Game/Game (Disc 2).cue"])
    put(psx / "Other.cue")
    lib = Library(tmp_path / "lib.db")
    lib.sync("psx", scan_system(tmp_path / "roms", system(config, "psx")))

    assert [r["title"] for r in lib.games("psx")] == ["Game", "Other"]
    assert lib.count("psx") == 2
    assert lib.summary()["systems"] == {"psx": 2}
    kids = lib.children(str(psx / "Game.m3u"))
    assert [r["path"].rsplit("/", 1)[1] for r in kids] == ["Game (Disc 1).cue", "Game (Disc 2).cue"]
    assert {r["kind"] for r in kids} == {"disc"}
    lib.close()


def test_playtime_and_favorite_move_to_the_playlist_without_double_counting(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    disc1 = put(psx / "Game (Disc 1).cue")
    disc2 = put(psx / "Game (Disc 2).cue")
    lib = Library(tmp_path / "lib.db")
    lib.sync("psx", scan_system(tmp_path / "roms", system(config, "psx")))
    lib.record_session(str(disc1), 1000.0, 600)
    lib.record_session(str(disc1), 2000.0, 300)
    lib.set_favorite(str(disc1), True)

    # The user (or the sorter) now joins the discs with a playlist.
    write_m3u(psx / "Game.m3u", ["Game (Disc 1).cue", "Game (Disc 2).cue"])
    for _ in range(2):  # a second rescan must not hand the stats over again
        lib.sync("psx", scan_system(tmp_path / "roms", system(config, "psx")))

    playlist = lib.get(str(psx / "Game.m3u"))
    assert (playlist["favorite"], playlist["play_count"], playlist["total_seconds"]) == (1, 2, 900)
    assert playlist["last_played"] == 2300.0
    old = lib.get(str(disc1))
    assert (old["favorite"], old["play_count"], old["total_seconds"]) == (0, 0, 0)
    assert [r["title"] for r in lib.games("psx")] == ["Game"]
    assert disc2.exists()
    lib.close()


def test_old_database_is_upgraded_in_place(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """CREATE TABLE games (key TEXT PRIMARY KEY, system_id TEXT NOT NULL, path TEXT NOT NULL,
               title TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, missing INTEGER NOT NULL DEFAULT 0,
               play_count INTEGER NOT NULL DEFAULT 0, total_seconds INTEGER NOT NULL DEFAULT 0, last_played REAL);
           CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, game_key TEXT NOT NULL, started REAL NOT NULL, seconds INTEGER NOT NULL);
           INSERT INTO games (key, system_id, path, title, favorite, play_count, total_seconds)
               VALUES ('/r/a.nes', 'nes', '/r/a.nes', 'A', 1, 3, 500);"""
    )
    conn.commit()
    conn.close()

    lib = Library(db)
    row = lib.get("/r/a.nes")
    assert (row["title"], row["favorite"], row["play_count"], row["kind"], row["parent_key"]) == ("A", 1, 3, "game", None)
    assert [r["title"] for r in lib.games("nes")] == ["A"]
    lib.close()
    Library(db).close()  # opening an already-upgraded database is fine


# ======================= launcher =======================

def test_extra_placeholders_are_filled_and_quoted():
    args = build_command(
        "emu --update {updates} --dlc {dlc} {rom}",
        Path("/roms/Game.nsp"),
        {"updates": [Path("/roms/Game upd.nsp")], "dlc": [Path("/roms/d1.nsp"), Path("/roms/d 2.nsp")]},
    )
    assert args == ["emu", "--update", "/roms/Game upd.nsp", "--dlc", "/roms/d1.nsp", "/roms/d 2.nsp", "/roms/Game.nsp"]


def test_unfilled_placeholders_vanish():
    assert build_command("emu {updates} {rom}", Path("/roms/G.nsp"), {}) == ["emu", "/roms/G.nsp"]
    assert build_command("emu {dlc}{rom}", Path("/roms/G.nsp")) == ["emu", "/roms/G.nsp"]


# ======================= sorter: Switch detection =======================

def test_switch_files_are_recognised_by_their_container(tmp_path):
    ident = identify(put(tmp_path / f"Game [{TID}2000].nsp", nsp()), ALL)
    assert (ident.system_id, ident.confidence) == ("switch", Confidence.CERTAIN)
    ident = identify(put(tmp_path / "Game.xci", xci()), ALL)
    assert (ident.system_id, ident.confidence) == ("switch", Confidence.CERTAIN)
    ident = identify(put(tmp_path / "Odd.nsp", b"not a container"), ALL)
    assert (ident.system_id, ident.confidence) == ("switch", Confidence.LIKELY)


# ======================= sorter: Switch bundles =======================

def test_game_update_and_dlc_arrive_as_one_bundle(tmp_path, config):
    inbox = tmp_path / "inbox"
    put(inbox / f"Super Game [{TID}2000][v0].nsp", nsp())
    put(inbox / f"Super Game [{TID}2800][v65536].nsp", nsp())
    put(inbox / f"Super Game DLC 1 [{TID}3001][v0].nsp", nsp())
    put(inbox / "Other Game [0100FFFF00020000][v0].nsp", nsp())

    plan = build_plan(inbox, config)
    bundle = next(i for i in plan.items if i.kind == "bundle")
    other = next(i for i in plan.items if i.kind == "single")
    assert len(plan.items) == 2
    assert bundle.source.name.startswith("Super Game [0100ABCD00012000]")
    assert bundle.detail == "+1 update, 1 DLC" and len(bundle.companions) == 2
    assert bundle.confidence is Confidence.CERTAIN and bundle.destination.parent.name == "switch"
    assert other.source.name.startswith("Other Game")

    result = apply_plan(plan.items, Journal(config.journal_path))
    assert len(result.moved) == 2
    games = scan_system(tmp_path / "roms", config.system("switch"))
    assert sorted(g.title for g in games if g.parent_key is None) == ["Other Game", "Super Game"]
    assert sorted(g.kind for g in games if g.parent_key) == ["dlc", "update"]


def test_update_for_a_game_not_in_the_library_is_flagged(tmp_path, config):
    inbox = tmp_path / "inbox"
    put(inbox / f"Super Game [{TID}2800][v65536].nsp", nsp())
    (item,) = build_plan(inbox, config).items
    assert item.confidence is Confidence.LIKELY and "base game isn't in your library" in item.reason


def test_update_for_a_game_already_in_the_library_is_fine(tmp_path, config):
    put(tmp_path / "roms" / "switch" / f"Super Game [{TID}2000][v0].nsp", nsp())
    inbox = tmp_path / "inbox"
    put(inbox / f"Super Game [{TID}2800][v65536].nsp", nsp())
    (item,) = build_plan(inbox, config).items
    assert item.confidence is Confidence.CERTAIN and "already in your library" in item.reason


# ======================= sorter: multi-disc sets =======================

def test_discs_become_one_set_with_a_playlist(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Final Fantasy VII (USA) (Disc 2)")
    put_disc(inbox, "Final Fantasy VII (USA) (Disc 1)")
    put_disc(inbox, "Final Fantasy VII (USA) (Disc 3)")
    put_disc(inbox, "Crash Bandicoot (USA)")

    plan = build_plan(inbox, config)
    assert len(plan.items) == 2
    ff7 = next(i for i in plan.items if i.kind == "disc_set")
    assert ff7.title == "Final Fantasy VII (USA)" and ff7.detail == "3 discs"
    assert [d.name for d in ff7.discs] == [f"Final Fantasy VII (USA) (Disc {n}).cue" for n in (1, 2, 3)]
    assert len(ff7.sources) == 6  # three cues and their three bin tracks
    assert ff7.confidence is Confidence.CERTAIN
    assert ff7.destination == tmp_path / "roms" / "psx" / "Final Fantasy VII (USA).m3u"
    assert ff7.dest_label() == "psx/Final Fantasy VII (USA)/" and ff7.label == ff7.title


def test_missing_disc_makes_the_set_ask(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 3)")
    (item,) = build_plan(inbox, config).items
    assert item.kind == "disc_set" and item.confidence is Confidence.UNSURE and "disc 2" in item.reason


def test_declared_total_exposes_a_missing_last_disc(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1 of 3)")
    put_disc(inbox, "Game (Disc 2 of 3)")
    (item,) = build_plan(inbox, config).items
    assert item.confidence is Confidence.UNSURE and "disc 3" in item.reason


def test_different_regions_or_titles_do_not_merge(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (USA) (Disc 1)")
    put_disc(inbox, "Game (Europe) (Disc 2)")
    put_disc(inbox, "Other (USA) (Disc 1)")
    plan = build_plan(inbox, config)
    assert all(i.kind == "single" for i in plan.items) and len(plan.items) == 3


def test_two_files_claiming_the_same_disc_are_left_alone(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 1) (Rev 1)".replace(" (Rev 1)", ""))  # same name again: one file
    put(inbox / "Game CD1.iso", b"\0" * 100)  # a second "disc 1" for the same game
    plan = build_plan(inbox, config)
    assert all(i.kind == "single" for i in plan.items)


def test_lone_disc_is_flagged_but_still_movable(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 2)")
    (item,) = build_plan(inbox, config).items
    assert item.kind == "single" and item.confidence is Confidence.LIKELY and "disc 2 of a multi-disc game" in item.reason


def test_lone_disc_joins_an_existing_playlist(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game" / "Game (Disc 1).cue")
    write_m3u(psx / "Game.m3u", ["Game/Game (Disc 1).cue"])
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 2)")
    (item,) = build_plan(inbox, config).items
    assert item.kind == "disc_set" and item.merge is True and item.detail == "adds disc 2"
    assert item.confidence is Confidence.CERTAIN


def test_apply_set_writes_ordered_relative_playlist_and_scan_sees_one_game(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 2)")
    put_disc(inbox, "Game (Disc 1)")
    journal = Journal(config.journal_path)
    result = apply_plan(build_plan(inbox, config).items, journal)
    assert len(result.moved) == 1

    psx = tmp_path / "roms" / "psx"
    assert (psx / "Game.m3u").read_text() == "Game/Game (Disc 1).cue\nGame/Game (Disc 2).cue\n"
    for name in ("Game (Disc 1).cue", "Game (Disc 1).bin", "Game (Disc 2).cue", "Game (Disc 2).bin"):
        assert (psx / "Game" / name).exists() and not (inbox / name).exists()

    games = scan_system(tmp_path / "roms", config.system("psx"))
    assert [g.title for g in games if g.parent_key is None] == ["Game"]
    assert len([g for g in games if g.kind == "disc"]) == 2


def test_undo_removes_the_playlist_and_folder_and_returns_the_discs(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 2)")
    journal = Journal(config.journal_path)
    apply_plan(build_plan(inbox, config).items, journal)

    restored, problems = journal.undo_last()
    assert (restored, problems) == (4, [])
    psx = tmp_path / "roms" / "psx"
    assert not (psx / "Game.m3u").exists() and not (psx / "Game").exists()
    assert sorted(p.name for p in inbox.iterdir()) == sorted(
        f"Game (Disc {n}).{ext}" for n in (1, 2) for ext in ("cue", "bin")
    )


def test_adding_a_disc_extends_the_playlist_and_undo_restores_it(tmp_path, config):
    psx = tmp_path / "roms" / "psx"
    put(psx / "Game" / "Game (Disc 1).cue")
    write_m3u(psx / "Game.m3u", ["Game/Game (Disc 1).cue"])
    original = (psx / "Game.m3u").read_text()
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 2)")
    journal = Journal(config.journal_path)

    apply_plan(build_plan(inbox, config).items, journal)
    assert (psx / "Game.m3u").read_text() == "Game/Game (Disc 1).cue\nGame/Game (Disc 2).cue\n"

    journal.undo_last()
    assert (psx / "Game.m3u").read_text() == original
    assert (inbox / "Game (Disc 2).cue").exists() and (psx / "Game" / "Game (Disc 1).cue").exists()


def test_a_set_that_collides_with_the_library_moves_nothing(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 2)")
    existing = tmp_path / "roms" / "psx" / "Game"
    put(existing / "Game (Disc 2).cue", b"precious")
    plan = build_plan(inbox, config)
    assert plan.items[0].exists is True

    result = apply_plan(plan.items, Journal(config.journal_path))
    assert result.moved == [] and "already exists" in result.skipped[0][1]
    assert (existing / "Game (Disc 2).cue").read_bytes() == b"precious"
    assert (inbox / "Game (Disc 1).cue").exists() and (inbox / "Game (Disc 2).bin").exists()
    assert not (tmp_path / "roms" / "psx" / "Game.m3u").exists()
    assert not (existing / "Game (Disc 1).cue").exists()


def test_a_failure_part_way_rolls_the_whole_set_back(tmp_path, config, monkeypatch):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 2)")
    plan = build_plan(inbox, config)
    real = sorter.safe_move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:  # the third file fails; two were already moved
            raise sorter.SortError("disk full")
        real(src, dst)

    monkeypatch.setattr(sorter, "safe_move", flaky)
    result = apply_plan(plan.items, Journal(config.journal_path))

    assert result.moved == [] and result.skipped[0][1] == "disk full"
    assert sorted(p.name for p in inbox.iterdir()) == sorted(
        f"Game (Disc {n}).{ext}" for n in (1, 2) for ext in ("cue", "bin")
    )
    assert not (tmp_path / "roms" / "psx" / "Game").exists()
    assert not (tmp_path / "roms" / "psx" / "Game.m3u").exists()


def test_user_can_retarget_a_set_to_another_system(tmp_path, config):
    inbox = tmp_path / "inbox"
    put_disc(inbox, "Game (Disc 1)")
    put_disc(inbox, "Game (Disc 2)")
    (item,) = build_plan(inbox, config).items
    item.retarget(config, "psp")
    assert item.destination == tmp_path / "roms" / "psp" / "Game.m3u" and item.dest_label() == "psp/Game/"
