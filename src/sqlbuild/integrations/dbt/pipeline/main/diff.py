"""Runtime diff pipeline for `sqb dbt diff`."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.models import (
    DbtComparisonPreparation,
    DbtDiffOptions,
    DbtDiffRun,
    DbtInteropConnection,
    DbtLsNode,
)
from sqlbuild.integrations.dbt.pipeline.helpers.diff import (
    execute_dbt_diff,
    mode_label,
    parse_dbt_diff_options,
)
from sqlbuild.integrations.dbt.pipeline.helpers.interop_prologue import (
    connect_dbt_interop_warehouse,
    prepare_dbt_comparison_manifests,
    resolve_selected_dbt_model_nodes,
)
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress


def run_dbt_diff_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    on_progress: Callable[[str], None] | None = None,
) -> DbtDiffRun:
    """Compile current and reuse manifests and diff selected dbt models."""

    options: DbtDiffOptions = parse_dbt_diff_options(args)
    preparation: DbtComparisonPreparation = prepare_dbt_comparison_manifests(
        project_dir=project_dir,
        dbt_args=options.dbt_args,
        command_label="dbt diff",
        missing_config_code="C346",
        on_progress=on_progress,
    )
    report_progress(on_progress, "Resolving dbt selection...")
    selection_start: float = time.monotonic()
    selected_nodes: tuple[DbtLsNode, ...] = resolve_selected_dbt_model_nodes(
        runner=preparation.runner,
        dbt_options=preparation.dbt_options,
        select=options.select,
        exclude=options.exclude,
    )
    report_progress(
        on_progress, f"Resolved dbt selection. ({time.monotonic() - selection_start:.2f}s)"
    )
    if not selected_nodes:
        raise DbtInteropConfigError(
            "dbt diff selected no dbt models",
            code="C347",
            help="Use --select to choose at least one dbt model.",
        )
    warehouse: DbtInteropConnection = connect_dbt_interop_warehouse(
        project_dir=project_dir,
        discovered_inputs=preparation.discovered_inputs,
        on_progress=on_progress,
    )
    try:
        report_progress(on_progress, "Comparing dbt relations...")
        diff_start: float = time.monotonic()
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=warehouse.adapter,
            connection=warehouse.connection,
            current_manifest=preparation.current_manifest,
            reuse_manifest=preparation.reuse_manifest,
            selected_nodes=selected_nodes,
            options=options,
        )
        report_progress(
            on_progress, f"Compared dbt relations. ({time.monotonic() - diff_start:.2f}s)"
        )
    finally:
        warehouse.adapter.close(warehouse.connection)
    return DbtDiffRun(
        result=result,
        from_label=preparation.production_git_ref,
        to_label="current",
        mode_label=mode_label(options),
        verbose=options.verbose,
        max_column_examples=options.max_column_examples,
        max_row_only_examples=options.max_row_only_examples,
    )
