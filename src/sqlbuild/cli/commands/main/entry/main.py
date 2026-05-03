"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.entry.models import CliEntrypointHandlers
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.exceptions import DiscoveryError


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

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(run_compile=_run_compile_placeholder)
    return _main_with_dependencies(argv=argv, handlers=handlers)


def _main_with_dependencies(
    argv: Sequence[str] | None = None,
    *,
    handlers: CliEntrypointHandlers,
) -> int:
    """Run the CLI entrypoint with injected handlers for testing."""

    parser: argparse.ArgumentParser = _build_parser()
    try:
        args: argparse.Namespace = parser.parse_args(argv)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1

    try:
        project_dir_value: str | None = getattr(args, "project_dir", None)
        project_dir: Path | None = None if project_dir_value is None else Path(project_dir_value)
        if getattr(args, "command", None) == "compile":
            return handlers.run_compile(project_dir)
        return 0
    except CliUserError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (DiscoveryError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


def _run_compile_placeholder(project_dir: Path | None) -> int:
    del project_dir
    return 0
