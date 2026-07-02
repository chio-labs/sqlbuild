from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.helpers.dbt_init.branch_detection import (
    detect_default_production_git_ref,
)
from tests.integration.src.sqlbuild.cli.commands.helpers.dbt_init._test_types import (
    DefaultBranchDetectionTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.helpers.dbt_init.helpers import (
    build_git_repo_for_case,
)

TEST_CASES: list[DefaultBranchDetectionTestCase] = [
    DefaultBranchDetectionTestCase(
        description="non-git directory falls back to main",
        init_branch=None,
        is_git_repo=False,
        expected_ref="main",
    ),
    DefaultBranchDetectionTestCase(
        description="master-only repo detects master",
        init_branch="master",
        expected_ref="master",
    ),
    DefaultBranchDetectionTestCase(
        description="main-only repo detects main",
        init_branch="main",
        expected_ref="main",
    ),
    DefaultBranchDetectionTestCase(
        description="remote HEAD takes precedence over local common branches",
        init_branch="feature",
        extra_branches=("master",),
        set_remote_head_to="feature",
        expected_ref="feature",
    ),
    DefaultBranchDetectionTestCase(
        description="non-standard current branch with no common branch falls back to current",
        init_branch="trunk",
        expected_ref="trunk",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_git_repo_topology_when_detecting_default_ref_then_returns_expected_ref(
    test_case: DefaultBranchDetectionTestCase,
    tmp_path: Path,
) -> None:
    repo_dir: Path = build_git_repo_for_case(root=tmp_path, test_case=test_case)

    detected: str = detect_default_production_git_ref(git_probe_dir=repo_dir)

    assert detected == test_case.expected_ref
