"""Invocation resolution for the dbt init command."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.cli.commands.helpers.dbt_init.branch_detection import (
    detect_default_production_git_ref,
)
from sqlbuild.cli.commands.helpers.dbt_init.models import (
    DbtInitCommandRequest,
    DbtInitInvocation,
)
from sqlbuild.cli.commands.helpers.dbt_init.progress import DbtInitProgressReporter
from sqlbuild.cli.commands.helpers.dbt_init.prompt import resolve_production_git_ref
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.integrations.dbt.main.profile_init import _validate_dbt_profile_init_request
from sqlbuild.integrations.dbt.models import DbtInitProgressCallbacks, DbtInitRequest
from sqlbuild.presentation.main.supports_color import supports_color


def resolve_dbt_init_invocation(*, request: DbtInitCommandRequest) -> DbtInitInvocation:
    """Resolve paths, validation, prompting, and progress callbacks for dbt init."""

    resolved_dbt_project_dir: Path = _resolve_dbt_project_dir(request=request)
    use_color: bool = supports_color()
    progress: DbtInitProgressReporter = DbtInitProgressReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    base_request: DbtInitRequest = DbtInitRequest(
        cwd=request.cwd,
        dbt_project_dir=resolved_dbt_project_dir,
        profiles_dir=None if request.profiles_dir is None else Path(request.profiles_dir),
        profile_name=request.profile_name,
        target_name=request.target_name,
        sqb_output_dir=None if request.sqb_output_dir is None else Path(request.sqb_output_dir),
        dry_run=request.dry_run,
        overwrite=request.overwrite,
        skip_dbt_debug=request.skip_dbt_debug,
    )
    _validate_dbt_profile_init_request(request=base_request)
    resolved_production_git_ref: str = resolve_production_git_ref(
        explicit_git_ref=request.production_git_ref,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
        use_color=use_color,
        default_ref=detect_default_production_git_ref(
            git_probe_dir=request.cwd / resolved_dbt_project_dir
        ),
    )
    return DbtInitInvocation(
        request=DbtInitRequest(
            cwd=base_request.cwd,
            dbt_project_dir=base_request.dbt_project_dir,
            profiles_dir=base_request.profiles_dir,
            profile_name=base_request.profile_name,
            target_name=base_request.target_name,
            sqb_output_dir=base_request.sqb_output_dir,
            dry_run=base_request.dry_run,
            overwrite=base_request.overwrite,
            skip_dbt_debug=base_request.skip_dbt_debug,
            production_git_ref=resolved_production_git_ref,
            progress_callbacks=DbtInitProgressCallbacks(
                start=progress.start,
                complete=progress.complete,
            ),
        ),
        use_color=use_color,
    )


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
