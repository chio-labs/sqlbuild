"""Pure virtual planning helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.virtual.state.models import ModelVersionRecord, VirtualEnvironmentRefRecord


def build_expected_local_hashes(
    *,
    graph: ProjectGraph,
) -> dict[str, str]:
    """Derive local-only semantic hashes for functions and models."""

    function_local_hashes: dict[str, str] = build_function_local_hashes(graph=graph)
    expected_local_hashes: dict[str, str] = dict(function_local_hashes)
    model_metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(
        graph=graph,
        function_local_hashes=function_local_hashes,
    )
    models_by_name: dict[str, Any] = {model.name: model for model in graph.project.models}
    key: Any
    for key in _topologically_order_keys(graph):
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: Any | None = models_by_name.get(key.name)
        if model is None:
            continue
        expected_local_hashes[model.name] = _stable_hash(
            "\n".join(
                (
                    model.query_sql,
                    model_metadata_jsons[model.name],
                )
            )
        )
    return expected_local_hashes


def build_function_local_hashes(*, graph: ProjectGraph) -> dict[str, str]:
    """Derive local-only semantic hashes for functions."""

    return {
        function.name: _stable_hash(
            json.dumps(
                {
                    "arguments": [
                        (argument.name, argument.type) for argument in function.arguments
                    ],
                    "returns": function.returns,
                    "body_sql": function.body_sql,
                    "language": function.language.value,
                },
                sort_keys=True,
                default=str,
            )
        )
        for function in graph.project.functions
    }


def build_model_fingerprint_metadata_jsons(
    *,
    graph: ProjectGraph,
    function_local_hashes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build deterministic non-query model fingerprint metadata JSON by model."""

    function_hashes: dict[str, str] = function_local_hashes or build_function_local_hashes(
        graph=graph
    )
    result: dict[str, str] = {}
    models_by_name: dict[str, Any] = {model.name: model for model in graph.project.models}
    key: Any
    for key in _topologically_order_keys(graph):
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: Any | None = models_by_name.get(key.name)
        if model is None:
            continue
        local_function_hashes: list[str] = []
        upstream_key: Any
        for upstream_key in model.deps:
            if upstream_key.resource_type != CompiledResourceType.FUNCTION:
                continue
            upstream_hash: str | None = function_hashes.get(upstream_key.name)
            if upstream_hash is not None:
                local_function_hashes.append(upstream_hash)
        result[model.name] = json.dumps(
            {
                "config": model.config.values,
                "local_function_hashes": local_function_hashes,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    return result


def build_expected_version_hashes(
    *,
    graph: ProjectGraph,
    expected_local_hashes: dict[str, str],
) -> dict[str, str]:
    """Derive expected model version hashes from current code and upstream hashes."""

    expected_hashes: dict[str, str] = {
        function.name: expected_local_hashes[function.name] for function in graph.project.functions
    }
    models_by_name: dict[str, Any] = {model.name: model for model in graph.project.models}

    key: Any
    for key in _topologically_order_keys(graph):
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: Any | None = models_by_name.get(key.name)
        if model is None:
            continue
        upstream_hashes: list[str] = []
        upstream_key: Any
        for upstream_key in model.deps:
            if upstream_key.resource_type not in (
                CompiledResourceType.MODEL,
                CompiledResourceType.FUNCTION,
            ):
                continue
            upstream_hash: str | None = expected_hashes.get(upstream_key.name)
            if upstream_hash is not None:
                upstream_hashes.append(upstream_hash)
        expected_hashes[model.name] = _stable_hash(
            "\n".join(
                (
                    expected_local_hashes[model.name],
                    *upstream_hashes,
                )
            )
        )
    return expected_hashes


def build_bound_version_hashes(
    refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> dict[str, str]:
    """Index bound version hashes by model name from VDE refs."""

    return {ref.model_name: ref.version_hash for ref in refs}


def build_stale_model_names(
    *,
    model_names: tuple[str, ...],
    expected_version_hashes: dict[str, str],
    bound_version_hashes: dict[str, str],
) -> tuple[str, ...]:
    """Return model names whose bound and expected hashes differ."""

    return tuple(
        model_name
        for model_name in model_names
        if bound_version_hashes.get(model_name) != expected_version_hashes.get(model_name)
    )


def build_bound_local_hashes(
    model_versions: dict[str, ModelVersionRecord | None],
) -> dict[str, str]:
    """Index bound local semantic hashes by model name from model-version records."""

    return {
        model_name: model_version.data_hash
        for model_name, model_version in model_versions.items()
        if model_version is not None
    }


def build_stale_root_reasons(
    *,
    stale_model_names: tuple[str, ...],
    expected_local_hashes: dict[str, str],
    bound_version_hashes: dict[str, str],
    bound_local_hashes: dict[str, str],
) -> dict[str, PlanReason]:
    """Classify stale root models by first-run vs local semantic change."""

    stale_root_reasons: dict[str, PlanReason] = {}
    stale_model_name: str
    for stale_model_name in stale_model_names:
        bound_version_hash: str | None = bound_version_hashes.get(stale_model_name)
        if bound_version_hash is None:
            stale_root_reasons[stale_model_name] = PlanReason.FIRST_RUN
            continue
        expected_local_hash: str | None = expected_local_hashes.get(stale_model_name)
        bound_local_hash: str | None = bound_local_hashes.get(stale_model_name)
        if expected_local_hash != bound_local_hash:
            stale_root_reasons[stale_model_name] = PlanReason.QUERY_CHANGED
    return stale_root_reasons


def build_stale_root_causes(
    *,
    stale_model_names: tuple[str, ...],
    stale_root_reasons: dict[str, PlanReason],
    graph: ProjectGraph,
) -> dict[str, str]:
    """Assign each non-root stale model to one stale root cause."""

    causes: dict[str, str] = {}
    stale_root_name: str
    for stale_root_name in sorted(stale_root_reasons):
        start_key: Any | None = graph.all_keys.get(stale_root_name)
        if start_key is None:
            continue
        stack: list[Any] = [start_key]
        visited: set[Any] = set()
        while stack:
            current: Any = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if (
                current.resource_type == CompiledResourceType.MODEL
                and current.name in stale_model_names
                and current.name not in stale_root_reasons
                and current.name not in causes
            ):
                causes[current.name] = stale_root_name
            downstream_key: Any
            for downstream_key in graph.downstream_deps.get(current, ()):  # pragma: no branch
                stack.append(downstream_key)
    return causes


def build_default_virtual_selection(
    *,
    stale_model_names: tuple[str, ...],
    graph: ProjectGraph,
) -> tuple[str, ...]:
    """Return stale models plus their downstream model closure."""

    selected: set[str] = set(stale_model_names)
    stale_model_name: str
    for stale_model_name in stale_model_names:
        start_key: Any | None = graph.all_keys.get(stale_model_name)
        if start_key is None:
            continue
        stack: list[Any] = [start_key]
        visited: set[Any] = set()
        while stack:
            current: Any = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if current.resource_type == CompiledResourceType.MODEL:
                selected.add(current.name)
            downstream_key: Any
            for downstream_key in graph.downstream_deps.get(current, ()):  # pragma: no branch
                stack.append(downstream_key)
    return tuple(sorted(selected))


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _topologically_order_keys(graph: ProjectGraph) -> tuple[Any, ...]:
    indegree: dict[Any, int] = {key: len(deps) for key, deps in graph.upstream_deps.items()}
    ready: list[Any] = sorted(
        (key for key, count in indegree.items() if count == 0),
        key=lambda obj: (obj.resource_type, obj.name),
    )
    ordered: list[Any] = []
    while ready:
        current: Any = ready.pop(0)
        ordered.append(current)
        downstream_key: Any
        for downstream_key in graph.downstream_deps.get(current, ()):  # pragma: no branch
            if downstream_key not in indegree:
                continue
            indegree[downstream_key] -= 1
            if indegree[downstream_key] == 0:
                ready.append(downstream_key)
                ready.sort(key=lambda obj: (obj.resource_type, obj.name))
    return tuple(ordered)
