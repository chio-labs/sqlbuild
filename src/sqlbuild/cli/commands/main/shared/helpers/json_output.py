"""JSON serialization for plan and compile outputs."""

from __future__ import annotations

import json

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import (
    CascadeResult,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SeedPlanEntry,
    SourceLoadPlanEntry,
)
from sqlbuild.compiler.planner.types import PlanReason


def format_plan_json(plan: PlanOutput) -> str:
    """Serialize a PlanOutput to JSON."""

    models: list[dict[str, object]] = [_serialize_model_entry(e) for e in plan.model_entries]
    seeds: list[dict[str, object]] = [_serialize_seed_entry(e) for e in plan.seed_entries]
    functions: list[dict[str, object]] = [
        _serialize_function_entry(e) for e in plan.function_entries
    ]
    source_loads: list[dict[str, object]] = [
        _serialize_source_load_entry(e) for e in plan.source_load_entries
    ]
    warnings: list[dict[str, object]] = [_serialize_warning(w) for w in plan.warnings]

    result: dict[str, object] = {
        "selected_count": len(plan.model_entries)
        + len(plan.seed_entries)
        + len(plan.function_entries),
        "source_load_count": len(source_loads),
        "models": models,
        "seeds": seeds,
        "source_loads": source_loads,
        "functions": functions,
        "warnings": warnings,
    }
    if plan.metadata:
        result["metadata"] = plan.metadata
    return json.dumps(result, indent=2)


def format_compile_json(plan: PlanOutput) -> str:
    """Serialize compile output to JSON."""

    models: list[dict[str, object]] = []
    entry: ModelPlanEntry
    for entry in plan.model_entries:
        model: dict[str, object] = {
            "name": entry.name,
            "relative_path": str(entry.relative_path),
            "materialization_type": entry.materialization_type.value,
            "resolved_sql": entry.resolved_sql,
            "logical_ddl": entry.logical_ddl,
        }
        if entry.target.qualified_name is not None:
            model["qualified_name"] = entry.target.qualified_name
        models.append(model)

    seeds: list[dict[str, object]] = [_serialize_seed_entry(e) for e in plan.seed_entries]
    functions: list[dict[str, object]] = [
        _serialize_function_entry(e) for e in plan.function_entries
    ]

    result: dict[str, object] = {
        "model_count": len(plan.model_entries),
        "seed_count": len(plan.seed_entries),
        "function_count": len(plan.function_entries),
        "audit_count": len(plan.audit_entries),
        "test_count": len(plan.test_entries),
        "models": models,
        "seeds": seeds,
        "functions": functions,
    }
    return json.dumps(result, indent=2)


def format_static_compile_json(graph: ProjectGraph) -> str:
    """Serialize offline compile output to JSON."""

    models: list[dict[str, object]] = []
    for model in graph.project.models:
        item: dict[str, object] = {
            "name": model.name,
            "relative_path": str(model.relative_path),
            "query_sql": model.query_sql,
        }
        if model.target.qualified_name is not None:
            item["qualified_name"] = model.target.qualified_name
        models.append(item)

    seeds: list[dict[str, object]] = []
    for seed in graph.project.seeds:
        item = {"name": seed.name}
        if seed.target.qualified_name is not None:
            item["qualified_name"] = seed.target.qualified_name
        seeds.append(item)

    functions: list[dict[str, object]] = []
    for function in graph.project.functions:
        item = {
            "name": function.name,
            "relative_path": str(function.relative_path),
            "language": function.language.value,
            "return_kind": "table" if function.return_columns else "scalar",
            "returns": function.returns,
            "return_columns": [
                {"name": column.name, "type": column.type} for column in function.return_columns
            ],
        }
        if function.target.qualified_name is not None:
            item["qualified_name"] = function.target.qualified_name
        functions.append(item)

    result: dict[str, object] = {
        "command": "compile",
        "offline": True,
        "model_count": len(graph.project.models),
        "seed_count": len(graph.project.seeds),
        "function_count": len(graph.project.functions),
        "audit_count": len(graph.project.audits),
        "test_count": len(graph.project.sql_tests),
        "models": models,
        "seeds": seeds,
        "functions": functions,
    }
    return json.dumps(result, indent=2)


