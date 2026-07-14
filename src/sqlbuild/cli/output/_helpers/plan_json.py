"""JSON presentation for plans."""

from __future__ import annotations

import difflib
import json
from typing import cast

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import (
    CascadeResult,
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    PlanProviderUsage,
    PlanWarning,
    RunDespiteUnchangedDecision,
    SeedPlanEntry,
    SourceLoadPlanEntry,
)
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.compiler.python_nodes.types import PythonIdentityStatus


def format_plan_json(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> str:
    """Serialize a PlanOutput to JSON."""

    models: list[dict[str, object]] = [_serialize_model_entry(e) for e in plan.model_entries]
    dependency_baseline_models: list[dict[str, object]] = [
        _serialize_dependency_baseline_entry(e) for e in plan.dependency_baseline_entries
    ]
    seeds: list[dict[str, object]] = [_serialize_seed_entry(e) for e in plan.seed_entries]
    functions: list[dict[str, object]] = [
        _serialize_function_entry(e) for e in plan.function_entries
    ]
    source_loads: list[dict[str, object]] = [
        _serialize_source_load_entry(e) for e in plan.source_load_entries
    ]
    warnings: list[dict[str, object]] = [_serialize_warning(w) for w in plan.warnings]
    python_nodes: list[dict[str, object]] = [
        _serialize_python_plan_entry(entry) for entry in python_plan_entries
    ]
    providers: list[dict[str, object]] = _serialize_provider_usages(
        plan=plan,
        python_plan_entries=python_plan_entries,
    )

    result: dict[str, object] = {
        "selected_count": len(plan.model_entries)
        + len(plan.seed_entries)
        + len(plan.function_entries),
        "source_load_count": len(source_loads),
        "python_node_count": len(python_nodes),
        "models": models,
        "dependency_baseline_models": dependency_baseline_models,
        "existing_destination_inputs": [
            _serialize_existing_destination_input_entry(e)
            for e in plan.existing_destination_input_entries
        ],
        "reuse": _serialize_reuse_summary(plan),
        "seeds": seeds,
        "source_loads": source_loads,
        "functions": functions,
        "python_nodes": python_nodes,
        "providers": providers,
        "warnings": warnings,
    }
    if plan.metadata:
        result["metadata"] = plan.metadata
    return json.dumps(result, indent=2)


def _serialize_dependency_baseline_entry(
    entry: DependencyBaselinePlanEntry,
) -> dict[str, object]:
    result: dict[str, object] = {
        "name": entry.name,
        "resource_label": entry.resource_label,
        "destination": entry.destination.qualified_name,
        "reuse_from_target": entry.relation_reuse.reuse_from_target_name,
        "origin_relation": entry.relation_reuse.origin.qualified_name,
        "hard_copy": entry.relation_reuse.hard_copy,
    }
    if entry.fingerprint_version_hash is not None:
        result["fingerprint_version_hash"] = entry.fingerprint_version_hash
    return result


def _serialize_existing_destination_input_entry(
    entry: ExistingDestinationInputPlanEntry,
) -> dict[str, object]:
    return {
        "name": entry.name,
        "destination": entry.destination.qualified_name,
        "status": entry.status,
        "expected_version_hash": entry.expected_version_hash,
        "destination_version_hash": entry.destination_version_hash,
    }


def _serialize_reuse_summary(plan: PlanOutput) -> dict[str, object]:
    return {
        "cloned_selected": [
            _serialize_model_entry(entry)
            for entry in plan.model_entries
            if entry.relation_reuse is not None
        ],
        "reused_inputs": [
            _serialize_dependency_baseline_entry(entry)
            for entry in plan.dependency_baseline_entries
        ],
        "existing_destination_inputs": [
            _serialize_existing_destination_input_entry(entry)
            for entry in plan.existing_destination_input_entries
        ],
    }


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
        "expected_version_hash": entry.fingerprint_version_hash,
        "built_version_hash": entry.previous_version_hash,
        "built_version_present": entry.previous_version_hash is not None,
        "identity_status": _model_identity_status(entry),
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

    if entry.destination.qualified_name is not None:
        model["qualified_name"] = entry.destination.qualified_name
    if entry.relation_reuse is not None:
        model["relation_reuse"] = {
            "kind": entry.relation_reuse.kind.value,
            "reuse_from_target": entry.relation_reuse.reuse_from_target_name,
            "origin_relation": entry.relation_reuse.origin.qualified_name,
            "hard_copy": entry.relation_reuse.hard_copy,
        }
    if entry.run_despite_unchanged is not None:
        decision: RunDespiteUnchangedDecision = entry.run_despite_unchanged
        model["run_despite_unchanged"] = {
            "mode": decision.mode.value,
            "duration": decision.duration,
            "newest_source_name": decision.newest_source_name,
            "newest_source_data_age_seconds": decision.newest_source_data_age_seconds,
        }

    return model


def _model_identity_status(entry: ModelPlanEntry) -> str:
    """Return a stable JSON status for expected-vs-built model identity."""

    if entry.fingerprint_version_hash is None:
        return "unknown"
    if entry.previous_version_hash is None:
        return "missing"
    if entry.previous_version_hash == entry.fingerprint_version_hash:
        return "current"
    return "stale"


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

    seed: dict[str, object] = {"name": entry.name, "reason": entry.reason.value}
    if entry.destination.qualified_name is not None:
        seed["qualified_name"] = entry.destination.qualified_name
    return seed


def _serialize_source_load_entry(entry: SourceLoadPlanEntry) -> dict[str, object]:
    source_load: dict[str, object] = {
        "name": entry.name,
        "loader": entry.loader,
        "kind": entry.resource_kind.value,
        "target": entry.destination,
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
    if entry.destination.qualified_name is not None:
        function["qualified_name"] = entry.destination.qualified_name
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


def _serialize_python_plan_entry(entry: PythonPlanEntry) -> dict[str, object]:
    result: dict[str, object] = {
        "name": entry.name,
        "kind": entry.kind.value,
        "phase": entry.phase.value,
        "identity_status": entry.identity_status.value,
    }
    identity_diff: dict[str, object] = _serialize_python_identity_diff(entry)
    if identity_diff:
        result["identity_diff"] = identity_diff
    return result


def _serialize_python_identity_diff(entry: PythonPlanEntry) -> dict[str, object]:
    if entry.identity_status != PythonIdentityStatus.CHANGED:
        return {}
    result: dict[str, object] = {}
    source_diff: list[str] = _python_source_diff(entry)
    if source_diff:
        result["source_diff"] = source_diff
    dependency_diff: list[str] = _python_dependency_diff(entry)
    if dependency_diff:
        result["dependency_diff"] = dependency_diff
    return result


def _python_source_diff(entry: PythonPlanEntry) -> list[str]:
    previous: str | None = _python_definition_source_text(entry.previous_definition_json)
    current: str | None = _python_definition_source_text(entry.current_definition_json)
    if previous is None or current is None or previous == current:
        return []
    return _unified_diff(previous=previous, current=current)


def _python_dependency_diff(entry: PythonPlanEntry) -> list[str]:
    previous: str | None = _python_dependency_source_text(entry.previous_metadata_json)
    current: str | None = _python_dependency_source_text(entry.current_metadata_json)
    if previous is None or current is None or previous == current:
        return []
    return _unified_diff(previous=previous, current=current)


def _python_definition_source_text(raw_json: str | None) -> str | None:
    payload: dict[str, object] | None = _json_object(raw_json)
    if payload is None:
        return None
    source_text: object = payload.get("source_text")
    return source_text if isinstance(source_text, str) else None


def _python_dependency_source_text(raw_json: str | None) -> str | None:
    payload: dict[str, object] | None = _json_object(raw_json)
    if payload is None:
        return None
    raw_dependencies: object = payload.get("dependencies")
    if not isinstance(raw_dependencies, list):
        return None
    blocks: list[str] = []
    dependency: object
    for dependency in sorted(raw_dependencies, key=_python_dependency_sort_key):
        if not isinstance(dependency, dict):
            continue
        dependency_payload: dict[object, object] = cast(dict[object, object], dependency)
        source_text: object = dependency_payload.get("source_text")
        if not isinstance(source_text, str):
            continue
        source_path: object = dependency_payload.get("source_path")
        module: object = dependency_payload.get("module")
        qualname: object = dependency_payload.get("qualname")
        header_parts: list[str] = []
        if isinstance(source_path, str) and source_path:
            header_parts.append(source_path)
        if isinstance(module, str) and module:
            header_parts.append(module)
        if isinstance(qualname, str) and qualname:
            header_parts.append(qualname)
        header: str = " :: ".join(header_parts) if header_parts else "dependency"
        blocks.append(f"# {header}\n{source_text}")
    return "\n\n".join(blocks)


def _python_dependency_sort_key(dependency: object) -> tuple[str, str, str]:
    if not isinstance(dependency, dict):
        return ("", "", "")
    dependency_payload: dict[object, object] = cast(dict[object, object], dependency)
    source_path: object = dependency_payload.get("source_path")
    module: object = dependency_payload.get("module")
    qualname: object = dependency_payload.get("qualname")
    return (
        source_path if isinstance(source_path, str) else "",
        module if isinstance(module, str) else "",
        qualname if isinstance(qualname, str) else "",
    )


def _json_object(raw_json: str | None) -> dict[str, object] | None:
    if raw_json is None:
        return None
    try:
        payload: object = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _unified_diff(*, previous: str, current: str) -> list[str]:
    return [
        line.rstrip("\n")
        for line in difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
        )
    ]


def _serialize_provider_usages(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...]
) -> list[dict[str, object]]:
    usage_by_provider: dict[str, list[PlanProviderUsage]] = {}
    usage: PlanProviderUsage
    for usage in plan.provider_usages:
        usage_by_provider.setdefault(usage.provider_name, []).append(usage)
    python_entry: PythonPlanEntry
    for python_entry in python_plan_entries:
        for provider_usage in python_entry.provider_usages:
            usage_by_provider.setdefault(provider_usage.provider_name, []).append(
                PlanProviderUsage(
                    provider_name=provider_usage.provider_name,
                    consumer_kind=python_entry.kind.value,
                    consumer_name=python_entry.name,
                    parameter_name=provider_usage.parameter_name,
                    annotation_class_name=provider_usage.annotation_class_name,
                    annotation_module=provider_usage.annotation_module,
                )
            )
    providers: list[dict[str, object]] = []
    for provider_name, usages in sorted(usage_by_provider.items()):
        serialized_usages: list[dict[str, object]] = []
        for usage in sorted(
            usages,
            key=lambda item: (item.consumer_kind, item.consumer_name, item.parameter_name),
        ):
            serialized_usages.append(_serialize_provider_usage(usage))
        providers.append({"name": provider_name, "used_by": serialized_usages})
    return providers


def _serialize_provider_usage(usage: PlanProviderUsage) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": usage.consumer_kind,
        "name": usage.consumer_name,
        "parameter": usage.parameter_name,
    }
    if usage.annotation_class_name is not None or usage.annotation_module is not None:
        payload["annotation"] = {
            "class_name": usage.annotation_class_name,
            "module": usage.annotation_module,
        }
    return payload
