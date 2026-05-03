"""Helpers for structure checker tests."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from scripts.structure.structure_conventions.checker import main


def base_repo_files() -> dict[str, str]:
    """Return the minimal repo file set for checker tests."""

    return {
        "pyproject.toml": "[project]\nname = 'tmp'\nversion = '0.0.0'\n",
        "src/sqlbuild/__init__.py": '"""sqlbuild."""\n',
        "scripts/__init__.py": '"""Repo scripts."""\n',
    }


def compliant_repo_files() -> dict[str, str]:
    """Return a small compliant repo slice."""

    return base_repo_files() | {
        "src/sqlbuild/example/__init__.py": '"""Example domain package."""\n',
        "src/sqlbuild/example/widget/__init__.py": '"""Widget domain."""\n',
        "src/sqlbuild/example/widget/main.py": dedent(
            """
            from sqlbuild.example.widget.models import ExampleModel


            def load_example() -> ExampleModel:
                return ExampleModel(name="demo")
            """
        ).strip()
        + "\n",
        "src/sqlbuild/example/widget/models.py": dedent(
            """
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class ExampleModel:
                name: str
            """
        ).strip()
        + "\n",
        "scripts/example_tool/__init__.py": '"""Example tool."""\n',
        "scripts/example_tool/main.py": dedent(
            """
            def main() -> int:
                return 0
            """
        ).strip()
        + "\n",
    }


def write_repo_files(repo_root: Path, repo_files: dict[str, str]) -> None:
    """Write a fake repo tree to disk."""

    for relative_path, content in repo_files.items():
        file_path: Path = repo_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def collect_violation_messages(repo_root: Path) -> tuple[str, ...]:
    """Run the structure checker and collect emitted messages."""

    previous_cwd: Path = Path.cwd()
    try:
        import os

        os.chdir(repo_root)
        exit_code: int = main(["src/sqlbuild", "scripts"])
        assert exit_code in {0, 1}
    finally:
        os.chdir(previous_cwd)

    violations: list[str] = []
    previous_cwd = Path.cwd()
    try:
        import os

        os.chdir(repo_root)
        from scripts.structure.structure_conventions.checker import check_paths

        raw_violations: list[object] = check_paths(
            [repo_root / "src/sqlbuild", repo_root / "scripts"]
        )
        violations = [violation.format(repo_root) for violation in raw_violations]
    finally:
        os.chdir(previous_cwd)
    return tuple(violations)