def _serialize_model_entry(entry: ModelPlanEntry) -> dict[str, object]:
    """Serialize one ModelPlanEntry for plan JSON output."""

    effective_reason: PlanReason = (
        PlanReason.UPSTREAM_CHANGED if entry.cascade is not None else entry.reason
    )
    model: dict[str, object] = {
        "name": entry.name,
        "relative_path": str(entry.relative_path),
        "materialization_type": entry.materialization_type.value,
        "action": entry.action.value,
        "reason": effective_reason.value,
    }

    if entry.incremental_strategy is not None:
        model["incremental_strategy"] = entry.incremental_strategy
    if entry.incremental_mode is not None:
        model["incremental_mode"] = entry.incremental_mode
    if entry.cursor_column is not None:
        model["cursor_column"] = entry.cursor_column
    if entry.cursor_type is not None:
        model["cursor_type"] = entry.cursor_type
    if entry.cursor_bounds is not None:
        model["cursor_bounds"] = {
            "start": entry.cursor_bounds.start,
            "end": entry.cursor_bounds.end,
        }

    model["backfill"] = {
        "action": entry.backfill.action.value,
        "duration": entry.backfill.duration,
    }

    if entry.cascade is not None:
        model["cascade"] = _serialize_cascade(entry.cascade)

    if entry.target.qualified_name is not None:
        model["qualified_name"] = entry.target.qualified_name

    return model


def _serialize_cascade(cascade: CascadeResult) -> dict[str, object]:
    """Serialize a CascadeResult."""

    result: dict[str, object] = {
        "effective_action": cascade.effective_action.value,
        "effective_duration": cascade.effective_duration,
        "root_cause": cascade.root_cause,
        "cause_count": len(cascade.causes),
    }
    return result


def _serialize_seed_entry(entry: SeedPlanEntry) -> dict[str, object]:
    """Serialize one SeedPlanEntry."""

    seed: dict[str, object] = {"name": entry.name}
    if entry.target.qualified_name is not None:
        seed["qualified_name"] = entry.target.qualified_name
    return seed


def _serialize_source_load_entry(entry: SourceLoadPlanEntry) -> dict[str, object]:
    source_load: dict[str, object] = {
        "name": entry.name,
        "loader": entry.loader,
        "kind": entry.resource_kind.value,
        "target": entry.target,
        "is_reload": entry.is_reload,
    }
    if entry.write_strategy is not None:
        source_load["write_strategy"] = entry.write_strategy.value
    if entry.cursor_column is not None:
        source_load["cursor_column"] = entry.cursor_column
    if entry.unique_key:
        source_load["unique_key"] = entry.unique_key
    return source_load


def _serialize_function_entry(entry: FunctionPlanEntry) -> dict[str, object]:
    """Serialize one FunctionPlanEntry."""

    function: dict[str, object] = {
        "name": entry.name,
        "relative_path": str(entry.relative_path),
        "language": entry.language.value,
        "return_kind": "table" if entry.return_columns else "scalar",
        "returns": entry.returns,
        "return_columns": [
            {"name": column.name, "type": column.type} for column in entry.return_columns
        ],
    }
    if entry.target.qualified_name is not None:
        function["qualified_name"] = entry.target.qualified_name
    return function


def _serialize_warning(warning: PlanWarning) -> dict[str, object]:
    """Serialize one PlanWarning."""

    result: dict[str, object] = {
        "severity": warning.severity.value,
        "message": warning.message,
    }
    if warning.model_name is not None:
        result["model_name"] = warning.model_name
    return result
