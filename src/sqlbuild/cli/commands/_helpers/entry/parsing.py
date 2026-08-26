"""CLI argument parsing with post-parse normalization."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import (
    DEBUG_OPTION,
    EMPTY_ENV_VALUE,
    NO_COLOR_OPTION,
    SCOPE_DEFAULT_PAGE_SIZE,
    SCOPE_GLOBAL_SUMMARY,
    SQLBUILD_CONCURRENCY_ENV_VAR,
)
from sqlbuild.cli.commands.models import ParsedCliInvocation
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.scopes.types import DeclarationKind

_DBT_PASSTHROUGH_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "plan",
        "run",
        "build",
        "debug",
    }
)


def resolve_env_default_concurrency(explicit_concurrency: int | None) -> int | None:
    """Return CLI concurrency, falling back to SQLBUILD_CONCURRENCY when unset."""

    if explicit_concurrency is not None:
        return explicit_concurrency
    raw_value: str | None = os.environ.get(SQLBUILD_CONCURRENCY_ENV_VAR)
    if raw_value is None or raw_value == EMPTY_ENV_VALUE:
        return None
    try:
        concurrency: int = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{SQLBUILD_CONCURRENCY_ENV_VAR} must be an integer"
        ) from error
    if concurrency < 1:
        raise argparse.ArgumentTypeError(f"{SQLBUILD_CONCURRENCY_ENV_VAR} must be >= 1")
    return concurrency


def read_selector_files(paths: list[str]) -> tuple[str, ...]:
    """Read newline-delimited selector files."""

    selectors: list[str] = []
    for raw_path in paths:
        path: Path = Path(raw_path)
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped: str = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            selectors.append(stripped)
    return tuple(selectors)


def parse_cli_invocation(
    *,
    argv: Sequence[str] | None,
    parser: argparse.ArgumentParser,
) -> ParsedCliInvocation:
    """Parse CLI arguments into a namespace, resolving passthrough and env defaults."""

    try:
        args: CliNamespace = CliNamespace()
        unknown_args: list[str]
        _, unknown_args = parser.parse_known_args(argv, namespace=args)
        if args.command == CliCommand.DBT and args.dbt_command in _DBT_PASSTHROUGH_SUBCOMMANDS:
            dbt_passthrough_args: list[str] = []
            dbt_arg: str
            for dbt_arg in unknown_args:
                if dbt_arg == NO_COLOR_OPTION:
                    args.no_color = True
                    continue
                if dbt_arg == DEBUG_OPTION:
                    args.debug = True
                    continue
                dbt_passthrough_args.append(dbt_arg)
            args.dbt_args = dbt_passthrough_args
        elif unknown_args:
            parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
        if args.command in {CliCommand.BUILD, CliCommand.LOAD, CliCommand.SEED}:
            try:
                args.concurrency = resolve_env_default_concurrency(args.concurrency)
            except argparse.ArgumentTypeError as error:
                parser.error(str(error))
        if args.command == CliCommand.SCOPE:
            _validate_scope_args(args=args, parser=parser)
    except SystemExit as error:
        exit_code: int = error.code if isinstance(error.code, int) else 1
        return ParsedCliInvocation(args=None, exit_code=exit_code)
    return ParsedCliInvocation(args=args, exit_code=None)


def _validate_scope_args(*, args: CliNamespace, parser: argparse.ArgumentParser) -> None:
    has_target: bool = args.scope_target is not None
    has_at: bool = args.scope_at is not None
    if has_target == has_at:
        parser.error("scope requires exactly one of TARGET or --at PATH")
    if args.scope_as_path is not None and not has_target:
        parser.error("scope --as-path requires TARGET")
    folder_mode: bool = args.scope_browse is not None or args.scope_list is not None
    if folder_mode and (
        args.scope_as_path is not None
        or args.scope_explain is not None
        or args.scope_include_nearby
        or args.scope_dependency_depth != 0
    ):
        parser.error(
            "scope --browse/--list cannot be combined with --as-path, --explain, "
            "--include-nearby, or --dependency-depth"
        )
    if args.scope_browse is not None and (
        args.scope_defined_under is not None
        or args.scope_kind
        or args.scope_match is not None
        or args.scope_used_only
        or args.scope_globals != SCOPE_GLOBAL_SUMMARY
        or args.scope_page_size != SCOPE_DEFAULT_PAGE_SIZE
    ):
        parser.error(
            "scope --browse is folder-only; use --list for declaration filters and pagination"
        )
    if args.scope_page_size < 1:
        parser.error("scope --page-size must be positive")
    if args.scope_nearby_depth < 0 or args.scope_dependency_depth < 0:
        parser.error("scope depth values must be nonnegative")
    if args.scope_explain is not None:
        prefix: str = args.scope_explain.partition(":")[0]
        qualified_name: str = args.scope_explain.partition(":")[2]
        try:
            DeclarationKind(prefix)
        except ValueError:
            parser.error("scope --explain requires a declaration-qualified identity")
        if not qualified_name:
            parser.error("scope --explain requires a declaration-qualified identity")
