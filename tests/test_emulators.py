"""Installing emulators into their own folders, against a real local HTTP server."""

import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import arcadia.emulators as emulators
from arcadia.config import Config
from arcadia.emulators import (
    CATALOG,
    Asset,
    EmulatorError,
    Fetcher,
    Installer,
    Release,
    candidate_assets,
    parse_release,
)
from arcadia.launcher import LaunchError, resolve_launch

SPEC = CATALOG["pcsx2"]
APPIMAGE = b"\x7fELF fake appimage " + bytes(2000)


# ---------- a local release server ----------

@pytest.fixture
def server():
    routes: dict[str, tuple[int, dict, bytes]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = routes.get(self.path)
            if route is None:
                self.send_response(404)
                self.end_headers()
                return
            status, headers, body = route
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            if "Content-Length" not in headers and status == 200:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if status == 200:
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, routes
    srv.shutdown()
    srv.server_close()


def fetcher_for(base: str) -> Fetcher:
    return Fetcher(api_base=base, hosts=frozenset(), allow_http=True, timeout=5)


def publish(base, routes, assets: dict[str, bytes], tag="v1.0.0", digest="correct", repo="PCSX2/pcsx2"):
    listed = []
    for name, body in assets.items():
        routes[f"/dl/{name}"] = (200, {}, body)
        entry = {"name": name, "browser_download_url": f"{base}/dl/{name}", "size": len(body)}
        if digest == "correct":
            entry["digest"] = "sha256:" + hashlib.sha256(body).hexdigest()
        elif digest == "wrong":
            entry["digest"] = "sha256:" + "0" * 64
        listed.append(entry)
    routes[f"/repos/{repo}/releases/latest"] = (200, {}, json.dumps({"tag_name": tag, "assets": listed}).encode())


def make_zip(members: dict[str, bytes], modes: dict[str, int] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = ((modes or {}).get(name, 0o644) | stat.S_IFREG) << 16
            zf.writestr(info, data)
    return buf.getvalue()


def make_targz(members: dict[str, tuple[bytes, int]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, (data, mode) in members.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def installer(tmp_path, server):
    base, _routes = server
    return Installer(tmp_path / "emulators", fetcher_for(base))


def install_from(installer, base, routes, assets, pick=None, **publish_kwargs):
    publish(base, routes, assets, **publish_kwargs)
    release = installer.latest_release(SPEC)
    asset = next(a for a in release.assets if a.name == (pick or next(iter(assets))))
    return installer.install(SPEC, release, asset)


# ======================= release parsing and choosing a build =======================

def test_parse_release_reads_version_assets_and_checksums():
    release = parse_release(
        {
            "tag_name": "v2.2.0",
            "assets": [
                {"name": "a.AppImage", "browser_download_url": "https://github.com/x/a.AppImage", "size": 10, "digest": "sha256:ABCDEF"},
                {"name": "b.zip", "browser_download_url": "https://github.com/x/b.zip", "size": 5},
                {"name": "broken", "browser_download_url": ""},
                {"browser_download_url": "https://github.com/x/nameless"},
            ],
        },
        "PCSX2/pcsx2",
    )
    assert release.tag == "v2.2.0" and release.page == "https://github.com/PCSX2/pcsx2/releases/tag/v2.2.0"
    assert [a.name for a in release.assets] == ["a.AppImage", "b.zip"]
    assert release.assets[0].digest == "abcdef" and release.assets[1].digest == ""
    with pytest.raises(EmulatorError):
        parse_release({"assets": []})


def _release(*names):
    return Release("v1", tuple(Asset(n, f"https://github.com/x/{n}", 100) for n in names))


def test_only_linux_x86_64_builds_we_can_unpack_are_offered():
    release = _release(
        "pcsx2-v2.2.0-linux-appimage-x64-Qt.AppImage",
        "pcsx2-v2.2.0-linux-appimage-x64-Qt.AppImage.zsync",
        "pcsx2-v2.2.0-linux-appimage-arm64-Qt.AppImage",
        "pcsx2-v2.2.0-linux-flatpak-x64-Qt.flatpak",
        "pcsx2-v2.2.0-windows-x64-Qt.7z",
        "pcsx2-v2.2.0-windows-x64-Qt.zip",
        "pcsx2-v2.2.0-macos-Qt.tar.xz",
        "SHA256SUMS.txt",
        "Source code.tar.gz",
        "pcsx2-v2.2.0-linux-x64-debug-symbols.tar.xz",
    )
    found = candidate_assets(SPEC, release)
    assert [a.name for a in found.assets] == ["pcsx2-v2.2.0-linux-appimage-x64-Qt.AppImage"]
    assert found.preselected.name == "pcsx2-v2.2.0-linux-appimage-x64-Qt.AppImage"


def test_nothing_is_preselected_when_no_known_pattern_matches():
    found = candidate_assets(SPEC, _release("tool-linux-x86_64.tar.gz", "tool-linux-x86_64-extra.zip"))
    assert len(found.assets) == 2 and found.preselected is None  # the user chooses; we don't guess


def test_known_patterns_decide_the_order():
    release = _release("zzz-linux-x64.AppImage", "pcsx2-linux-appimage-x64-Qt.AppImage")
    found = candidate_assets(SPEC, release)
    assert found.assets[0].name == "pcsx2-linux-appimage-x64-Qt.AppImage" and found.preselected is found.assets[0]


def test_a_release_with_no_linux_build_offers_nothing():
    found = candidate_assets(SPEC, _release("pcsx2-windows-x64.7z", "pcsx2-macos.tar.xz", "notes.txt"))
    assert found.assets == () and found.preselected is None


def test_every_catalog_entry_is_well_formed():
    for spec in CATALOG.values():
        assert "/" in spec.repo and spec.prefer and spec.args and spec.flatpak and spec.systems, spec.id
    from arcadia.presets import PRESETS
    for spec in CATALOG.values():
        for system in spec.systems:
            assert PRESETS[system].emulator == spec.id, (spec.id, system)  # the preset points back at it
            assert spec.flatpak in PRESETS[system].command  # and the fallback is the same emulator


# ======================= the fetcher's safety rules =======================

def test_the_fetcher_only_talks_to_known_hosts_over_https():
    f = Fetcher()
    f.check_url("https://github.com/o/r/releases/download/v1/a.AppImage")
    f.check_url("https://objects.githubusercontent.com/x")
    for bad in ("http://github.com/x", "https://evil.example/x", "ftp://github.com/x", "file:///etc/passwd", "https://github.com.evil.example/x"):
        with pytest.raises(EmulatorError):
            f.check_url(bad)


def test_a_redirect_to_an_unknown_host_is_refused(server, tmp_path):
    base, routes = server
    routes["/go"] = (302, {"Location": "http://evil.example/payload", "Content-Length": "0"}, b"")
    with pytest.raises(EmulatorError, match="refusing to download from evil.example"):
        fetcher_for(base).download(f"{base}/go", tmp_path / "x")
    assert not (tmp_path / "x").exists()


def test_a_redirect_to_an_allowed_place_is_followed(server, tmp_path):
    base, routes = server
    routes["/real"] = (200, {}, b"payload")
    routes["/go"] = (302, {"Location": f"{base}/real", "Content-Length": "0"}, b"")
    sha = fetcher_for(base).download(f"{base}/go", tmp_path / "x")
    assert (tmp_path / "x").read_bytes() == b"payload" and sha == hashlib.sha256(b"payload").hexdigest()


def test_http_errors_become_friendly_messages(server, tmp_path):
    base, routes = server
    with pytest.raises(EmulatorError, match="wasn't found"):
        fetcher_for(base).get_json(f"{base}/nothing")
    routes["/limited"] = (403, {"x-ratelimit-remaining": "0", "Content-Length": "0"}, b"")
    with pytest.raises(EmulatorError, match="limiting requests"):
        fetcher_for(base).get_json(f"{base}/limited")
    routes["/bad"] = (200, {}, b"not json")
    with pytest.raises(EmulatorError, match="couldn't be read"):
        fetcher_for(base).get_json(f"{base}/bad")
    routes["/list"] = (200, {}, b"[1, 2]")
    with pytest.raises(EmulatorError, match="expected form"):
        fetcher_for(base).get_json(f"{base}/list")
    with pytest.raises(EmulatorError, match="couldn't reach"):
        fetcher_for("http://127.0.0.1:1").get_json("http://127.0.0.1:1/x")


def test_an_oversized_download_is_refused_and_leaves_nothing(server, tmp_path, monkeypatch):
    base, routes = server
    routes["/big"] = (200, {}, b"x" * 5000)
    monkeypatch.setattr(emulators, "MAX_DOWNLOAD", 1000)
    with pytest.raises(EmulatorError, match="larger than"):
        fetcher_for(base).download(f"{base}/big", tmp_path / "big")
    assert not (tmp_path / "big").exists()


# ======================= installing =======================

def test_install_an_appimage_into_its_own_folder(installer, server, tmp_path):
    base, routes = server
    seen = []
    publish(base, routes, {"pcsx2-linux-x64.AppImage": APPIMAGE})
    release = installer.latest_release(SPEC)
    inst = installer.install(SPEC, release, release.assets[0], lambda done, total: seen.append((done, total)))

    folder = tmp_path / "emulators" / "pcsx2"
    exe = folder / "app" / "pcsx2-linux-x64.AppImage"
    assert exe.read_bytes() == APPIMAGE and os.access(exe, os.X_OK)
    assert inst.version == "v1.0.0" and inst.verified is True and inst.exe == "pcsx2-linux-x64.AppImage"
    assert inst.sha256 == hashlib.sha256(APPIMAGE).hexdigest()
    assert seen and seen[-1] == (len(APPIMAGE), len(APPIMAGE))
    assert sorted(p.name for p in folder.iterdir()) == ["app", "install.json"]  # no staging left behind

    again = installer.get("pcsx2")
    assert again == inst and installer.exe_path(again) == exe
    assert list(installer.installed()) == ["pcsx2"]


def test_without_a_published_checksum_the_install_is_marked_unverified(installer, server):
    base, routes = server
    inst = install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE}, digest="none")
    assert inst.verified is False and inst.sha256 == hashlib.sha256(APPIMAGE).hexdigest()  # still recorded


def test_a_checksum_mismatch_installs_nothing(installer, server, tmp_path):
    base, routes = server
    with pytest.raises(EmulatorError, match="doesn't match the checksum"):
        install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE}, digest="wrong")
    folder = tmp_path / "emulators" / "pcsx2"
    assert not (folder / "app").exists() and not (folder / "install.json").exists()
    assert [p.name for p in folder.iterdir()] == []  # the thrown-away download isn't kept either
    assert installer.get("pcsx2") is None


