"""dbt defer-clone prephase progress helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlbuild.executor.clone.main.prephase_cause_annotation import (
    format_prephase_cause_annotation,
)
from sqlbuild.executor.clone.main.write_prephase_header import (
    write_prephase_header,
)
from sqlbuild.integrations.dbt.main.cli.build_command_argv import build_dbt_command_argv
from sqlbuild.integrations.dbt.main.runtime.execute_json_event_stream import (
    execute_dbt_json_event_stream,
)
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandExecutionResult,
    DbtManifestIndex,
    DbtManifestModel,
    DbtNodeExecutionResult,
)


def selected_dbt_defer_clone_cause_names(
    *,
    manifest: DbtManifestIndex,
    selected_sqlbuild_model_names: tuple[str, ...],
    selected_dbt_unique_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return selected model names used in prephase cause annotations."""

    names: set[str] = set(selected_sqlbuild_model_names)
    unique_id: str
    for unique_id in selected_dbt_unique_ids:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        names.add(model.name if model is not None else unique_id)
    return tuple(sorted(names))


def run_dbt_defer_clone_view_chain_prephase(
    *,
    dbt_options: DbtCliOptions,
    dbt_executable: str,
    view_chain_terms: tuple[str, ...],
    view_chain_unique_ids: frozenset[str],
    caused_by_names: tuple[str, ...],
    output_stream: TextIO,
    use_color: bool,
    on_progress: Callable[[str], None] | None,
) -> DbtCommandExecutionResult:
    """Refresh deferred dbt view-chain models with dbt run."""

    if not view_chain_terms:
        return DbtCommandExecutionResult(returncode=0)
    write_prephase_header(stream=output_stream, title="dbt defer clone views", use_color=use_color)
    detail: str = format_prephase_cause_annotation(caused_by_names)
    returncode: int
    results: tuple[DbtNodeExecutionResult, ...]
    argv: tuple[str, ...] = build_dbt_command_argv(
        dbt_executable=dbt_executable,
        command="run",
        options=dbt_options,
        args=("--select", *view_chain_terms),
    )
    returncode, results = execute_dbt_json_event_stream(
        argv=argv,
        cwd=dbt_options.project_dir,
        stream=output_stream,
        use_color=use_color,
        target_path=dbt_options.target_path,
        display_total=len(view_chain_terms),
        detail_by_unique_id={unique_id: detail for unique_id in view_chain_unique_ids},
        enable_status=True,
    )
    return DbtCommandExecutionResult(returncode=returncode, node_results=results)
