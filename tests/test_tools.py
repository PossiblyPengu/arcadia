"""BIOS checks, RetroArch settings/cores/Flatpak access, and save sync."""

import io
import os
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from arcadia import bios, retroarch, savesync
from arcadia.backup import create_backup, restore_backup
from arcadia.config import Config
from arcadia.emulators import EmulatorError
from arcadia.launcher import resolve_launch


def make_config(tmp_path) -> Config:
    config = Config.new_install(tmp_path / "Arcadia")
    config.ensure_layout()
    return config


# ----- BIOS -----

def rows(config):
    return {r.system_id: r for r in bios.check_bios(config)}


def test_missing_bios_is_reported_and_found_case_insensitively(tmp_path):
    config = make_config(tmp_path)
    assert rows(config)["psx"].state == "missing"
    (config.bios_path / "PSX").mkdir()
    (config.bios_path / "PSX" / "SCPH5501.BIN").write_bytes(b"x")
    r = rows(config)["psx"]
    assert r.state == "ok" and r.needs[0].found == "PSX/SCPH5501.BIN"


def test_optional_files_do_not_count_as_missing(tmp_path):
    config = make_config(tmp_path)
    assert rows(config)["gba"].state == "optional"
    assert rows(config)["dreamcast"].state == "missing"
    (config.bios_path / "dc_boot.bin").write_bytes(b"x")
    assert rows(config)["dreamcast"].state == "optional"  # flash is optional


def test_patterns_and_depth_limit(tmp_path):
    config = make_config(tmp_path)
    (config.bios_path / "a" / "b" / "c").mkdir(parents=True)
    (config.bios_path / "a" / "b" / "c" / "scph10000.bin").write_bytes(b"x")
    assert rows(config)["ps2"].state == "missing"  # three folders down: not searched
    (config.bios_path / "a" / "scph10000.bin").write_bytes(b"x")
    assert rows(config)["ps2"].state == "ok"


def test_systems_without_known_needs_are_not_listed(tmp_path):
    assert "nes" not in rows(make_config(tmp_path))


# ----- RetroArch settings -----

def test_appendconfig_text_and_file(tmp_path):
    config = make_config(tmp_path)
    text = retroarch.config_text(config)
    assert f'system_directory = "{config.bios_path}"' in text
    assert 'video_fullscreen = "true"' in text and 'video_scale_integer = "false"' in text
    assert "savefile_directory" not in text  # existing saves are not moved unless asked
    config.ra_saves_in_home = True
    assert f'savefile_directory = "{config.saves_path}"' in retroarch.config_text(config)
    path = retroarch.write_appendconfig(config)
    assert path.read_text() == retroarch.config_text(config)


def test_appendconfig_goes_right_after_the_program():
    p = Path("/x/a.cfg")
    flat = ["flatpak", "run", "org.libretro.RetroArch", "-L", "/c/s.so", "/r/g.sfc"]
    assert retroarch.with_appendconfig(flat, p) == ["flatpak", "run", "org.libretro.RetroArch", "--appendconfig=/x/a.cfg", "-L", "/c/s.so", "/r/g.sfc"]
    assert retroarch.with_appendconfig(["retroarch", "-L", "c"], p)[1] == "--appendconfig=/x/a.cfg"
    other = ["flatpak", "run", "org.DolphinEmu.dolphin-emu", "-b"]
    assert retroarch.with_appendconfig(other, p) == other
    mine = ["retroarch", "--appendconfig=/mine.cfg"]
    assert retroarch.with_appendconfig(mine, p) == mine


def test_resolve_launch_applies_it_only_to_retroarch(tmp_path):
    config = make_config(tmp_path)
    rom = tmp_path / "g.nes"
    plan = resolve_launch(config, config.system("nes"), rom)
    assert any(a.startswith("--appendconfig=") for a in plan.args)
    assert retroarch.appendconfig_path(config).is_file()
    plan = resolve_launch(config, config.system("snes"), rom)
    assert not any(a.startswith("--appendconfig") for a in plan.args)
    config.manage_retroarch = False
    assert not any(a.startswith("--appendconfig") for a in resolve_launch(config, config.system("nes"), rom).args)