def test_install_a_zip_whose_program_is_in_a_subfolder(installer, server, tmp_path):
    base, routes = server
    archive = make_zip(
        {"RMG-Portable/RMG": b"\x7fELF program", "RMG-Portable/Lib/libthing.so": b"lib", "RMG-Portable/readme.txt": b"hi"},
        modes={"RMG-Portable/RMG": 0o755},
    )
    spec = CATALOG["rmg"]
    publish(base, routes, {"RMG-Portable-Linux64.zip": archive}, repo=spec.repo)
    release = installer.latest_release(spec)
    inst = installer.install(spec, release, release.assets[0])
    assert inst.exe == "RMG-Portable/RMG"
    exe = installer.exe_path(inst)
    assert os.access(exe, os.X_OK) and (exe.parent / "Lib" / "libthing.so").exists()


def test_install_a_tarball_even_when_the_program_has_no_execute_bit(installer, server):
    base, routes = server
    archive = make_targz({"mgba/mgba-qt": (b"\x7fELF", 0o644), "mgba/data.bin": (b"d", 0o644)})
    spec = CATALOG["mgba"]
    spec = type(spec)(**{**spec.__dict__, "exe": r"mgba-qt$"})
    publish(base, routes, {"mgba-linux.tar.gz": archive}, repo=spec.repo)
    inst = installer.install(spec, installer.latest_release(spec), installer.latest_release(spec).assets[0])
    assert inst.exe == "mgba/mgba-qt" and os.access(installer.exe_path(inst), os.X_OK)  # made executable for you


