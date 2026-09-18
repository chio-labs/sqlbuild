"""Diff command invocation resolution and validation."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import DiffCommandRequest, DiffInvocation
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
    if not request.select and not is_virtual_mode and not is_query_diff_request(request=request):
        raise CliUserError("diff requires --select in v1", code="C204")
    return DiffInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        is_virtual_mode=is_virtual_mode,
    )


def _validate_diff_request(*, request: DiffCommandRequest) -> None:
    query_mode: bool = is_query_diff_request(request=request)
    selected_modes: int = (
        int(request.full) + int(request.schema_only) + int(request.bounded is not None)
    )
    if selected_modes != 1 and not (query_mode and selected_modes == 0):
        raise CliUserError(
            "diff requires exactly one of --full, --schema-only, or --bounded",
            code="C201",
        )
    if request.max_column_examples is not None and request.max_column_examples <= 0:
        raise CliUserError("diff --max-column-examples must be positive", code="C202")
    if request.max_row_only_examples is not None and request.max_row_only_examples <= 0:
        raise CliUserError("diff --max-row-only-examples must be positive", code="C203")
    if request.sample_rows is not None and request.sample_rows <= 0:
        raise CliUserError("diff --sample-rows must be positive", code="C208")
    if request.exhaustive and request.sample_rows is not None:
        raise CliUserError("diff --exhaustive cannot be combined with --sample-rows", code="C209")
    if request.max_models is not None and request.max_models <= 0:
        raise CliUserError("diff --max-models must be positive", code="C210")
    if request.max_columns is not None and request.max_columns <= 0:
        raise CliUserError("diff --max-columns must be positive", code="C211")
    if request.unkeyed and request.unique_key_override:
        raise CliUserError("diff --unkeyed cannot be combined with --key", code="C226")
    if request.unkeyed and (request.sample_rows is not None or request.sample_seed is not None):
        raise CliUserError("unkeyed diff does not support sampling", code="C222")
    if request.unkeyed and request.tolerance_overrides:
        raise CliUserError("unkeyed diff does not support tolerances", code="C223")
    if any(not key.strip() for key in request.unique_key_override):
        raise CliUserError("diff --key values must not be empty", code="C241")
    normalized_keys: tuple[str, ...] = tuple(key.lower() for key in request.unique_key_override)
    if len(set(normalized_keys)) != len(normalized_keys):
        raise CliUserError("diff --key values must be unique", code="C242")
    if query_mode:
        _validate_query_diff_request(request=request)
    else:
        _validate_model_diff_request(request=request)


def is_query_diff_request(*, request: DiffCommandRequest) -> bool:
    """Return whether any raw-query input was supplied."""

    return any(
        value is not None
        for value in (
            request.left_query,
            request.left_query_file,
            request.right_query,
            request.right_query_file,
        )
    )


def _validate_query_diff_request(*, request: DiffCommandRequest) -> None:
    if request.from_name is not None or request.to_name is not None:
        raise CliUserError("raw-query diff does not accept FROM:TO", code="C212")
    if request.select or request.exclude:
        raise CliUserError("raw-query diff does not accept model selectors", code="C213")
    if request.bounded is not None:
        raise CliUserError(
            "raw-query diff does not support --bounded; filter both raw queries explicitly",
            code="C214",
        )
    if request.allow_partial_diff:
        raise CliUserError("raw-query diff does not use --allow-partial-diff", code="C215")
    if request.max_models is not None:
        raise CliUserError("raw-query diff does not accept --max-models", code="C243")
    if request.left_query is None and request.left_query_file is None:
        raise CliUserError("raw-query diff requires a left query", code="C216")
    if request.left_query is not None and request.left_query_file is not None:
        raise CliUserError(
            "raw-query diff accepts either --left-query or --left-query-file, not both",
            code="C217",
        )
    if request.right_query is None and request.right_query_file is None:
        raise CliUserError("raw-query diff requires a right query", code="C218")
    if request.right_query is not None and request.right_query_file is not None:
        raise CliUserError(
            "raw-query diff accepts either --right-query or --right-query-file, not both",
            code="C219",
        )
    if request.schema_only:
        if request.unkeyed or request.unique_key_override:
            raise CliUserError(
                "schema-only raw-query diff does not accept --key or --unkeyed",
                code="C220",
            )
        return
    if bool(request.unique_key_override) == request.unkeyed:
        raise CliUserError(
            "raw-query diff requires one or more --key values or explicit --unkeyed",
            code="C221",
        )


def _validate_model_diff_request(*, request: DiffCommandRequest) -> None:
    if request.from_name is None or request.to_name is None:
        raise CliUserError("model diff requires FROM:TO", code="C224")
    if request.selected_target is not None:
        raise CliUserError("model diff does not accept --target", code="C225")