# ----- cores -----

def core_zip(name, payload=b"\x7fELF" + b"\0" * 2000):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, payload)
    return buf.getvalue()


class FakeFetcher:
    def __init__(self, data):
        self.data, self.urls = data, []

    def download(self, url, dest, progress=None):
        self.urls.append(url)
        if isinstance(self.data, Exception):
            raise self.data
        dest.write_bytes(self.data)
        return "x"


def test_cores_in_use_lists_missing_and_present(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    cores = tmp_path / "cores"
    for s in config.systems:
        s.command = s.command.replace("~/.var/app/org.libretro.RetroArch/config/retroarch/cores", str(cores))
    cores.mkdir()
    (cores / "nestopia_libretro.so").write_bytes(b"x")
    by = {r.name: r for r in retroarch.cores_in_use(config)}
    assert by["nestopia_libretro.so"].installed and not by["genesis_plus_gx_libretro.so"].installed
    assert len(by["genesis_plus_gx_libretro.so"].systems) == 4  # genesis, sms, game gear, sega cd


def test_install_core_replaces_atomically(tmp_path):
    dest = tmp_path / "cores" / "nestopia_libretro.so"
    fetcher = FakeFetcher(core_zip("nestopia_libretro.so"))
    retroarch.install_core(dest, fetcher)
    assert dest.read_bytes().startswith(b"\x7fELF") and os.access(dest, os.X_OK)
    assert fetcher.urls == ["https://buildbot.libretro.com/nightly/linux/x86_64/latest/nestopia_libretro.so.zip"]
    assert [p.name for p in dest.parent.iterdir()] == ["nestopia_libretro.so"]  # no temp left over


@pytest.mark.parametrize("data", [core_zip("other_libretro.so"), core_zip("nestopia_libretro.so", b"not a program" * 200), b"junk", EmulatorError("down")])
def test_bad_downloads_leave_the_existing_core_alone(tmp_path, data):
    dest = tmp_path / "nestopia_libretro.so"
    dest.write_bytes(b"old")
    with pytest.raises(EmulatorError):
        retroarch.install_core(dest, FakeFetcher(data))
    assert dest.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["nestopia_libretro.so"]


def test_core_names_are_validated(tmp_path):
    with pytest.raises(EmulatorError):
        retroarch.install_core(tmp_path / "../evil.so", FakeFetcher(b""))


def test_update_cores_continues_after_a_failure(tmp_path):
    good = retroarch.CoreRow("a_libretro.so", tmp_path / "a_libretro.so", ("A",), False)
    bad = retroarch.CoreRow("b_libretro.so", tmp_path / "b_libretro.so", ("B",), False)

    class Mixed:
        def download(self, url, dest, progress=None):
            if "b_libretro" in url:
                raise EmulatorError("nope")
            dest.write_bytes(core_zip("a_libretro.so"))

    out = retroarch.update_cores([bad, good], Mixed())
    assert [(o.name, o.ok) for o in out] == [("b_libretro.so", False), ("a_libretro.so", True)]
    assert (tmp_path / "a_libretro.so").is_file()


def test_core_fetcher_only_talks_to_the_libretro_build_server():
    f = retroarch.core_fetcher()
    f.check_url("https://buildbot.libretro.com/x")
    with pytest.raises(EmulatorError):
        f.check_url("https://github.com/x")


# ----- Flatpak access -----

def test_access_paths_and_commands(tmp_path):
    config = make_config(tmp_path)
    assert retroarch.access_paths(config) == [config.home_path]
    config.rom_root = str(tmp_path / "elsewhere")
    assert retroarch.access_paths(config) == [config.home_path, tmp_path / "elsewhere"]
    cmds = retroarch.grant_commands(["a.b.C"], [Path("/x y")])
    assert cmds == [["flatpak", "override", "--user", "--filesystem=/x y", "a.b.C"]]


def test_a_path_with_a_colon_is_not_granted(tmp_path):
    config = Config.new_install(tmp_path / "we:ird")
    assert retroarch.access_paths(config) == []


def test_grant_access_reports_failure_and_missing_flatpak():
    class R:
        def __init__(self, code):
            self.returncode, self.stdout, self.stderr = code, "", "boom"

    ok = retroarch.grant_access(["a.b.C"], [Path("/x")], run=lambda *a, **k: R(0), which=lambda _: "/usr/bin/flatpak")
    assert ok.ok and ok.done == 1
    bad = retroarch.grant_access(["a.b.C"], [Path("/x")], run=lambda *a, **k: R(1), which=lambda _: "/usr/bin/flatpak")
    assert not bad.ok and "boom" in bad.output
    assert not retroarch.grant_access(["a.b.C"], [Path("/x")], which=lambda _: None).ok


# ----- save sync -----

def sync_config(tmp_path) -> Config:
    config = make_config(tmp_path)
    config.sync_remote = ""
    config.sync_dir = str(tmp_path / "cloud")
    return config


def run_sync(config, tmp_path, **kw):
    return savesync.sync(config, retroarch_saves=tmp_path / "no-retroarch", **kw)


def test_first_sync_copies_both_ways_without_deleting(tmp_path):
    config = sync_config(tmp_path)
    (config.saves_path / "a.srm").write_bytes(b"local")
    remote = tmp_path / "cloud" / "Arcadia" / "saves"
    remote.mkdir(parents=True)
    (remote / "b.srm").write_bytes(b"remote")
    r = run_sync(config, tmp_path)
    assert (r.pushed, r.pulled, r.conflicts) == (1, 1, 0)
    assert (remote / "a.srm").read_bytes() == b"local"
    assert (config.saves_path / "b.srm").read_bytes() == b"remote"
    assert run_sync(config, tmp_path).changed == 0


def test_a_change_on_one_side_flows_to_the_other(tmp_path):
    config = sync_config(tmp_path)
    (config.saves_path / "a.srm").write_bytes(b"v1")
    run_sync(config, tmp_path)
    remote = tmp_path / "cloud" / "Arcadia" / "saves" / "a.srm"
    remote.write_bytes(b"v2 from the other device")
    r = run_sync(config, tmp_path)
    assert r.pulled == 1 and r.conflicts == 0
    assert (config.saves_path / "a.srm").read_bytes() == b"v2 from the other device"
    # what was overwritten here is kept
    kept = list((config.backups_path / "savesync").rglob("a.srm"))
    assert kept and kept[0].read_bytes() == b"v1"
    (config.saves_path / "a.srm").write_bytes(b"v3 here")
    assert run_sync(config, tmp_path).pushed == 1 and remote.read_bytes() == b"v3 here"


def test_conflicts_keep_both_and_newest_wins(tmp_path):
    config = sync_config(tmp_path)
    local = config.saves_path / "a.srm"
    local.write_bytes(b"v1")
    run_sync(config, tmp_path)
    remote = tmp_path / "cloud" / "Arcadia" / "saves" / "a.srm"
    local.write_bytes(b"local edit")
    remote.write_bytes(b"remote edit")
    os.utime(local, (1000, 1000))
    os.utime(remote, (2000, 2000))  # remote is newer
    r = run_sync(config, tmp_path)
    assert r.conflicts == 1 and r.pulled == 1
    assert local.read_bytes() == b"remote edit"
    assert any(Path(k).read_bytes() == b"local edit" for k in r.kept)


def test_conflict_where_this_device_is_newer_keeps_the_remote_copy(tmp_path):
    config = sync_config(tmp_path)
    local = config.saves_path / "a.srm"
    local.write_bytes(b"v1")
    run_sync(config, tmp_path)
    remote = tmp_path / "cloud" / "Arcadia" / "saves" / "a.srm"
    local.write_bytes(b"local edit")
    remote.write_bytes(b"remote edit")
    os.utime(remote, (1000, 1000))
    os.utime(local, (2000, 2000))
    r = run_sync(config, tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))
    assert r.pushed == 1 and remote.read_bytes() == b"local edit"
    kept = tmp_path / "cloud" / "Arcadia" / "_conflicts" / "20260102-030405" / "saves" / "a.srm"
    assert kept.read_bytes() == b"remote edit"


