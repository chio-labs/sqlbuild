"""Structured diagnostics result models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResourceUsage:
    """Process resource deltas for one command invocation."""

    wall_seconds: float
    user_cpu_seconds: float
    system_cpu_seconds: float
    max_rss_bytes: int | None


@dataclass(frozen=True)
class DiagnosticRoutingOptions:
    """Policy for one invocation's diagnostic destinations."""

    debug_console: bool = False
    use_color: bool = False
    include_sql_text: bool = False
    project_roots: tuple[str, ...] = ()
