"""dbt init command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtInitRequest


@dataclass(frozen=True)
class DbtInitCommandRequest:
    """CLI inputs for one dbt init command invocation."""

    cwd: Path
    dbt_project_dir: str | None
    profiles_dir: str | None
    profile_name: str | None
    target_name: str | None
    sqb_output_dir: str | None
    dry_run: bool
    overwrite: bool
    skip_dbt_debug: bool
    production_git_ref: str | None = None


@dataclass(frozen=True)
class DbtInitInvocation:
    """Resolved profile-init request and output styling context."""

    request: DbtInitRequest
    use_color: bool
