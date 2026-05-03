"""Build a dbt-compatible manifest.json from compiled project state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
    LoadedMacro,
)
from sqlbuild.compiler.manifest.constants import DBT_MANIFEST_SCHEMA_VERSION
from sqlbuild.compiler.manifest.helpers.graph_maps import (
    build_child_map,
    build_parent_map,
)
from sqlbuild.compiler.manifest.helpers.macros import build_macro_node
from sqlbuild.compiler.manifest.helpers.model_nodes import build_model_node
from sqlbuild.compiler.manifest.helpers.seeds import build_seed_node
from sqlbuild.compiler.manifest.helpers.sources import build_source_node
from sqlbuild.compiler.manifest.helpers.tests import (
    build_audit_test_nodes,
    build_sql_test_nodes,
)
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SqlTestPlanEntry,
)


def build_manifest(
    *,
    project: CompiledProject,
    plan_output: PlanOutput,
    loaded_macros: dict[str, LoadedMacro],
    project_name: str,
    adapter_type: str,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[str, object]:
    """Build a full dbt v12-compatible manifest dictionary."""

    model_plan_map: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in plan_output.model_entries
    }

    nodes: dict[str, dict[str, object]] = {}
    sources: dict[str, dict[str, object]] = {}
    macros: dict[str, dict[str, object]] = {}

    model: CompiledModel
    for model in project.models:
        plan_entry: ModelPlanEntry | None = model_plan_map.get(model.name)
        unique_id: str = f"model.{project_name}.{model.name}"
        nodes[unique_id] = build_model_node(
            model=model,
            plan_entry=plan_entry,
            project_name=project_name,
        )

    source: CompiledSource
    for source in project.sources:
        unique_id = f"source.{project_name}.{source.name}"
        sources[unique_id] = build_source_node(
            source=source,
            project_name=project_name,
        )

    seed: CompiledSeed
    for seed in project.seeds:
        unique_id = f"seed.{project_name}.{seed.name}"
        nodes[unique_id] = build_seed_node(
            seed=seed,
            project_name=project_name,
        )

    audit_entry: AuditPlanEntry
    for audit_entry in plan_output.audit_entries:
        audit_nodes: dict[str, dict[str, object]] = build_audit_test_nodes(
            audit_entry=audit_entry,
            project_name=project_name,
        )
        nodes.update(audit_nodes)

    test_entry: SqlTestPlanEntry
    for test_entry in plan_output.test_entries:
        test_nodes: dict[str, dict[str, object]] = build_sql_test_nodes(
            test_entry=test_entry,
            project_name=project_name,
        )
        nodes.update(test_nodes)

    macro_name: str
    loaded_macro: LoadedMacro
    for macro_name, loaded_macro in loaded_macros.items():
        unique_id = f"macro.{project_name}.{macro_name}"
        macros[unique_id] = build_macro_node(
            loaded_macro=loaded_macro,
            project_name=project_name,
        )

    parent_map: dict[str, list[str]] = build_parent_map(
        upstream_deps=upstream_deps,
        project_name=project_name,
        project=project,
    )
    child_map: dict[str, list[str]] = build_child_map(
        downstream_deps=downstream_deps,
        project_name=project_name,
        project=project,
    )

    return {
        "metadata": _build_metadata(
            project_name=project_name,
            adapter_type=adapter_type,
            run_id=project.run_id,
        ),
        "nodes": nodes,
        "sources": sources,
        "macros": macros,
        "exposures": {},
        "metrics": {},
        "groups": {},
        "selectors": {},
        "disabled": {},
        "parent_map": parent_map,
        "child_map": child_map,
        "group_map": {},
        "docs": {},
        "saved_queries": {},
        "semantic_models": {},
        "unit_tests": {},
    }


def _build_metadata(
    *,
    project_name: str,
    adapter_type: str,
    run_id: str,
) -> dict[str, object]:
    """Build the top-level manifest metadata block."""

    return {
        "dbt_schema_version": DBT_MANIFEST_SCHEMA_VERSION,
        "dbt_version": "1.12.0",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "invocation_id": run_id,
        "env": {},
        "project_name": project_name,
        "project_id": None,
        "user_id": None,
        "send_anonymous_usage_stats": False,
        "adapter_type": adapter_type,
    }
