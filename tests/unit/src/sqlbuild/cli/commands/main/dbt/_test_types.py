from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtPlanProgressTestCase:
    description: str
    json_output: bool
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionWrapperTestCase:
    description: str
    command_name: str
    args: tuple[str, ...]
    expected_forwarded_args: tuple[str, ...]
    expected_progress_stream_name: str


@dataclass(frozen=True)
class DbtDebugWrapperTestCase:
    description: str
    args: tuple[str, ...]
    expected_dbt_args: tuple[str, ...]
    expected_sqlbuild_no_connection: bool
    expected_exit_code: int


@dataclass(frozen=True)
class DbtInitOutputTestCase:
    description: str
    dry_run: bool
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()
