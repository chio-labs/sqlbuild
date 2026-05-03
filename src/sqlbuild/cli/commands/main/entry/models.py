"""CLI entry models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[[Path | None, bool, str | None, bool], int]
    run_plan: Callable[[Path | None, bool, str | None, CursorOverrides | None, bool], int]
