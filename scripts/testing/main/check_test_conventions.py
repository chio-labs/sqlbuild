"""CLI entry for test convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.testing._helpers.filesystem import resolve_repo_root
from scripts.testing.main.check_paths import check_paths
from scripts.testing.models import Violation


def check_test_conventions(argv: list[str] | None = None) -> int:
    """Run the test convention checker CLI."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="check_test_conventions")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("tests")])
    args: argparse.Namespace = parser.parse_args(argv)

    violations: list[Violation] = check_paths(paths=args.paths)
    repo_root: Path = resolve_repo_root([path.resolve() for path in args.paths])

    for violation in violations:
        print(violation.format(repo_root), file=sys.stderr)

    return 1 if violations else 0
