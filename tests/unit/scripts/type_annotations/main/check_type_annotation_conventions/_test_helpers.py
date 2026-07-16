"""Helpers for type annotation checker tests."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from scripts.type_annotations.main.check_paths import check_paths
from scripts.type_annotations.models import Violation


def base_repo_files() -> dict[str, str]:
    """Return the minimal repo file set for checker tests."""

    return {
        "pyproject.toml": "[project]\nname = 'tmp'\nversion = '0.0.0'\n",
        "src/sqlbuild/__init__.py": '"""sqlbuild."""\n',
        "tests/unit/__init__.py": '"""Unit tests."""\n',
    }


def compliant_repo_files() -> dict[str, str]:
    """Return a small compliant repo slice."""

    return base_repo_files() | {
        "src/sqlbuild/example/main.py": dedent(
            """
            from sqlbuild.example.models import ExampleModel


            def load_example(raw_name: str) -> ExampleModel:
                normalized_name: str = raw_name.strip()
                return ExampleModel(name=normalized_name)
            """
        ).strip()
        + "\n",
        "src/sqlbuild/example/models.py": dedent(
            """
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class ExampleModel:
                name: str
                category: str = "demo"
            """
        ).strip()
        + "\n",
        "tests/unit/src/sqlbuild/example/_test_types.py": dedent(
            """
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class ExampleTestCase:
                description: str
                raw_name: str
                expected_name: str
            """
        ).strip()
        + "\n",
        "tests/unit/src/sqlbuild/example/test_example.py": dedent(
            """
            import pytest

            from tests.unit.src.sqlbuild.example._test_types import ExampleTestCase


            TEST_CASES: list[ExampleTestCase] = [
                ExampleTestCase(
                    description="strips whitespace",
                    raw_name="  demo  ",
                    expected_name="demo",
                )
            ]


            @pytest.mark.parametrize(
                "test_case",
                TEST_CASES,
                ids=[case.description for case in TEST_CASES],
            )
            def test_given_name_when_normalizing_then_returns_trimmed_value(
                test_case: ExampleTestCase,
            ) -> None:
                normalized_name: str = test_case.raw_name.strip()

                assert normalized_name == test_case.expected_name
            """
        ).strip()
        + "\n",
    }


def collect_violation_codes(repo_root: Path) -> tuple[str, ...]:
    """Run the type checker and collect violation codes."""

    violations: list[Violation] = check_paths(
        paths=[repo_root / "src", repo_root / "tests"], repo_root=repo_root
    )
    return tuple(violation.code for violation in violations)
