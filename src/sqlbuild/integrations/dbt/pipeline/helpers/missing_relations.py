"""Missing dbt relation checks for dbt interop execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    find_sqlbuild_models_with_missing_dbt_relations,
    resolve_connection_config,
)


def find_and_report_missing_dbt_relation_blocks(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    adapter: BaseAdapter,
    adapter_name: str,
    selected_model_names: tuple[str, ...],
    dbt_unique_ids_selected_for_execution: frozenset[str],
    output_stream: TextIO,
) -> dict[str, tuple[DbtManifestModel, ...]]:
    if not selected_model_names:
        return {}
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    connection: Any = adapter.connect(connection_config)
    try:
        blocked: dict[str, tuple[DbtManifestModel, ...]] = (
            find_sqlbuild_models_with_missing_dbt_relations(
                project=project,
                manifest=manifest,
                adapter=adapter,
                connection=connection,
                selected_model_names=selected_model_names,
                dbt_unique_ids_selected_for_execution=dbt_unique_ids_selected_for_execution,
            )
        )
    finally:
        adapter.close(connection)
    if blocked:
        write_missing_dbt_relation_blocks(blocked=blocked, output_stream=output_stream)
    return blocked


def missing_dbt_relations_exit_code(blocked: dict[str, tuple[DbtManifestModel, ...]]) -> int:
    return 1 if blocked else 0


def write_missing_dbt_relation_blocks(
    *, blocked: dict[str, tuple[DbtManifestModel, ...]], output_stream: TextIO
) -> None:
    for model_name, dbt_models in sorted(blocked.items()):
        relation_names: str = ", ".join(
            dbt_model.relation_name
            for dbt_model in sorted(dbt_models, key=lambda model: model.unique_id)
        )
        output_stream.write(
            "Warning: SQLBuild model "
            f"'{model_name}' depends on missing dbt relation(s): {relation_names}. "
            f"Use --select +{model_name} to build upstream dbt models, or build them "
            "with dbt first.\n"
        )
    output_stream.flush()