def test_deleting_a_file_is_never_propagated(tmp_path):
    config = sync_config(tmp_path)
    (config.saves_path / "a.srm").write_bytes(b"v1")
    run_sync(config, tmp_path)
    (config.saves_path / "a.srm").unlink()
    run_sync(config, tmp_path)
    assert (config.saves_path / "a.srm").read_bytes() == b"v1"  # restored from the sync folder


def test_dry_run_changes_nothing(tmp_path):
    config = sync_config(tmp_path)
    (config.saves_path / "a.srm").write_bytes(b"v1")
    r = run_sync(config, tmp_path, dry_run=True)
    assert r.pushed == 1
    assert not (tmp_path / "cloud").exists() and not (config.data_path / "savesync.json").exists()


def test_states_and_retroarch_flatpak_saves_are_included(tmp_path):
    config = sync_config(tmp_path)
    ra = tmp_path / "ra-saves"
    ra.mkdir()
    (ra / "g.srm").write_bytes(b"x")
    (config.savestate_path / "s").mkdir()
    (config.savestate_path / "s" / "1.state").write_bytes(b"y")
    r = savesync.sync(config, retroarch_saves=ra)
    assert r.pushed == 2
    assert (tmp_path / "cloud" / "Arcadia" / "retroarch" / "g.srm").is_file()
    assert (tmp_path / "cloud" / "Arcadia" / "states" / "s" / "1.state").is_file()
    config.ra_saves_in_home = True
    assert "retroarch" not in savesync.sources(config, ra)


