"""Public dbt mixed-lineage entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.integrations.dbt.helpers.lineage.columns import (
    dbt_column_lineage_selected_keys,
    inspect_dbt_source_schemas,
    select_dbt_column_lineage_target,
)
from sqlbuild.integrations.dbt.helpers.lineage.output import (
    render_dbt_column_lineage,
    render_dbt_lineage_graph,
)
from sqlbuild.integrations.dbt.helpers.lineage.preparation import prepare_dbt_lineage_inputs
from sqlbuild.integrations.dbt.helpers.lineage.selection import select_dbt_lineage_target
from sqlbuild.integrations.dbt.models import (
    DbtColumnLineageTrace,
    DbtCombinedGraphKey,
    DbtLineageGraph,
    DbtLineagePreparation,
)
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress


def build_dbt_lineage_output(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    use_color: bool,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Build formatted mixed dbt/SQLBuild lineage output."""

    preparation: DbtLineagePreparation = prepare_dbt_lineage_inputs(
        project_dir=project_dir,
        args=args,
        on_progress=on_progress,
    )
    column_lineage_selected_keys: frozenset[DbtCombinedGraphKey] = dbt_column_lineage_selected_keys(
        project=preparation.project,
        manifest=preparation.manifest,
        graph=preparation.graph,
        target=preparation.lineage_args.target,
        direction=preparation.lineage_args.direction,
        depth=preparation.lineage_args.depth,
    )
    if column_lineage_selected_keys:
        report_progress(on_progress, "Inspecting dbt source and seed schemas...")
    column_trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=preparation.project,
        manifest=preparation.manifest,
        graph=preparation.graph,
        target=preparation.lineage_args.target,
        direction=preparation.lineage_args.direction,
        depth=preparation.lineage_args.depth,
        source_schemas=inspect_dbt_source_schemas(
            adapter=preparation.adapter,
            connection_config=preparation.connection_config,
            manifest=preparation.manifest,
            selected_keys=column_lineage_selected_keys,
        ),
    )
    if column_trace is not None:
        return render_dbt_column_lineage(
            column_trace,
            output_format=preparation.lineage_args.output_format,
            use_color=use_color,
        )
    lineage_graph: DbtLineageGraph = select_dbt_lineage_target(
        project=preparation.project,
        manifest=preparation.manifest,
        graph=preparation.graph,
        target=preparation.lineage_args.target,
        direction=preparation.lineage_args.direction,
        depth=preparation.lineage_args.depth,
    )
    return render_dbt_lineage_graph(
        lineage_graph,
        output_format=preparation.lineage_args.output_format,
        use_color=use_color,
    )
