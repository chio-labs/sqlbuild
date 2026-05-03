"""CLI entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb")
    parser.add_argument("--project-dir", default=None)

    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command"
    )
    subparsers.add_parser("compile")
    subparsers.add_parser("run")
    subparsers.add_parser("build")
    subparsers.add_parser("test")
    subparsers.add_parser("audit")
    subparsers.add_parser("seed")
    subparsers.add_parser("clone")
    subparsers.add_parser("diff")
    subparsers.add_parser("clean")
    subparsers.add_parser("janitor")
    subparsers.add_parser("init")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    parser: argparse.ArgumentParser = _build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1
    return 0