def test_an_appimage_inside_a_zip_is_found(installer, server):
    base, routes = server
    publish(base, routes, {"melonDS-appimage-x86_64.zip": make_zip({"melonDS-x86_64.AppImage": b"\x7fELF"})}, repo="melonDS-emu/melonDS")
    spec = CATALOG["melonds"]
    release = installer.latest_release(spec)
    inst = installer.install(spec, release, release.assets[0])
    assert inst.exe == "melonDS-x86_64.AppImage"


# ======================= unsafe or odd downloads =======================

def test_zip_paths_cannot_escape_the_install_folder(installer, server, tmp_path):
    base, routes = server
    for evil in ("../evil.txt", "app/../../evil.txt", "/etc/evil.txt", "..\\evil.txt"):
        routes.clear()
        archive = make_zip({"ok/pcsx2": b"\x7fELF", evil: b"pwned"})
        publish(base, routes, {"pcsx2-linux-x64.zip": archive})
        release = installer.latest_release(SPEC)
        with pytest.raises(EmulatorError, match="unsafe path"):
            installer.install(SPEC, release, release.assets[0])
    assert not list(tmp_path.rglob("evil.txt"))
    assert installer.get("pcsx2") is None


def test_tar_paths_cannot_escape_and_links_are_skipped(installer, server, tmp_path):
    base, routes = server
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("../evil")
        info.size = 5
        tf.addfile(info, io.BytesIO(b"pwned"))
    publish(base, routes, {"pcsx2-linux.tar.gz": buf.getvalue()})
    release = installer.latest_release(SPEC)
    with pytest.raises(EmulatorError, match="unsafe path"):
        installer.install(SPEC, release, release.assets[0])
    assert not list(tmp_path.rglob("evil"))

    routes.clear()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        link = tarfile.TarInfo("pcsx2/escape")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tf.addfile(link)
        real = tarfile.TarInfo("pcsx2/pcsx2")
        real.size, real.mode = 4, 0o755
        tf.addfile(real, io.BytesIO(b"ELF!"))
    publish(base, routes, {"pcsx2-linux.tar.gz": buf.getvalue()})
    release = installer.latest_release(SPEC)
    inst = installer.install(SPEC, release, release.assets[0])
    assert not (installer.app_dir("pcsx2") / "pcsx2" / "escape").exists()  # the link was skipped
    assert inst.exe == "pcsx2/pcsx2"


