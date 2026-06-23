import subprocess
from pathlib import Path

from tests.integration.src.sqlbuild.cli.commands.main.helpers.dbt_init._test_types import (
    DefaultBranchDetectionTestCase,
)


def build_git_repo_for_case(*, root: Path, test_case: DefaultBranchDetectionTestCase) -> Path:
    """Create a git repo on disk matching the test case branch topology."""

    if not test_case.is_git_repo:
        return root

    _git(root, "init", f"--initial-branch={test_case.init_branch or 'main'}")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "file.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-m", "initial")

    branch: str
    for branch in test_case.extra_branches:
        _git(root, "branch", branch)

    if test_case.set_remote_head_to is not None:
        _git(root, "remote", "add", "origin", str(root))
        _git(
            root,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            f"refs/remotes/origin/{test_case.set_remote_head_to}",
        )

    return root


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *args),
        capture_output=True,
        check=True,
        text=True,
    )
