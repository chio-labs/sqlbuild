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
class PartialBuildPhaseTimings:
    """Available disjoint phase durations after an exceptional build."""

    compile_seconds: float | None = None
    planning_seconds: float | None = None
    connection_preparation_seconds: float | None = None
    schema_preparation_seconds: float | None = None
    execution_seconds: float | None = None
    cost_collection_seconds: float | None = None
    total_seconds: float | None = None


@dataclass(frozen=True)
class DiagnosticRoutingOptions:
    """Policy for one invocation's diagnostic destinations."""

    debug_console: bool = False
    use_color: bool = False
    include_sql_text: bool = False
    write_legacy_file: bool = True
