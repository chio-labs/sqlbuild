"""Diff command invocation resolution and validation."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.helpers.diff.models import DiffCommandRequest, DiffInvocation
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def resolve_diff_invocation(*, request: DiffCommandRequest) -> DiffInvocation:
    """Validate diff flags and discover project inputs."""

    _validate_diff_request(request=request)
    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    is_virtual_mode: bool = discovered_inputs.project_config.settings.virtual_environments
    if not request.select and not is_virtual_mode:
        raise CliUserError("diff requires --select in v1", code="C204")
    return DiffInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        is_virtual_mode=is_virtual_mode,
    )


def _validate_diff_request(*, request: DiffCommandRequest) -> None:
    selected_modes: int = (
        int(request.full) + int(request.schema_only) + int(request.bounded is not None)
    )
    if selected_modes != 1:
        raise CliUserError(
            "diff requires exactly one of --full, --schema-only, or --bounded",
            code="C201",
        )
    if request.max_column_examples is not None and request.max_column_examples <= 0:
        raise CliUserError("diff --max-column-examples must be positive", code="C202")
    if request.max_row_only_examples is not None and request.max_row_only_examples <= 0:
        raise CliUserError("diff --max-row-only-examples must be positive", code="C203")
