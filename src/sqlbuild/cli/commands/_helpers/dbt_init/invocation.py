"""Invocation resolution for the dbt init command."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.cli.commands.classes.dbt_init_progress_reporter import DbtInitProgressReporter
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    DbtInitCommandRequest,
    DbtInitInvocation,
)
from sqlbuild.integrations.dbt.main.profile.profile_init import _validate_dbt_profile_init_request
from sqlbuild.integrations.dbt.models import DbtInitProgressCallbacks, DbtInitRequest
from sqlbuild.presentation.main.supports_color import supports_color


def resolve_dbt_init_invocation(*, request: DbtInitCommandRequest) -> DbtInitInvocation:
    """Resolve paths, validation, and progress callbacks for dbt init."""

    resolved_dbt_project_dir: Path = _resolve_dbt_project_dir(request=request)
    use_color: bool = supports_color()
    progress: DbtInitProgressReporter = DbtInitProgressReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    init_request: DbtInitRequest = DbtInitRequest(
        cwd=request.cwd,
        dbt_project_dir=resolved_dbt_project_dir,
        profiles_dir=None if request.profiles_dir is None else Path(request.profiles_dir),
        profile_name=request.profile_name,
        target_name=request.target_name,
        sqb_output_dir=None if request.sqb_output_dir is None else Path(request.sqb_output_dir),
        dry_run=request.dry_run,
        overwrite=request.overwrite,
        skip_dbt_debug=request.skip_dbt_debug,
        progress_callbacks=DbtInitProgressCallbacks(
            start=progress.start,
            complete=progress.complete,
        ),
    )
    _validate_dbt_profile_init_request(request=init_request)
    return DbtInitInvocation(request=init_request, use_color=use_color)


def _resolve_dbt_project_dir(*, request: DbtInitCommandRequest) -> Path:
    resolved_dbt_project_dir: Path | None = (
        None if request.dbt_project_dir is None else Path(request.dbt_project_dir)
    )
    if resolved_dbt_project_dir is None and (request.cwd / "dbt_project.yml").exists():
        resolved_dbt_project_dir = Path(".")
    if resolved_dbt_project_dir is None:
        raise CliUserError(
            "sqb dbt init requires --project-dir pointing at a dbt project",
            code="C242",
        )
    return resolved_dbt_project_dir