def test_zip_symlinks_are_skipped(installer, server):
    base, routes = server
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        link = zipfile.ZipInfo("pcsx2/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")
        prog = zipfile.ZipInfo("pcsx2/pcsx2")
        prog.external_attr = (stat.S_IFREG | 0o755) << 16
        zf.writestr(prog, b"ELF!")
    publish(base, routes, {"pcsx2-linux.zip": buf.getvalue()})
    release = installer.latest_release(SPEC)
    inst = installer.install(SPEC, release, release.assets[0])
    assert not (installer.app_dir("pcsx2") / "pcsx2" / "link").exists() and inst.exe == "pcsx2/pcsx2"


def test_a_download_that_is_not_a_known_archive_is_refused(installer, server):
    base, routes = server
    publish(base, routes, {"pcsx2-linux.AppImage.zip": b"this is not a zip"})
    release = installer.latest_release(SPEC)
    with pytest.raises(EmulatorError, match="couldn't be unpacked"):
        installer.install(SPEC, release, release.assets[0])
    publish(base, routes, {"pcsx2-linux.bin": b"x"})
    release = installer.latest_release(SPEC)
    with pytest.raises(EmulatorError, match="don't know how to unpack"):
        installer.install(SPEC, release, release.assets[0])


def test_an_archive_with_no_program_or_with_several_is_not_guessed_at(installer, server):
    base, routes = server
    publish(base, routes, {"pcsx2-linux.zip": make_zip({"docs/readme.txt": b"hi", "lib/a.so": b"x"})})
    release = installer.latest_release(SPEC)
    with pytest.raises(EmulatorError, match="couldn't find the program"):
        installer.install(SPEC, release, release.assets[0])
    publish(base, routes, {"pcsx2-linux.zip": make_zip({"a/one.AppImage": b"1", "b/two.AppImage": b"2"})})
    release = installer.latest_release(SPEC)
    with pytest.raises(EmulatorError, match="couldn't tell which file"):
        installer.install(SPEC, release, release.assets[0])


