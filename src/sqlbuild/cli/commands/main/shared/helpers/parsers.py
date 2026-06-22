"""Shared CLI parser helpers."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands.main.shared.constants import SQLBUILD_CONCURRENCY_ENV_VAR


def parse_cli_vars(value: str) -> dict[str, object]:
    """Parse SQLBuild CLI project vars from a JSON object."""

    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"--vars must be valid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("--vars must be a JSON object")
    result: dict[str, object] = {}
    key: object
    item_value: object
    for key, item_value in parsed.items():
        if not isinstance(key, str):
            raise argparse.ArgumentTypeError("--vars keys must be strings")
        result[key] = item_value
    return result


def resolve_env_default_concurrency(explicit_concurrency: int | None) -> int | None:
    """Return CLI concurrency, falling back to SQLBUILD_CONCURRENCY when unset."""

    if explicit_concurrency is not None:
        return explicit_concurrency
    raw_value: str | None = os.environ.get(SQLBUILD_CONCURRENCY_ENV_VAR)
    if raw_value is None or raw_value == "":
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


def parse_cursor_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def parse_cursor_integer(value: str | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(value))


def add_vars_args(parser: argparse.ArgumentParser) -> None:
    """Add SQLBuild project variable override flags to a subparser."""

    parser.add_argument("--vars", dest="vars", type=parse_cli_vars, default={})


def add_cursor_override_args(parser: argparse.ArgumentParser) -> None:
    """Add typed cursor override flags to a subparser."""

    parser.add_argument("--start-cursor-ts", default=None)
    parser.add_argument("--end-cursor-ts", default=None)
    parser.add_argument("--start-cursor-int", default=None)
    parser.add_argument("--end-cursor-int", default=None)


def add_execution_args(parser: argparse.ArgumentParser) -> None:
    """Add execution control flags shared by build and run commands."""

    parser.add_argument("--fail-fast", action="store_true", default=False)
    parser.add_argument("--full-refresh", action="store_true", default=False)
    parser.add_argument("--allow-snapshot-full-refresh", action="store_true", default=False)
    parser.add_argument("--allow-snapshot-schema-change", action="store_true", default=False)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--verbose", "-v", action="store_true", default=False)


def add_execution_json_output_arg(parser: argparse.ArgumentParser) -> None:
    """Add structured execution JSON output flags."""

    parser.add_argument("--json-output", type=Path, default=None)


def add_select_args(parser: argparse.ArgumentParser) -> None:
    """Add --select and --exclude flags for scope selection."""

    parser.add_argument("--select", "-s", nargs="+", action="extend", default=[])
    parser.add_argument("--select-file", action="append", default=[])
    parser.add_argument("--exclude", nargs="+", action="extend", default=[])


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


def add_dbt_config_args(parser: argparse.ArgumentParser, *, prefix: str = "dbt") -> None:
    """Add dbt configuration flags to a subparser."""

    flag_prefix: str = f"{prefix}-" if prefix else ""
    dest_prefix: str = f"{prefix}_" if prefix else ""
    parser.add_argument(
        f"--{flag_prefix}project-dir", dest=f"{dest_prefix}project_dir", default=None
    )
    parser.add_argument(
        f"--{flag_prefix}profiles-dir", dest=f"{dest_prefix}profiles_dir", default=None
    )
    parser.add_argument(f"--{flag_prefix}target", dest=f"{dest_prefix}target", default=None)
    parser.add_argument(
        f"--{flag_prefix}target-path", dest=f"{dest_prefix}target_path", default=None
    )


def add_scenario_snapshot_safety_args(parser: argparse.ArgumentParser) -> None:
    """Add scenario snapshot capture safety flags to a subparser."""

    parser.add_argument("--force", dest="scenario_force", action="store_true", default=False)
    parser.add_argument(
        "--max-snapshot-rows",
        dest="scenario_max_snapshot_rows",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-snapshot-total-rows",
        dest="scenario_max_snapshot_total_rows",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-snapshot-bytes",
        dest="scenario_max_snapshot_bytes",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-snapshot-total-bytes",
        dest="scenario_max_snapshot_total_bytes",
        type=int,
        default=None,
    )