def test_unsafe_or_missing_sync_folders_are_refused(tmp_path):
    config = make_config(tmp_path)
    with pytest.raises(savesync.SyncError):
        savesync.sync(config)
    config.sync_dir = str(config.saves_path / "inside")
    with pytest.raises(savesync.SyncError):
        savesync.sync(config)
    config.sync_dir = str(tmp_path)  # contains the Arcadia folder
    with pytest.raises(savesync.SyncError):
        savesync.sync(config)


def test_temp_files_are_ignored(tmp_path):
    config = sync_config(tmp_path)
    (config.saves_path / "a.srm.tmp").write_bytes(b"half")
    (config.saves_path / ".hidden").write_bytes(b"h")
    assert run_sync(config, tmp_path).changed == 0


# ----- backup includes saves -----

def test_backup_round_trips_the_saves_folder(tmp_path):
    config = make_config(tmp_path)
    cfg_path = tmp_path / "config.json"
    config.save(cfg_path)
    (config.saves_path / "g.srm").write_bytes(b"precious")
    result = create_backup(config, cfg_path, now=datetime(2026, 1, 1, 1, 1, 1))
    (config.saves_path / "g.srm").write_bytes(b"ruined")
    restore_backup(config, cfg_path, result.path, now=datetime(2026, 1, 1, 1, 2, 3))
    assert (config.saves_path / "g.srm").read_bytes() == b"precious"


# ----- Google Drive through rclone -----

class FakeRclone:
    """Stands in for rclone: remote "gd:x" is the folder <cloud>/x, and `copy` never deletes."""

    def __init__(self, cloud: Path, fail=None):
        self.cloud, self.calls, self.fail = cloud, [], fail

    def _path(self, spec):
        return self.cloud / spec.split(":", 1)[1] if ":" in spec and not spec.startswith("/") else Path(spec)

    def __call__(self, cmd, **kw):
        import shutil as sh
        import types

        self.calls.append(cmd)
        if cmd[:2] == ["rclone", "listremotes"]:
            return types.SimpleNamespace(returncode=0, stdout="gd: drive\nold: dropbox\n", stderr="")
        assert cmd[:3] == ["rclone", "copy", "--"]
        if self.fail:
            return types.SimpleNamespace(returncode=1, stdout="", stderr=self.fail)
        src, dest = self._path(cmd[3]), self._path(cmd[4])
        if src.is_dir():
            sh.copytree(src, dest, dirs_exist_ok=True)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")