# ======================= updating and removing =======================

def test_updating_replaces_the_program_but_never_the_emulators_own_data(installer, server, tmp_path):
    base, routes = server
    install_from(installer, base, routes, {"pcsx2.AppImage": b"\x7fELF v1"}, tag="v1")
    folder = tmp_path / "emulators" / "pcsx2"
    for sub in ("config", "data"):
        (folder / sub).mkdir(exist_ok=True)
    (folder / "config" / "settings.ini").write_text("my settings")
    (folder / "data" / "memcards.bin").write_text("my saves")

    inst = install_from(installer, base, routes, {"pcsx2.AppImage": b"\x7fELF v2"}, tag="v2")
    assert inst.version == "v2" and installer.exe_path(inst).read_bytes() == b"\x7fELF v2"
    assert (folder / "config" / "settings.ini").read_text() == "my settings"
    assert (folder / "data" / "memcards.bin").read_text() == "my saves"
    assert not (folder / ".app.previous").exists()


def test_a_failed_update_leaves_the_working_copy_alone(installer, server):
    base, routes = server
    install_from(installer, base, routes, {"pcsx2.AppImage": b"\x7fELF v1"}, tag="v1")
    with pytest.raises(EmulatorError):
        install_from(installer, base, routes, {"pcsx2.AppImage": b"\x7fELF v2"}, tag="v2", digest="wrong")
    inst = installer.get("pcsx2")
    assert inst.version == "v1" and installer.exe_path(inst).read_bytes() == b"\x7fELF v1"


def test_update_available_compares_versions(installer, server):
    base, routes = server
    install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE}, tag="v1")
    assert installer.update_available(SPEC, Release("v1", ())) is False
    assert installer.update_available(SPEC, Release("v2", ())) is True
    assert installer.update_available(CATALOG["cemu"], Release("v9", ())) is False  # not installed: nothing to update


def test_remove_keeps_the_data_unless_asked(installer, server, tmp_path):
    base, routes = server
    install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE})
    folder = tmp_path / "emulators" / "pcsx2"
    (folder / "config").mkdir()
    (folder / "config" / "settings.ini").write_text("mine")

    installer.remove("pcsx2")
    assert installer.get("pcsx2") is None and not (folder / "app").exists()
    assert (folder / "config" / "settings.ini").read_text() == "mine"  # settings and saves survive

    install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE})
    installer.remove("pcsx2", delete_data=True)
    assert not folder.exists()


def test_an_installed_emulator_whose_program_was_deleted_counts_as_not_installed(installer, server):
    base, routes = server
    inst = install_from(installer, base, routes, {"pcsx2.AppImage": APPIMAGE})
    installer.exe_path(inst).unlink()
    assert installer.get("pcsx2") is None and installer.installed() == {}


def test_a_damaged_record_is_ignored(installer, tmp_path):
    folder = tmp_path / "emulators" / "pcsx2"
    folder.mkdir(parents=True)
    (folder / "install.json").write_text("{not json")
    assert installer.get("pcsx2") is None


def test_latest_release_asks_the_projects_own_repo(installer, server):
    base, routes = server
    publish(base, routes, {"pcsx2.AppImage": APPIMAGE}, tag="v7")
    assert installer.latest_release(SPEC).tag == "v7"
    with pytest.raises(EmulatorError, match="wasn't found"):
        installer.latest_release(CATALOG["cemu"])  # nothing published at that repo


# ======================= keeping an emulator's data in its own folder =======================

def test_launch_env_points_every_xdg_directory_into_the_emulators_folder(installer, tmp_path):
    env = installer.launch_env("pcsx2")
    base = tmp_path / "emulators" / "pcsx2"
    assert env == {
        "XDG_CONFIG_HOME": str(base / "config"),
        "XDG_DATA_HOME": str(base / "data"),
        "XDG_CACHE_HOME": str(base / "cache"),
        "XDG_STATE_HOME": str(base / "state"),
    }
    assert all(Path(v).is_dir() for v in env.values())


