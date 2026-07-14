import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

from tests.integration.src.sqlbuild.cli.commands._helpers.dbt_init._test_types import (
    DefaultBranchDetectionTestCase,
)


def build_git_repo_for_case(*, root: Path, test_case: DefaultBranchDetectionTestCase) -> Path:
    """Create a git repo on disk matching the test case branch topology."""

    strategy: Callable[..., Path] = {
        False: _preserve_non_git_directory,
        True: _build_git_repo,
    }[test_case.is_git_repo]
    return strategy(root=root, test_case=test_case)


def _preserve_non_git_directory(*, root: Path, test_case: DefaultBranchDetectionTestCase) -> Path:
    return root


def _build_git_repo(*, root: Path, test_case: DefaultBranchDetectionTestCase) -> Path:
    """Create the configured repository variant."""

    _git(root, "init", f"--initial-branch={test_case.init_branch or 'main'}")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "file.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-m", "initial")

    branch: str
    for branch in test_case.extra_branches:
        _git(root, "branch", branch)

    remote_strategy: Callable[..., None] = {
        False: _preserve_repo_without_remote_head,
        True: _set_remote_head,
    }[test_case.set_remote_head_to is not None]
    remote_strategy(root=root, remote_head=test_case.set_remote_head_to)

    return root


def _preserve_repo_without_remote_head(**_kwargs: object) -> None:
    return


def _set_remote_head(*, root: Path, remote_head: str | None) -> None:
    _git(root, "remote", "add", "origin", str(root))
    _git(
        root,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        f"refs/remotes/origin/{cast(str, remote_head)}",
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *args),
        capture_output=True,
        check=True,
        text=True,
    )
