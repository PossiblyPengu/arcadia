"""Updating every emulator at once."""

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from arcadia.config import Config
from arcadia.emulators import CATALOG, Asset, EmulatorError, Installer
from arcadia.updates import (
    CHOOSE,
    CURRENT,
    ERROR,
    NO_BUILD,
    READY,
    apply_updates,
    flatpaks_in_use,
    installed_flatpaks,
    pick_same_build,
    plan_updates,
    skeleton,
    update_flatpaks,
)
from test_emulators import APPIMAGE, fetcher_for, install_from, publish, server  # noqa: F401


def assets(*names):
    return tuple(Asset(n, f"https://github.com/x/{n}", 1) for n in names)


# ======================= finding the same build =======================

@pytest.mark.parametrize(
    "a, b",
    [
        ("Eden-Linux-v0.2.1-steamdeck-gcc-standard.AppImage", "Eden-Linux-v0.2.2-steamdeck-gcc-standard.AppImage"),
        ("pcsx2-v2.2.0-linux-appimage-x64-Qt.AppImage", "pcsx2-v2.10.1-linux-appimage-x64-Qt.AppImage"),
        ("mGBA-0.10.5-appimage-x64.appimage", "mGBA-0.11.0-appimage-x64.appimage"),
        ("rpcs3-v0.0.30-16343-a1b2c3d4_linux64.AppImage", "rpcs3-v0.0.31-16401-9f8e7d6c5b_linux64.AppImage"),
    ],
)
def test_the_same_build_has_the_same_skeleton_across_versions(a, b):
    assert skeleton(a) == skeleton(b)


def test_different_builds_have_different_skeletons():
    assert skeleton("Eden-Linux-v0.2.1-steamdeck-gcc-standard.AppImage") != skeleton("Eden-Linux-v0.2.1-amd64-gcc-standard.AppImage")
    assert skeleton("Eden-Linux-v1-amd64-gcc-standard.AppImage") != skeleton("Eden-Linux-v1-amd64-clang-pgo.AppImage")


def test_an_update_keeps_the_variant_that_was_installed():
    new = assets(
        "Eden-Linux-v0.2.2-amd64-gcc-standard.AppImage",
        "Eden-Linux-v0.2.2-amd64-clang-pgo.AppImage",
        "Eden-Linux-v0.2.2-legacy-gcc-standard.AppImage",
        "Eden-Linux-v0.2.2-steamdeck-gcc-standard.AppImage",
        "Eden-Linux-v0.2.2-steamdeck-clang-pgo.AppImage",
    )
    assert pick_same_build("Eden-Linux-v0.2.1-steamdeck-gcc-standard.AppImage", new).name == "Eden-Linux-v0.2.2-steamdeck-gcc-standard.AppImage"
    assert pick_same_build("Eden-Linux-v0.2.1-amd64-clang-pgo.AppImage", new).name == "Eden-Linux-v0.2.2-amd64-clang-pgo.AppImage"


def test_when_the_same_build_cannot_be_told_nothing_is_picked():
    assert pick_same_build("Old-name-v1.AppImage", assets("Totally-different-v2.AppImage")) is None  # the naming changed
    assert pick_same_build("Game-v1-x64.AppImage", assets("Game-v2-x64.AppImage", "Game-v3-x64.AppImage")) is None  # two fit equally
    assert pick_same_build("Game-v1.AppImage", ()) is None


# ======================= planning =======================

@pytest.fixture
def installer(tmp_path, server):
    base, _routes = server
    return Installer(tmp_path / "emulators", fetcher_for(base))


def put_installed(installer, base, routes, spec, name, tag="v1", digest="correct"):
    publish(base, routes, {name: APPIMAGE}, tag=tag, digest=digest, repo=spec.repo)
    release = installer.latest_release(spec)
    return installer.install(spec, release, release.assets[0])


def test_a_newer_release_of_the_same_build_is_ready_to_install(installer, server):
    base, routes = server
    spec = CATALOG["pcsx2"]
    put_installed(installer, base, routes, spec, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "v1")
    publish(base, routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE, "pcsx2-v2-windows-x64.7z": b"w"}, tag="v2", repo=spec.repo)
    (row,) = plan_updates(installer)
    assert (row.status, row.newer, row.asset.name) == (READY, "v2", "pcsx2-v2-linux-appimage-x64-Qt.AppImage")
    assert row.installed.version == "v1"


def test_an_emulator_already_on_the_latest_release_is_current(installer, server):
    base, routes = server
    spec = CATALOG["pcsx2"]
    put_installed(installer, base, routes, spec, "pcsx2-linux-appimage-x64-Qt.AppImage", "v5")
    (row,) = plan_updates(installer)
    assert row.status == CURRENT and row.asset is None


