import io
import subprocess
import zipfile

import pytest

from arcadia import appupdate
from arcadia.emulators import EmulatorError


class FakeFetcher:
    api_base = "https://api.github.com"

    def __init__(self, remote, compare=None, files=None):
        self.remote, self.compare, self.files = remote, compare, files

    def get_json(self, url):
        if "/commits/" in url:
            return {"sha": self.remote}
        if "/compare/" in url:
            if self.compare is None:
                raise EmulatorError("that release or file wasn't found")
            return self.compare
        raise AssertionError(url)

    def download(self, url, dest, progress=None):
        dest.write_bytes(self.files)
        return "x"


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


def make_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "arcadia").mkdir()
    (path / "arcadia" / "__init__.py").write_text("v1")
    (path / "requirements.txt").write_text("a\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "one")
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_up_to_date_and_behind(tmp_path):
    sha = make_repo(tmp_path / "app")
    assert not appupdate.check(tmp_path / "app", "main", fetcher=FakeFetcher(sha)).available
    cmp = {"status": "ahead", "commits": [{"commit": {"message": "second\n\nbody"}}, {"commit": {"message": "first"}}]}
    st = appupdate.check(tmp_path / "app", "main", fetcher=FakeFetcher("b" * 40, cmp))
    assert st.available and st.changes == ["first", "second"]
    # your copy is ahead of GitHub: nothing to do
    assert not appupdate.check(tmp_path / "app", "main", fetcher=FakeFetcher("c" * 40, {"status": "behind"})).available
    # your commit unknown to GitHub: still offered, with a note
    odd = appupdate.check(tmp_path / "app", "main", fetcher=FakeFetcher("d" * 40, None))
    assert odd.available and odd.note


def test_git_update_fast_forwards(tmp_path):
    upstream = tmp_path / "up"
    make_repo(upstream)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
    (upstream / "arcadia" / "__init__.py").write_text("v2")
    (upstream / "requirements.txt").write_text("a\nb\n")
    git(upstream, "commit", "-qam", "two")
    new = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    status = appupdate.Status(True, "main", None, new)
    (clone / "arcadia" / "__init__.py").write_text("edited")
    with pytest.raises(EmulatorError, match="changed files"):
        appupdate.apply(clone, status)
    git(clone, "checkout", "--", ".")
    result = appupdate.apply(clone, status)
    assert (clone / "arcadia" / "__init__.py").read_text() == "v2" and result.requirements_changed


def test_zip_update_keeps_previous(tmp_path):
    root = tmp_path / "app"
    (root / "arcadia").mkdir(parents=True)
    (root / "arcadia" / "__init__.py").write_text("old")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("arcadia-esde-abc/arcadia/__init__.py", "new")
        zf.writestr("arcadia-esde-abc/README.md", "hi")
    status = appupdate.Status(True, "main", None, "abc1234567")
    appupdate.apply(root, status, fetcher=FakeFetcher("x", files=buf.getvalue()))
    assert (root / "arcadia" / "__init__.py").read_text() == "new"
    assert (root / ".previous" / "arcadia" / "__init__.py").read_text() == "old"
    assert (root / appupdate.MARKER).read_text().strip() == "abc1234567"
    assert appupdate.local_commit(root) == "abc1234567"


def test_zip_that_is_not_arcadia_changes_nothing(tmp_path):
    root = tmp_path / "app"
    (root / "arcadia").mkdir(parents=True)
    (root / "arcadia" / "__init__.py").write_text("old")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other/readme", "x")
    with pytest.raises(EmulatorError):
        appupdate.apply(root, appupdate.Status(True, "main", None, "abc"), fetcher=FakeFetcher("x", files=buf.getvalue()))
    assert (root / "arcadia" / "__init__.py").read_text() == "old"
