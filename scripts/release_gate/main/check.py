"""Release gate command entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.release_gate._helpers.gate import get_release_gate_errors
from scripts.release_gate.exceptions import ReleaseGateError


def run_release_gate_check(argv: list[str] | None = None) -> int:
    """Fail when anything but the trusted release checks can pass a release pull request."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments: argparse.Namespace = parser.parse_args(argv)
    try:
        errors: tuple[str, ...] = get_release_gate_errors(arguments.root)
    except ReleaseGateError as error:
        errors = (str(error),)
    if errors:
        print("Release pull request Verify gate is invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Release pull request Verify gate is valid.")
    return 0