def test_if_the_naming_changed_the_user_chooses_from_the_new_builds(installer, server):
    base, routes = server
    spec = CATALOG["pcsx2"]
    put_installed(installer, base, routes, spec, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "v1")
    publish(base, routes, {"pcsx2-v2-linux-x86_64.AppImage": APPIMAGE, "pcsx2-v2-linux-x86_64-legacy.AppImage": APPIMAGE}, tag="v2", repo=spec.repo)
    (row,) = plan_updates(installer)
    assert row.status == CHOOSE and row.asset is None
    assert {a.name for a in row.choices} == {"pcsx2-v2-linux-x86_64.AppImage", "pcsx2-v2-linux-x86_64-legacy.AppImage"}
    assert "same build" in row.message


def test_a_release_with_no_linux_build_is_reported_not_attempted(installer, server):
    base, routes = server
    spec = CATALOG["pcsx2"]
    put_installed(installer, base, routes, spec, "pcsx2-linux-appimage-x64-Qt.AppImage", "v1")
    publish(base, routes, {"pcsx2-windows.7z": b"w"}, tag="v2", repo=spec.repo)
    (row,) = plan_updates(installer)
    assert row.status == NO_BUILD and "no Linux" in row.message


def test_a_lookup_that_fails_is_reported_for_that_emulator_only(installer, server):
    base, routes = server
    pcsx2, mgba = CATALOG["pcsx2"], CATALOG["mgba"]
    put_installed(installer, base, routes, pcsx2, "pcsx2-linux-appimage-x64-Qt.AppImage", "v1")
    put_installed(installer, base, routes, mgba, "mGBA-1-appimage-x64.appimage", "1")
    del routes[f"/repos/{pcsx2.repo}/releases/latest"]  # pcsx2's release page has gone
    publish(base, routes, {"mGBA-2-appimage-x64.appimage": APPIMAGE}, tag="2", repo=mgba.repo)
    rows = {r.spec.id: r for r in plan_updates(installer)}
    assert rows["pcsx2"].status == ERROR and "wasn't found" in rows["pcsx2"].message
    assert rows["mgba"].status == READY  # the other one is unaffected


def test_only_installed_emulators_are_looked_up(installer):
    assert plan_updates(installer) == []  # nothing installed, so nothing is fetched


def test_a_steam_deck_build_of_eden_stays_a_steam_deck_build(installer, server):
    base, routes = server
    eden = dataclasses.replace(CATALOG["eden"], api=f"{base}/api/v1/repos/{{repo}}/releases/latest", hosts=("localhost",))
    port = base.rsplit(":", 1)[1]

    def publish_eden(tag):
        listed = []
        for variant in ("amd64-gcc-standard", "steamdeck-gcc-standard", "steamdeck-clang-pgo", "legacy-gcc-standard"):
            name = f"Eden-Linux-{tag}-{variant}.AppImage"
            routes[f"/dl/{name}"] = (200, {}, APPIMAGE + tag.encode())
            listed.append({"name": name, "size": 1, "browser_download_url": f"http://localhost:{port}/dl/{name}"})
        routes["/api/v1/repos/eden-emu/eden/releases/latest"] = (200, {}, json.dumps({"tag_name": tag, "assets": listed}).encode())

    publish_eden("v1")
    release = installer.latest_release(eden)
    steamdeck = next(a for a in release.assets if "steamdeck-gcc-standard" in a.name)
    installer.install(eden, release, steamdeck)  # the user chose the Steam Deck build

    publish_eden("v2")
    (row,) = plan_updates(installer, [eden])
    assert row.status == READY and row.asset.name == "Eden-Linux-v2-steamdeck-gcc-standard.AppImage"  # not amd64, not clang-pgo


# ======================= applying =======================

def test_applying_updates_installs_each_and_keeps_every_emulators_own_data(installer, server, tmp_path):
    base, routes = server
    pcsx2, mgba = CATALOG["pcsx2"], CATALOG["mgba"]
    put_installed(installer, base, routes, pcsx2, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "v1")
    put_installed(installer, base, routes, mgba, "mGBA-1-appimage-x64.appimage", "1")
    for emu in ("pcsx2", "mgba"):
        (tmp_path / "emulators" / emu / "config").mkdir(exist_ok=True)
        (tmp_path / "emulators" / emu / "config" / "settings.ini").write_text(f"my {emu} settings")
    publish(base, routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE + b"2"}, tag="v2", repo=pcsx2.repo)
    publish(base, routes, {"mGBA-2-appimage-x64.appimage": APPIMAGE + b"2"}, tag="2", repo=mgba.repo)

    rows = plan_updates(installer)
    seen = []
    outcomes = apply_updates(installer, [(r, r.asset) for r in rows], progress=lambda done, total: seen.append((done, total)))
    assert [(o.spec.id, o.ok, o.version) for o in outcomes] == [("pcsx2", True, "v2"), ("mgba", True, "2")]
    assert installer.get("pcsx2").version == "v2" and installer.get("mgba").version == "2"
    for emu in ("pcsx2", "mgba"):
        assert (tmp_path / "emulators" / emu / "config" / "settings.ini").read_text() == f"my {emu} settings"
    assert seen[-1] == (200, 200) and [d for d, _ in seen] == sorted(d for d, _ in seen)  # progress only moves forward


