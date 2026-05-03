"""CLI entry models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliContext:
    """Minimal CLI context placeholder."""

    project_dir: str | None = None