# ======================= launching =======================

def _config(tmp_path, **kw):
    return Config.new_install(tmp_path / "Arcadia") if not kw else Config(**kw)


def _install_fake(config, emu_id="pcsx2", script=None):
    installer = Installer(config.emulators_path)
    app = installer.app_dir(emu_id)
    app.mkdir(parents=True)
    exe = app / "emu"
    exe.write_text(script or "#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    record = {"id": emu_id, "version": "v1", "asset": "emu", "sha256": "0" * 64, "verified": True, "exe": "emu"}
    (installer.folder(emu_id) / "install.json").write_text(json.dumps(record))
    return installer, exe


def test_an_installed_emulator_is_launched_instead_of_the_flatpak(tmp_path):
    config = _config(tmp_path)
    installer, exe = _install_fake(config)
    plan = resolve_launch(config, config.system("ps2"), Path("/roms/ps2/Game Name.iso"))
    assert plan.via == "local:pcsx2"
    assert plan.args == [str(exe), "-batch", "--", "/roms/ps2/Game Name.iso"]
    assert plan.env == installer.launch_env("pcsx2")


def test_without_a_local_copy_the_flatpak_command_is_used_as_before(tmp_path):
    config = _config(tmp_path)
    plan = resolve_launch(config, config.system("ps2"), Path("/roms/ps2/G.iso"))
    assert plan.via == "command" and plan.env == {} and plan.args[:3] == ["flatpak", "run", "net.pcsx2.PCSX2"]


def test_a_system_with_no_managed_emulator_always_uses_its_command(tmp_path):
    config = _config(tmp_path)
    _install_fake(config)
    config.system("ps2").emulator = ""  # the user opted out
    assert resolve_launch(config, config.system("ps2"), Path("/r/G.iso")).via == "command"
    assert resolve_launch(config, config.system("snes"), Path("/r/G.sfc")).via == "command"  # none for this system


def test_a_deleted_program_falls_back_rather_than_failing(tmp_path):
    config = _config(tmp_path)
    _installer, exe = _install_fake(config)
    exe.unlink()
    assert resolve_launch(config, config.system("ps2"), Path("/r/G.iso")).via == "command"


def test_a_missing_emulator_with_no_fallback_says_where_to_get_it(tmp_path):
    config = _config(tmp_path)
    config.system("ps2").command = ""
    with pytest.raises(LaunchError, match="PCSX2 isn't installed.*Emulators"):
        resolve_launch(config, config.system("ps2"), Path("/r/G.iso"))


def test_the_placeholders_work_with_a_local_emulator(tmp_path):
    config = _config(tmp_path)
    _install_fake(config, "cemu")
    plan = resolve_launch(config, config.system("wiiu"), Path("/roms/wiiu/Game/code/game.rpx"))
    assert plan.args[1:] == ["-g", "/roms/wiiu/Game/code/game.rpx"]


def test_a_launched_emulator_really_keeps_its_settings_in_its_own_folder(tmp_path):
    config = _config(tmp_path)
    out = tmp_path / "seen.txt"
    script = f'#!/bin/sh\necho "$XDG_CONFIG_HOME|$XDG_DATA_HOME|$@" > "{out}"\nmkdir -p "$XDG_CONFIG_HOME/PCSX2"\necho cfg > "$XDG_CONFIG_HOME/PCSX2/PCSX2.ini"\n'
    installer, _exe = _install_fake(config, script=script)
    plan = resolve_launch(config, config.system("ps2"), Path("/roms/ps2/Game.iso"))
    subprocess.run(plan.args, env={**os.environ, **plan.env}, check=True)

    folder = tmp_path / "Arcadia" / "emulators" / "pcsx2"
    assert out.read_text().startswith(f"{folder / 'config'}|{folder / 'data'}|-batch -- /roms/ps2/Game.iso")
    assert (folder / "config" / "PCSX2" / "PCSX2.ini").read_text() == "cfg\n"  # written inside the emulator's folder
