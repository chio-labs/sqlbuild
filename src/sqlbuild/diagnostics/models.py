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
