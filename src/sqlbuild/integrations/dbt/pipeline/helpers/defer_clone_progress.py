"""dbt defer-clone prephase progress helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.integrations.dbt.helpers.cli.runner import build_dbt_command_argv
from sqlbuild.integrations.dbt.helpers.runtime.event_stream import execute_dbt_json_event_stream
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandExecutionResult,
    DbtNodeExecutionResult,
)
from sqlbuild.shared.helpers.prephase_progress import (
    format_prephase_cause_annotation,
    write_prephase_header,
    write_prephase_rows,
)
from sqlbuild.shared.models import PrephaseProgressRow


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


def write_dbt_defer_clone_prephase_rows(
    *,
    stream: TextIO,
    result: CloneExecutionResult | None,
    caused_by_names: tuple[str, ...],
    use_color: bool,
) -> None:
    """Write dbt defer-clone clone/copy rows with shared prephase formatting."""

    if result is None or not result.item_results:
        return
    write_prephase_header(stream=stream, title="dbt defer clone", use_color=use_color)
    write_prephase_rows(
        stream=stream,
        rows=tuple(
            PrephaseProgressRow(
                label=_clone_item_label(item),
                name=item.name,
                status=_clone_item_status(item),
                duration_seconds=item.duration_seconds,
                caused_by_names=caused_by_names,
            )
            for item in result.item_results
        ),
        use_color=use_color,
    )


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
    if on_progress is not None:
        on_progress("Refreshing deferred dbt view chain...")
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
    )
    if on_progress is not None:
        on_progress("Refreshed deferred dbt view chain.")
    return DbtCommandExecutionResult(returncode=returncode, node_results=results)


def _clone_item_label(item: CloneItemResult) -> str:
    if item.action == CloneAction.RECREATED_VIEW:
        return "view"
    if item.action == CloneAction.COPIED:
        return "copy"
    return "clone"


def _clone_item_status(item: CloneItemResult) -> str:
    if item.status == CloneStatus.SUCCESS:
        return "OK"
    if item.status == CloneStatus.WARNING:
        return "WARN"
    return "FAIL"
