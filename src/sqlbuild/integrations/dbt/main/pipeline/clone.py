"""Runtime clone pipeline for `sqb dbt clone`."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneItemCallback, CloneStartCallback
from sqlbuild.integrations.dbt._helpers.pipeline.clone import (
    execute_dbt_clone,
    parse_dbt_clone_options,
)
from sqlbuild.integrations.dbt._helpers.pipeline.interop_prologue import (
    connect_dbt_interop_warehouse,
    prepare_dbt_comparison_manifests,
    resolve_selected_dbt_model_nodes,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.main.runtime._report_progress import report_progress
from sqlbuild.integrations.dbt.models import (
    DbtCloneOptions,
    DbtCloneRun,
    DbtComparisonPreparation,
    DbtInteropConnection,
    DbtLsNode,
)


def run_dbt_clone_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    on_progress: Callable[[str], None] | None = None,
    on_clone_start: CloneStartCallback | None = None,
    on_item: CloneItemCallback | None = None,
) -> DbtCloneRun:
    """Compile current and reuse manifests and clone selected dbt models."""

    options: DbtCloneOptions = parse_dbt_clone_options(args)
    preparation: DbtComparisonPreparation = prepare_dbt_comparison_manifests(
        project_dir=project_dir,
        dbt_args=options.dbt_args,
        command_label="dbt clone",
        missing_config_code="C348",
        on_progress=on_progress,
    )
    report_progress(on_progress=on_progress, message="Resolving dbt selection...")
    selected_nodes: tuple[DbtLsNode, ...] = resolve_selected_dbt_model_nodes(
        runner=preparation.runner,
        dbt_options=preparation.dbt_options,
        select=options.select,
        exclude=options.exclude,
    )
    if not selected_nodes:
        raise DbtInteropConfigError(
            "dbt clone selected no dbt models",
            code="C349",
            help="Use --select to choose at least one dbt model.",
        )
    warehouse: DbtInteropConnection = connect_dbt_interop_warehouse(
        project_dir=project_dir,
        discovered_inputs=preparation.discovered_inputs,
        on_progress=on_progress,
    )
    origin_label: str = preparation.production_git_ref
    destination_label: str = (
        preparation.dbt_options.target
        or preparation.discovered_inputs.local_config.target
        or preparation.discovered_inputs.project_config.default_target
        or "current"
    )
    try:
        report_progress(on_progress=on_progress, message="Applying clone plan...")
        clone_start: float = time.monotonic()

        def _on_start(total: int) -> None:
            if on_clone_start is not None:
                on_clone_start(
                    origin_target_name=origin_label,
                    destination_target_name=destination_label,
                    total=total,
                )

        result: CloneExecutionResult = execute_dbt_clone(
            adapter=warehouse.adapter,
            connection=warehouse.connection,
            current_manifest=preparation.current_manifest,
            reuse_manifest=preparation.reuse_manifest,
            selected_nodes=selected_nodes,
            hard_copy=options.hard_copy,
            on_start=_on_start,
            on_item=on_item,
        )
        report_progress(
            on_progress=on_progress,
            message=f"Applied clone plan. ({time.monotonic() - clone_start:.2f}s)",
        )
    finally:
        warehouse.adapter.close(warehouse.connection)
    return DbtCloneRun(
        result=result,
        origin_label=origin_label,
        destination_label=destination_label,
    )
