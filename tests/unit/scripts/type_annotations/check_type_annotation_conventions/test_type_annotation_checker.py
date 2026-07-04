"""Tests for the type annotation checker."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.type_annotations.check_type_annotation_conventions import main
from tests.unit.scripts.type_annotations.check_type_annotation_conventions._test_helpers import (
    collect_violation_codes,
    compliant_repo_files,
)
from tests.unit.scripts.type_annotations.check_type_annotation_conventions._test_types import (
    CheckCliMainTestCase,
    CheckPathsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CheckPathsTestCase(
            description="reports no violations for a compliant repo slice",
            repo_files=compliant_repo_files(),
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports missing function parameter and return annotations",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/main.py": dedent(
                    """
                def load_example(raw_name):
                    normalized_name: str = raw_name.strip()
                    return normalized_name
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("TA001", "TA002"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repo_slice_when_checking_type_annotations_then_it_reports_expected_codes(
    test_case: CheckPathsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    """Type checker should report the expected violation codes."""

    write_repo_files(tmp_path, test_case.repo_files)

    assert collect_violation_codes(tmp_path) == test_case.expected_violation_codes


@pytest.mark.parametrize(
    "test_case",
    [
        CheckCliMainTestCase(
            description="returns zero when no violations are found",
            repo_files=compliant_repo_files(),
            cli_paths=("src", "tests"),
            expected_exit_code=0,
        ),
        CheckCliMainTestCase(
            description="returns one when violations are found",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/main.py": dedent(
                    """
                def load_example(raw_name):
                    value = raw_name.strip()
                    return value
                """
                ).strip()
                + "\n"
            },
            cli_paths=("src", "tests"),
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repo_slice_when_running_type_annotation_cli_then_it_returns_expected_exit_code(
    test_case: CheckCliMainTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    """Type checker CLI should return the expected exit code."""

    write_repo_files(tmp_path, test_case.repo_files)

    monkeypatch.chdir(tmp_path)
    assert main(list(test_case.cli_paths)) == test_case.expected_exit_code
