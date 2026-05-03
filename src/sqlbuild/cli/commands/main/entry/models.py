"""CLI entry models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.planner.models import CursorOverrides


@dataclass
class CliNamespace:
    """Typed namespace for all CLI arguments across all commands."""

    command: str | None = None
    project_dir: str | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    json: bool = False
    start_cursor_ts: str | None = None
    end_cursor_ts: str | None = None
    start_cursor_int: str | None = None
    end_cursor_int: str | None = None
    no_color: bool = False
    fail_fast: bool = False
    full_refresh: bool = False
    concurrency: int | None = None
    verbose: bool = False
    select: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[[Path | None, bool, str | None, bool], int]
    run_plan: Callable[[Path | None, bool, str | None, CursorOverrides | None, bool, bool], int]
    run_build: Callable[
        [
            Path | None,
            bool,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
        ],
        int,
    ]
    run_run: Callable[
        [
            Path | None,
            bool,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
        ],
        int,
    ]
    run_test: Callable[[Path | None, bool, bool, tuple[str, ...], tuple[str, ...]], int]
    run_audit: Callable[
        [Path | None, bool, str | None, bool, tuple[str, ...], tuple[str, ...]], int
    ]
    run_seed: Callable[[Path | None, bool, tuple[str, ...], tuple[str, ...]], int]
