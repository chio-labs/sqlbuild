"""Declarative argparse front end for `sqb dbt` execution commands."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import NoReturn

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.models import DbtInteropParsedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def add_dbt_execution_args(parser: argparse.ArgumentParser) -> None:
    """Declare category-1 `sqb dbt` flags plus the `--` passthrough positional."""

    parser.add_argument("--select", "-s", nargs="+", action="extend", default=[])
    parser.add_argument("--exclude", nargs="+", action="extend", default=[])
    parser.add_argument("--vars", default=None)
    parser.add_argument("--threads", default=None)
    parser.add_argument("--full-refresh", action="store_true", default=False)
    parser.add_argument("--event-time-start", default=None)
    parser.add_argument("--event-time-end", default=None)
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--profiles-dir", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--target-path", default=None)
    parser.add_argument("--state", default=None)
    parser.add_argument("--indirect-selection", default=None)
    parser.add_argument("--defer", action="store_true", default=False)
    parser.add_argument("--defer-to", default=None)
    parser.add_argument("--start-cursor-ts", default=None)
    parser.add_argument("--end-cursor-ts", default=None)
    parser.add_argument("--start-cursor-int", default=None)
    parser.add_argument("--end-cursor-int", default=None)
    parser.add_argument("--fail-fast", action="store_true", default=False)
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument("--hard-copy", action="store_true", default=False)
    parser.add_argument(
        "dbt_passthrough",
        nargs="*",
        metavar="-- DBT_ARGS",
        help="raw dbt flags after `--`, forwarded verbatim",
    )


def build_dbt_execution_parser(
    command: DbtInteropCommand, *, prog: str | None = None
) -> argparse.ArgumentParser:
    """Build the standalone argparse parser declaring flags for a dbt command."""

    parser: argparse.ArgumentParser = _StrictArgumentParser(
        prog=prog or f"sqb dbt {command.value}",
        add_help=True,
        description=f"Run `dbt {command.value}` through SQLBuild change detection.",
        epilog="Pass raw dbt operational flags after `--`, e.g. `-- --log-level debug`.",
    )
    add_dbt_execution_args(parser)
    return parser


def parse_dbt_execution_args(
    *, command: DbtInteropCommand, args: Sequence[str]
) -> DbtInteropParsedArgs:
    """Parse raw `sqb dbt <command>` tokens into declared flags and a `--` tail."""

    head, tail = _split_passthrough(args)
    parser: argparse.ArgumentParser = build_dbt_execution_parser(command)
    namespace: argparse.Namespace
    unknown: list[str]
    namespace, unknown = parser.parse_known_args(head)
    if unknown:
        raise DbtInteropArgumentError(
            f"unrecognized option(s) for sqb dbt {command.value}: {' '.join(unknown)}",
            code="C238",
            help="SQLBuild flags go before `--`; pass raw dbt flags after `--`.",
        )
    leading: tuple[str, ...] = tuple(namespace.dbt_passthrough or ())
    return DbtInteropParsedArgs(
        select=tuple(namespace.select),
        exclude=tuple(namespace.exclude),
        vars=namespace.vars,
        threads=namespace.threads,
        full_refresh=namespace.full_refresh,
        event_time_start=namespace.event_time_start,
        event_time_end=namespace.event_time_end,
        project_dir=namespace.project_dir,
        profiles_dir=namespace.profiles_dir,
        profile=namespace.profile,
        target=namespace.target,
        target_path=namespace.target_path,
        state=namespace.state,
        indirect_selection=namespace.indirect_selection,
        defer=namespace.defer,
        defer_to=namespace.defer_to,
        start_cursor_ts=namespace.start_cursor_ts,
        end_cursor_ts=namespace.end_cursor_ts,
        start_cursor_int=namespace.start_cursor_int,
        end_cursor_int=namespace.end_cursor_int,
        fail_fast=namespace.fail_fast,
        force=namespace.force,
        hard_copy=namespace.hard_copy,
        dbt_passthrough=(*leading, *tail),
    )


def _split_passthrough(args: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tokens: list[str] = list(args)
    if "--" not in tokens:
        return tuple(tokens), ()
    separator: int = tokens.index("--")
    return tuple(tokens[:separator]), tuple(tokens[separator + 1 :])


class _StrictArgumentParser(argparse.ArgumentParser):
    """argparse parser that raises DbtInteropArgumentError instead of sys.exit."""

    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        raise DbtInteropArgumentError(
            f"{self.prog}: {message}",
            code="C238",
            help="Run `-h` to list supported flags; pass raw dbt flags after `--`.",
        )
