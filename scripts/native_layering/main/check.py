"""Native crate layering command entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.native_layering._helpers.layering import get_native_layering_errors
from scripts.native_layering._helpers.versions import get_native_version_errors


def run_native_layering_check(argv: list[str] | None = None) -> int:
    """Fail when a native crate breaks the declared layering or the release versions differ."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments: argparse.Namespace = parser.parse_args(argv)
    errors: tuple[str, ...] = get_native_layering_errors(
        arguments.root
    ) + get_native_version_errors(arguments.root)
    if errors:
        print("Native crate layering is invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Native crate layering is valid.")
    return 0
