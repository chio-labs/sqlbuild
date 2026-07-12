"""Orchestration and CLI for type annotation convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.type_annotations.type_annotation_conventions.filesystem import (
    iter_python_files,
    resolve_repo_root,
)
from scripts.type_annotations.type_annotation_conventions.models import Violation
from scripts.type_annotations.type_annotation_conventions.rules import (
    check_module,
    parse_python_module,
)


def check_paths(*, paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Run type annotation convention checks for the provided paths."""

    target_paths: list[Path] = [path.resolve() for path in paths] if paths else _default_paths()
    violations: list[Violation] = []
    for file_path in iter_python_files(target_paths):
        module: object = parse_python_module(file_path)
        violations.extend(check_module(file_path=file_path, module=module))

    return sorted(
        violations,
        key=lambda violation: (str(violation.path), violation.line or 0, violation.code),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="check_type_annotation_conventions"
    )
    parser.add_argument("paths", nargs="*", type=Path, default=_default_paths())
    args: argparse.Namespace = parser.parse_args(argv)

    resolved_paths: list[Path] = [path.resolve() for path in args.paths]
    violations: list[Violation] = check_paths(paths=args.paths)
    repo_root: Path = resolve_repo_root(resolved_paths)

    for violation in violations:
        print(violation.format(repo_root), file=sys.stderr)

    return 1 if violations else 0


def _default_paths() -> list[Path]:
    return [Path("src"), Path("tests")]
