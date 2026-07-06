"""Rollback command request model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RollbackCommandRequest:
    """CLI inputs for one `sqb rollback` invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    virtual_environment: str | None
    verbose: bool = False
    checkpoint_id: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_rollback: bool = False
    include_stale_upstreams: bool = False
    cli_vars: dict[str, object] | None = None
