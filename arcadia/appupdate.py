"""Updates for Arcadia itself, from its GitHub repository.

* Checking asks GitHub (api.github.com) whether the branch you follow has commits yours doesn't.
* Updating a git checkout runs `git merge --ff-only` (refusing if you've changed files, so your edits are
  never overwritten). A copy without git is replaced from GitHub's zip of the same commit instead, after the
  old files are kept in `.previous`.
* Your library, ROMs, saves and settings live in your Arcadia folder, not in the program folder, so an update
  never touches them.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from arcadia.emulators import GITHUB_HOSTS, EmulatorError, Fetcher, _extract_zip

REPO = "PossiblyPengu/arcadia-esde"
DEFAULT_BRANCH = "steamdeck-main"
MARKER = ".arcadia-commit"  # records which commit a non-git copy was made from
KEEP_OUT = {".git", ".previous", "__pycache__", MARKER}


def app_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise EmulatorError(f"git couldn't be run: {exc}") from exc
    if done.returncode != 0:
        raise EmulatorError((done.stderr or done.stdout).strip() or "git failed")
    return done.stdout.strip()


def is_git_checkout(root: Path) -> bool:
    return (root / ".git").exists() and shutil.which("git") is not None


def local_commit(root: Path) -> str | None:
    if is_git_checkout(root):
        try:
            return _git(root, "rev-parse", "HEAD")
        except EmulatorError:
            return None
    try:
        return (root / MARKER).read_text().strip() or None
    except OSError:
        return None


def branch_to_follow(root: Path, configured: str = "") -> str:
    if configured.strip():
        return configured.strip()
    if is_git_checkout(root):
        try:
            name = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
            if name and name != "HEAD":
                return name
        except EmulatorError:
            pass
    return DEFAULT_BRANCH


@dataclass
class Status:
    available: bool
    branch: str
    local: str | None
    remote: str
    changes: list[str] = field(default_factory=list)  # newest first, one line each
    note: str = ""  # something to tell the user (e.g. couldn't compare)

    @property
    def short(self) -> str:
        return self.remote[:7]


def _fetcher() -> Fetcher:
    return Fetcher(hosts=GITHUB_HOSTS | {"codeload.github.com"})


def check(root: Path, branch: str = "", repo: str = REPO, fetcher: Fetcher | None = None) -> Status:
    """Is there a newer version on GitHub? Raises EmulatorError if GitHub can't be reached or the repo isn't public."""
    fetcher = fetcher or _fetcher()
    branch = branch_to_follow(root, branch)
    try:
        head = fetcher.get_json(f"{fetcher.api_base}/repos/{repo}/commits/{branch}")
    except EmulatorError as exc:
        if "wasn't found" in str(exc):
            raise EmulatorError(f"GitHub has no branch “{branch}” in {repo} (or the repository isn't public)") from exc
        raise
    remote = str(head.get("sha", ""))
    if not remote:
        raise EmulatorError("GitHub's answer didn't say which version is newest")
    local = local_commit(root)
    if local == remote:
        return Status(False, branch, local, remote)
    if local is None:
        return Status(True, branch, None, remote, [], "This copy doesn't record which version it is, so it can't be compared.")
    try:
        cmp = fetcher.get_json(f"{fetcher.api_base}/repos/{repo}/compare/{local}...{remote}")
    except EmulatorError:
        return Status(True, branch, local, remote, [], "Your version isn't on GitHub's branch (a local change?), so it can't be compared.")
    state = cmp.get("status")
    if state in ("identical", "behind"):  # you are the same or already ahead of GitHub
        return Status(False, branch, local, remote)
    commits = cmp.get("commits") or []
    lines = [str((c.get("commit") or {}).get("message", "")).split("\n")[0] for c in reversed(commits)]
    note = "Your copy and GitHub's have both changed; the update may not apply cleanly." if state == "diverged" else ""
    return Status(True, branch, local, remote, [l for l in lines if l][:30], note)


@dataclass
class Applied:
    version: str
    requirements_changed: bool


def _requirements(root: Path) -> str:
    try:
        return (root / "requirements.txt").read_text()
    except OSError:
        return ""


def apply(
    root: Path,
    status: Status,
    repo: str = REPO,
    fetcher: Fetcher | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Applied:
    before = _requirements(root)
    if is_git_checkout(root):
        if _git(root, "status", "--porcelain", "--untracked-files=no"):
            raise EmulatorError("you've changed files in Arcadia's folder, so it won't update over them (commit or undo them first)")
        if _git(root, "rev-parse", "--abbrev-ref", "HEAD") != status.branch:
            raise EmulatorError(f"this copy is on a different branch than “{status.branch}”; switch with git, or change the branch in Settings")
        _git(root, "fetch", "origin", status.branch)
        try:
            _git(root, "merge", "--ff-only", "FETCH_HEAD")
        except EmulatorError as exc:
            raise EmulatorError(f"it couldn't be fast-forwarded (your copy has its own commits): {exc}") from exc
    else:
        _replace_from_zip(root, status.remote, repo, fetcher or _fetcher(), progress)
    return Applied(status.remote[:7], _requirements(root) != before)


def _replace_from_zip(root: Path, sha: str, repo: str, fetcher: Fetcher, progress) -> None:
    with tempfile.TemporaryDirectory(prefix="arcadia-update-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / "update.zip"
        fetcher.download(f"https://codeload.github.com/{repo}/zip/{sha}", archive, progress)
        try:
            _extract_zip(archive, tmp_dir / "new")
        except zipfile.BadZipFile as exc:
            raise EmulatorError("the downloaded update wasn't a valid archive") from exc
        tops = [p for p in (tmp_dir / "new").iterdir() if p.is_dir()]
        if len(tops) != 1 or not (tops[0] / "arcadia" / "__init__.py").is_file():
            raise EmulatorError("the downloaded update didn't look like Arcadia, so nothing was changed")
        new = tops[0]
        previous = root / ".previous"
        shutil.rmtree(previous, ignore_errors=True)
        previous.mkdir()
        for item in new.iterdir():  # keep what's about to be replaced, one generation back
            if item.name in KEEP_OUT:
                continue
            old = root / item.name
            if old.exists():
                shutil.move(str(old), str(previous / item.name)) if old.is_dir() else shutil.copy2(old, previous / item.name)
        try:
            for item in new.iterdir():
                if item.name in KEEP_OUT:
                    continue
                target = root / item.name
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            (root / MARKER).write_text(sha + "\n")
        except OSError as exc:
            for item in previous.iterdir():  # put the old files back
                target = root / item.name
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.move(str(item), str(target))
            raise EmulatorError(f"the update couldn't be put in place, so the old version was restored: {exc.strerror or exc}") from exc