def test_one_failing_update_does_not_stop_the_others_or_damage_its_own_emulator(installer, server):
    base, routes = server
    pcsx2, mgba = CATALOG["pcsx2"], CATALOG["mgba"]
    put_installed(installer, base, routes, pcsx2, "pcsx2-v1-linux-appimage-x64-Qt.AppImage", "v1")
    put_installed(installer, base, routes, mgba, "mGBA-1-appimage-x64.appimage", "1")
    publish(base, routes, {"pcsx2-v2-linux-appimage-x64-Qt.AppImage": APPIMAGE + b"2"}, tag="v2", digest="wrong", repo=pcsx2.repo)
    publish(base, routes, {"mGBA-2-appimage-x64.appimage": APPIMAGE + b"2"}, tag="2", repo=mgba.repo)

    rows = plan_updates(installer)
    outcomes = {o.spec.id: o for o in apply_updates(installer, [(r, r.asset) for r in rows])}
    assert not outcomes["pcsx2"].ok and "checksum" in outcomes["pcsx2"].error
    assert outcomes["mgba"].ok
    assert installer.get("pcsx2").version == "v1" and installer.exe_path(installer.get("pcsx2")).read_bytes() == APPIMAGE  # untouched
    assert installer.get("mgba").version == "2"


def test_nothing_chosen_is_nothing_done(installer):
    assert apply_updates(installer, []) == []


# ======================= Flatpak =======================

def fake_run(listing="net.pcsx2.PCSX2\norg.libretro.RetroArch\n", returncode=0, stderr=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=listing, stderr=stderr)

    run.calls = calls
    return run


def test_the_installed_flatpaks_are_read_from_flatpak():
    run = fake_run()
    assert installed_flatpaks(run, lambda p: "/usr/bin/flatpak") == {"net.pcsx2.PCSX2", "org.libretro.RetroArch"}
    assert run.calls == [["flatpak", "list", "--app", "--columns=application"]]


def test_flatpak_being_unavailable_or_failing_gives_none():
    assert installed_flatpaks(fake_run(), lambda p: None) is None
    assert installed_flatpaks(fake_run(returncode=1), lambda p: "/usr/bin/flatpak") is None

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 60)

    assert installed_flatpaks(boom, lambda p: "/usr/bin/flatpak") is None


def test_only_flatpaks_that_systems_still_use_and_are_installed_are_updated(tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    installer = Installer(config.emulators_path)
    everything = {"net.pcsx2.PCSX2", "org.libretro.RetroArch", "io.mgba.mGBA", "org.unrelated.App"}
    apps = flatpaks_in_use(config, everything, installer)
    assert "org.unrelated.App" not in apps  # not behind any system
    assert "com.snes9x.Snes9x" not in apps  # behind a system but not installed
    assert apps.count("io.mgba.mGBA") == 1 and apps.count("org.libretro.RetroArch") == 1  # shared ones are listed once
    assert set(apps) == {"net.pcsx2.PCSX2", "org.libretro.RetroArch", "io.mgba.mGBA"}


def test_an_emulator_installed_in_the_arcadia_folder_no_longer_counts_as_a_flatpak(tmp_path):
    config = Config.new_install(tmp_path / "Arcadia")
    installer = Installer(config.emulators_path)
    app = installer.app_dir("pcsx2")
    app.mkdir(parents=True)
    (app / "emu").write_text("x")
    (installer.folder("pcsx2") / "install.json").write_text('{"id":"pcsx2","version":"v1","asset":"a","sha256":"0","verified":true,"exe":"emu"}')
    assert "net.pcsx2.PCSX2" not in flatpaks_in_use(config, {"net.pcsx2.PCSX2", "io.mgba.mGBA"}, installer)


def test_the_flatpak_update_names_only_the_apps_it_was_given():
    run = fake_run(listing="Updating net.pcsx2.PCSX2\nDone\n")
    result = update_flatpaks(["net.pcsx2.PCSX2", "io.mgba.mGBA"], run, lambda p: "/usr/bin/flatpak")
    assert run.calls == [["flatpak", "update", "-y", "--noninteractive", "net.pcsx2.PCSX2", "io.mgba.mGBA"]]  # never "update everything"
    assert result.ok and "Updating net.pcsx2.PCSX2" in result.output and result.apps == ["net.pcsx2.PCSX2", "io.mgba.mGBA"]


def test_flatpak_update_failures_are_reported_with_the_tail_of_the_output():
    noisy = "\n".join(f"line {i}" for i in range(40))
    result = update_flatpaks(["x.y.Z"], fake_run(listing=noisy, returncode=1, stderr="error: no network"), lambda p: "/usr/bin/flatpak")
    assert not result.ok and "error: no network" in result.output and "line 0" not in result.output  # just the end
    assert not update_flatpaks(["x.y.Z"], fake_run(), lambda p: None).ok
    assert update_flatpaks([], fake_run(), lambda p: None).ok  # nothing to do is not a failure

    def boom(cmd, **kw):
        raise OSError("gone")

    assert "couldn't be run" in update_flatpaks(["x.y.Z"], boom, lambda p: "/usr/bin/flatpak").output
