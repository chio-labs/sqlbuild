"""CLI argument parsing with post-parse normalization."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from sqlbuild.cli.commands.helpers.entry.models import CliNamespace, ParsedCliInvocation
from sqlbuild.cli.commands.shared.helpers.config.parsers import resolve_env_default_concurrency
from sqlbuild.cli.commands.shared.types import CliCommand

_DBT_PASSTHROUGH_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "plan",
        "run",
        "build",
        "test",
        "scenario",
        "debug",
        "lineage",
        "diff",
        "clone",
    }
)


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
                if dbt_arg == "--no-color":
                    args.no_color = True
                    continue
                if dbt_arg == "--debug":
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
    except SystemExit as error:
        exit_code: int = error.code if isinstance(error.code, int) else 1
        return ParsedCliInvocation(args=None, exit_code=exit_code)
    return ParsedCliInvocation(args=args, exit_code=None)
