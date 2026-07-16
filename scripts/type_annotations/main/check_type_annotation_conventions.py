"""CLI entry for type annotation convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.type_annotations._helpers.filesystem import resolve_repo_root
from scripts.type_annotations.main.check_paths import check_paths
from scripts.type_annotations.models import Violation


def check_type_annotation_conventions(argv: list[str] | None = None) -> int:
    """Run the type annotation convention checker CLI."""

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
