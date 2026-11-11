"""The launcher and installer scripts (run with their dry-run / skip-pip switches)."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else "python3"


def run(script, *args, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "SteamGameId")}
    e.update(env)
    return subprocess.run(["bash", str(ROOT / script), *args], env=e, capture_output=True, text=True)


def test_syntax():
    for s in ("arcadia.sh", "install.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / s)]).returncode == 0


def test_fullscreen_default_and_windowed(tmp_path):
    env = dict(ARCADIA_DRY_RUN="1", ARCADIA_PYTHON=PY, ARCADIA_VENV=str(tmp_path / "none"), XDG_DATA_HOME=str(tmp_path))
    assert "--fullscreen" in run("arcadia.sh", **env).stdout
    out = run("arcadia.sh", "--windowed", "--home", "/tmp/x", **env).stdout
    assert "--fullscreen" not in out and "--windowed" not in out and "--home /tmp/x" in out


def test_not_installed_message(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python3").write_text("#!/bin/sh\nexit 1\n")  # a python3 without PySide6
    (fake / "python3").chmod(0o755)
    env = dict(ARCADIA_VENV=str(tmp_path / "none"), XDG_DATA_HOME=str(tmp_path))
    r = run("arcadia.sh", **env, PATH=f"{fake}:/usr/bin:/bin")
    assert r.returncode == 1 and "install.sh" in r.stderr


def test_install_and_uninstall(tmp_path):
    env = dict(ARCADIA_SKIP_PIP="1", ARCADIA_VENV=str(tmp_path / "venv"), ARCADIA_DESKTOP_DIR=str(tmp_path / "apps"), XDG_DATA_HOME=str(tmp_path))
    assert run("install.sh", **env).returncode == 0
    entry = (tmp_path / "apps" / "arcadia.desktop").read_text()
    assert f'Exec="{ROOT}/arcadia.sh"' in entry and (ROOT / "arcadia/assets/icon.png").is_file()
    assert (tmp_path / "venv" / "bin" / "python").exists()
    assert run("install.sh", "--uninstall", **env).returncode == 0
    assert not (tmp_path / "venv").exists() and not (tmp_path / "apps" / "arcadia.desktop").exists()
