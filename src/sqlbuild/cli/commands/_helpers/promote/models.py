"""Promote command request model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromoteCommandRequest:
    """CLI inputs for one `sqb promote` invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    from_virtual_environment: str
    to_virtual_environment: str
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_promotion: bool = False
    include_stale_upstreams: bool = False
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
