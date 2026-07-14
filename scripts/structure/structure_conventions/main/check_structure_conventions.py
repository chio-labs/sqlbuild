"""CLI entry for structure convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.structure.structure_conventions.filesystem import resolve_repo_root
from scripts.structure.structure_conventions.main.check_paths import check_paths
from scripts.structure.structure_conventions.models import Violation


def check_structure_conventions(argv: list[str] | None = None) -> int:
    """Run the structure convention checker CLI."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="check-structure-conventions")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("src/sqlbuild"), Path("scripts")],
    )
    args: argparse.Namespace = parser.parse_args(argv)

    violations: list[Violation] = check_paths(paths=args.paths)
    repo_root: Path = resolve_repo_root([path.resolve() for path in args.paths])

    for violation in violations:
        print(violation.format(repo_root), file=sys.stderr)

    return 1 if violations else 0
