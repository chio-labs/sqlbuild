from pathlib import Path
from textwrap import dedent

from scripts.testing.test_conventions.checker import check_paths
from scripts.testing.test_conventions.models import Violation


def base_repo_files() -> dict[str, str]:
    return {
        "pyproject.toml": "[project]\nname = 'tmp'\nversion = '0.0.0'\n",
        "tests/unit/__init__.py": '"""Unit tests."""\n',
        "tests/unit/example/__init__.py": '"""Example unit tests."""\n',
        "src/example_pkg/example_area/__init__.py": '"""Example area."""\n',
        "scripts/example_tool/__init__.py": '"""Example tool."""\n',
    }


def compliant_repo_files() -> dict[str, str]:
    return base_repo_files() | {
        "tests/unit/scripts/example_tool/_test_types.py": dedent(
            """
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class ParseNameTestCase:
                description: str
                raw_name: str
                expected_result: str
            """
        ).strip()
        + "\n",
        "tests/unit/scripts/example_tool/_test_helpers.py": dedent(
            """
            def normalize_name(raw_name: str) -> str:
                return raw_name.strip()
            """
        ).strip()
        + "\n",
        "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
            """
            import pytest

            from tests.unit.scripts.example_tool._test_types import ParseNameTestCase
            from tests.unit.scripts.example_tool._test_helpers import normalize_name


            @pytest.mark.parametrize(
                "test_case",
                [
                    ParseNameTestCase(
                        description="strips surrounding whitespace",
                        raw_name="  alice  ",
                        expected_result="alice",
                    )
                ],
                ids=lambda case: case.description,
            )
            def test_given_name_with_surrounding_whitespace_when_parsing_then_returns_trimmed_name(
                test_case: ParseNameTestCase,
            ) -> None:
                result = normalize_name(test_case.raw_name)

                assert result == test_case.expected_result
            """
        ).strip()
        + "\n",
    }


def collect_violation_codes(repo_root: Path) -> tuple[str, ...]:
    violations: list[Violation] = check_paths(paths=[repo_root / "tests"], repo_root=repo_root)
    return tuple(violation.code for violation in violations)


def collect_violation_messages(repo_root: Path) -> tuple[str, ...]:
    violations: list[Violation] = check_paths(paths=[repo_root / "tests"], repo_root=repo_root)
    return tuple(violation.message for violation in violations)
