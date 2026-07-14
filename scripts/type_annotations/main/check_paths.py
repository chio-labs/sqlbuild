"""Run type annotation convention checks for selected paths."""

from __future__ import annotations

from pathlib import Path

from scripts.type_annotations._helpers.filesystem import collect_python_files
from scripts.type_annotations._helpers.rules import (
    check_module,
    parse_python_module,
)
from scripts.type_annotations.models import Violation


def check_paths(*, paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Run type annotation convention checks for the provided paths."""

    target_paths: list[Path] = [path.resolve() for path in paths] if paths else _default_paths()
    violations: list[Violation] = []
    for file_path in collect_python_files(target_paths):
        module: object = parse_python_module(file_path)
        violations.extend(check_module(file_path=file_path, module=module))

    return sorted(
        violations,
        key=lambda violation: (str(violation.path), violation.line or 0, violation.code),
    )


def _default_paths() -> list[Path]:
    return [Path("src"), Path("tests")]