HAVE = lambda _: "/usr/bin/rclone"  # noqa: E731


def remote_config(tmp_path):
    config = make_config(tmp_path)
    config.sync_remote = "gd:Saves"
    return config


def test_two_devices_share_saves_through_a_remote(tmp_path):
    cloud = tmp_path / "cloud"
    rc = FakeRclone(cloud)
    deck = remote_config(tmp_path / "deck")
    pc = remote_config(tmp_path / "pc")
    (deck.saves_path / "g.srm").write_bytes(b"from deck")
    r = savesync.sync_remote(deck, retroarch_saves=tmp_path / "x", run=rc, which=HAVE)
    assert r.pushed == 1 and (cloud / "Saves" / "Arcadia" / "saves" / "g.srm").read_bytes() == b"from deck"
    r = savesync.sync_remote(pc, retroarch_saves=tmp_path / "x", run=rc, which=HAVE)
    assert r.pulled == 1 and (pc.saves_path / "g.srm").read_bytes() == b"from deck"
    (pc.saves_path / "g.srm").write_bytes(b"pc progress")
    savesync.sync_remote(pc, retroarch_saves=tmp_path / "x", run=rc, which=HAVE)
    r = savesync.sync_remote(deck, retroarch_saves=tmp_path / "x", run=rc, which=HAVE)
    assert r.pulled == 1 and (deck.saves_path / "g.srm").read_bytes() == b"pc progress"
    assert all(c[:3] == ["rclone", "copy", "--"] for c in rc.calls)  # only ever `copy`: nothing is deleted


def test_remote_preview_does_not_upload(tmp_path):
    rc = FakeRclone(tmp_path / "cloud")
    config = remote_config(tmp_path)
    (config.saves_path / "g.srm").write_bytes(b"x")
    r = savesync.sync_remote(config, dry_run=True, retroarch_saves=tmp_path / "x", run=rc, which=HAVE)
    assert r.pushed == 1 and not (tmp_path / "cloud" / "Saves" / "Arcadia").exists()


def test_rclone_failures_and_bad_input_are_reported(tmp_path):
    config = remote_config(tmp_path)
    with pytest.raises(savesync.SyncError, match="quota"):
        savesync.sync_remote(config, run=FakeRclone(tmp_path / "c", fail="quota exceeded"), which=HAVE)
    with pytest.raises(savesync.SyncError, match="isn't installed"):
        savesync.sync_remote(config, which=lambda _: None)
    for bad in ("", "no-colon", "-flag:x", "a:b\nc"):
        config.sync_remote = bad
        with pytest.raises(savesync.SyncError):
            savesync.sync_remote(config, run=FakeRclone(tmp_path / "c"), which=HAVE)


def test_listing_remotes_and_choosing_the_target(tmp_path):
    assert savesync.rclone_remotes(FakeRclone(tmp_path), HAVE) == [("gd:", "drive"), ("old:", "dropbox")]
    with pytest.raises(savesync.SyncError):
        savesync.rclone_remotes(which=lambda _: None)
    config = make_config(tmp_path)
    config.sync_remote = ""
    config.sync_dir = str(tmp_path / "folder")
    (config.saves_path / "g.srm").write_bytes(b"x")
    savesync.run_sync(config, retroarch_saves=tmp_path / "x")  # no remote set: uses the folder
    assert (tmp_path / "folder" / "Arcadia" / "saves" / "g.srm").is_file()


def test_google_drive_via_rclone_is_the_default_but_old_folder_configs_keep_working(tmp_path):
    assert Config.new_install(tmp_path).sync_remote == "gdrive:Arcadia"
    import json
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"sync_dir": "/mnt/sd"}))
    old = Config.load(path)
    assert old.sync_remote == "" and old.sync_dir == "/mnt/sd"
    path.write_text(json.dumps({"rom_root": "/r"}))
    assert Config.load(path).sync_remote == "gdrive:Arcadia"
