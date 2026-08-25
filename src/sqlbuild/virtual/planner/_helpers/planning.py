"""Pure virtual planning helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.identity.seed_identity import build_seed_identity
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes as build_shared_function_local_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_local_hash import (
    build_model_local_identity_hash,
)
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.main.identity.version_identity_stale_model_names import (
    build_version_identity_stale_model_names,
)
from sqlbuild.compiler.planner.main.identity.version_identity_version_hash import (
    build_model_version_identity_hash,
)
from sqlbuild.compiler.planner.main.selection.model_downstream_closure import (
    build_downstream_model_names,
)
from sqlbuild.compiler.planner.main.selection.model_upstream_closure import (
    build_upstream_model_names,
)
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.compiler.planner.types import PlanReason, WorkSelectionPolicy
from sqlbuild.compiler.python_nodes.main.hook_identities import build_hook_identities
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    SourceFreshnessRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)


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
        expected_local_hashes[model.name] = build_model_local_identity_hash(
            query_sql=model.query_sql,
            metadata_json=model_metadata_jsons[model.name],
        )
    return expected_local_hashes


def build_function_local_hashes(*, graph: ProjectGraph) -> dict[str, str]:
    """Derive local-only semantic hashes for functions."""

    return build_shared_function_local_hashes(functions=graph.project.functions)


def build_expected_seed_version_hashes(*, graph: ProjectGraph) -> dict[str, str]:
    """Derive expected seed version hashes from current compiled seed identities."""

    version_hashes: dict[str, str] = {}
    for seed in graph.project.seeds:
        seed_version_hash, _metadata_json = build_seed_identity(seed)
        version_hashes[seed.name] = seed_version_hash
    return version_hashes


def build_seed_identity_metadata_jsons(*, graph: ProjectGraph) -> dict[str, str]:
    """Build deterministic seed identity metadata JSON by seed name."""

    metadata_jsons: dict[str, str] = {}
    for seed in graph.project.seeds:
        _seed_version_hash, metadata_json = build_seed_identity(seed)
        metadata_jsons[seed.name] = metadata_json
    return metadata_jsons


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
    hook_version_hashes: dict[str, str] = {
        name: identity.version_hash
        for name, identity in build_hook_identities(graph.project.hook_functions).items()
    }
    models_by_name: dict[str, Any] = {model.name: model for model in graph.project.models}
    key: Any
    for key in _topologically_order_keys(graph):
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: Any | None = models_by_name.get(key.name)
        if model is None:
            continue
        result[model.name] = build_model_version_identity_metadata_json(
            model=model,
            function_local_hashes=function_hashes,
            hook_version_hashes=hook_version_hashes,
        )
    return result


def build_expected_version_hashes(
    *,
    graph: ProjectGraph,
    expected_local_hashes: dict[str, str],
    source_version_hashes: dict[str, str] | None = None,
    seed_version_hashes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Derive expected model version hashes from current code and upstream hashes."""

    source_hashes: dict[str, str] = source_version_hashes or {}
    expected_hashes: dict[str, str] = {
        function.name: expected_local_hashes[function.name] for function in graph.project.functions
    }
    expected_hashes.update(seed_version_hashes or build_expected_seed_version_hashes(graph=graph))
    models_by_name: dict[str, Any] = {model.name: model for model in graph.project.models}

    key: Any
    for key in _topologically_order_keys(graph):
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: Any | None = models_by_name.get(key.name)
        if model is None:
            continue
        expected_hashes[model.name] = build_model_version_identity_hash(
            local_hash=expected_local_hashes[model.name],
            upstream_deps=model.deps,
            upstream_version_hashes=expected_hashes,
            source_version_hashes=source_hashes,
        )
    return expected_hashes


def build_source_freshness_incomplete_model_names(
    *,
    graph: ProjectGraph,
    source_version_hashes: dict[str, str],
) -> tuple[str, ...]:
    """Return models whose upstream source freshness proof is incomplete."""

    incomplete_source_keys: tuple[Any, ...] = tuple(
        source.key for source in graph.project.sources if source.name not in source_version_hashes
    )
    incomplete_model_names: set[str] = set()
    source_key: Any
    for source_key in incomplete_source_keys:
        stack: list[Any] = list(graph.downstream_deps.get(source_key, ()))
        visited: set[Any] = set()
        while stack:
            current: Any = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if current.resource_type == CompiledResourceType.MODEL:
                incomplete_model_names.add(current.name)
            downstream_key: Any
            for downstream_key in graph.downstream_deps.get(current, ()):  # pragma: no branch
                stack.append(downstream_key)
    return tuple(sorted(incomplete_model_names))


def build_bound_version_hashes(
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, str]:
    """Index bound version hashes by model name from VDE refs."""

    return {ref.model_name: ref.version_hash for ref in refs}


def build_bound_seed_version_hashes(
    refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
) -> dict[str, str]:
    """Index bound version hashes by seed name from VDE seed refs."""

    return {ref.seed_name: ref.version_hash for ref in refs}


def build_stale_seed_names(
    *,
    seed_names: tuple[str, ...],
    expected_seed_version_hashes: dict[str, str],
    bound_seed_version_hashes: dict[str, str],
) -> tuple[str, ...]:
    """Return seed names whose bound and expected version hashes differ."""

    return tuple(
        sorted(
            seed_name
            for seed_name in seed_names
            if bound_seed_version_hashes.get(seed_name)
            != expected_seed_version_hashes.get(seed_name)
        )
    )


def build_seed_plan_reasons(
    *,
    seed_names: tuple[str, ...],
    expected_seed_version_hashes: dict[str, str],
    bound_seed_version_hashes: dict[str, str],
) -> dict[str, PlanReason]:
    """Classify VDE seed plan reasons from typed seed refs."""

    reasons: dict[str, PlanReason] = {}
    seed_name: str
    for seed_name in seed_names:
        bound_version_hash: str | None = bound_seed_version_hashes.get(seed_name)
        expected_version_hash: str | None = expected_seed_version_hashes.get(seed_name)
        if bound_version_hash is None:
            reasons[seed_name] = PlanReason.FIRST_RUN
        elif expected_version_hash is not None and bound_version_hash != expected_version_hash:
            reasons[seed_name] = PlanReason.CONFIG_CHANGED
        else:
            reasons[seed_name] = PlanReason.NO_CHANGE
    return reasons


def build_source_version_hashes(
    records: tuple[SourceFreshnessRecord, ...],
) -> dict[str, str]:
    """Index source freshness input hashes by source name."""

    return {record.source_name: record.data_version_hash for record in records}


def build_source_freshness_unchanged_source_names(
    *,
    previous_records: tuple[SourceFreshnessRecord, ...],
    current_records: tuple[SourceFreshnessRecord, ...],
) -> tuple[str, ...]:
    """Return source names whose current freshness record matches previous state."""

    previous_by_source: dict[str, SourceFreshnessRecord] = {
        record.source_name: record for record in previous_records
    }
    return tuple(
        sorted(
            record.source_name
            for record in current_records
            if previous_by_source.get(record.source_name) is not None
            and previous_by_source[record.source_name].data_version_hash == record.data_version_hash
        )
    )


def build_stale_model_names(
    *,
    model_names: tuple[str, ...],
    expected_version_hashes: dict[str, str],
    bound_version_hashes: dict[str, str],
    source_freshness_incomplete_model_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return model names whose bound and expected hashes differ."""

    return build_version_identity_stale_model_names(
        model_names=model_names,
        expected_version_hashes=expected_version_hashes,
        built_version_hashes=bound_version_hashes,
        forced_stale_model_names=source_freshness_incomplete_model_names,
    )


def build_bound_local_hashes(
    model_versions: dict[str, ModelVersionRecord | None],
) -> dict[str, str]:
    """Index bound local semantic hashes by model name from model-version records."""

    return {
        model_name: model_version.definition_identity_hash
        for model_name, model_version in model_versions.items()
        if model_version is not None
    }


def build_stale_root_reasons(
    *,
    stale_model_names: tuple[str, ...],
    expected_local_hashes: dict[str, str],
    bound_version_hashes: dict[str, str],
    bound_local_hashes: dict[str, str],
    current_query_sqls: dict[str, str] | None = None,
    bound_previous_query_sqls: dict[str, str] | None = None,
    expected_metadata_jsons: dict[str, str] | None = None,
    bound_metadata_jsons: dict[str, str] | None = None,
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
            current_query_sql: str | None = (current_query_sqls or {}).get(stale_model_name)
            previous_query_sql: str | None = (bound_previous_query_sqls or {}).get(stale_model_name)
            if previous_query_sql is not None and current_query_sql != previous_query_sql:
                stale_root_reasons[stale_model_name] = PlanReason.QUERY_CHANGED
                continue
            expected_metadata_json: str | None = (expected_metadata_jsons or {}).get(
                stale_model_name
            )
            bound_metadata_json: str | None = (bound_metadata_jsons or {}).get(stale_model_name)
            if _metadata_config_payload(expected_metadata_json) != _metadata_config_payload(
                bound_metadata_json
            ):
                stale_root_reasons[stale_model_name] = PlanReason.CONFIG_CHANGED
                continue
            stale_root_reasons[stale_model_name] = PlanReason.QUERY_CHANGED
    return stale_root_reasons


def _metadata_config_payload(metadata_json: str | None) -> object:
    if metadata_json is None:
        return None
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    if not isinstance(payload, dict):
        return None
    return payload.get("config", {})


def _metadata_function_hashes(metadata_json: str | None) -> dict[str, str]:
    if metadata_json is None:
        return {}
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_hashes: object = payload.get("local_function_hashes", {})
    if not isinstance(raw_hashes, dict):
        return {}
    return {str(name): str(value) for name, value in raw_hashes.items()}


def build_stale_root_causes(
    *,
    stale_model_names: tuple[str, ...],
    stale_root_reasons: dict[str, PlanReason],
    graph: ProjectGraph,
    stale_root_source_causes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign each non-root stale model to one stale root cause."""

    causes: dict[str, str] = {}
    root_source_causes: dict[str, str] = stale_root_source_causes or {}
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
                causes[current.name] = root_source_causes.get(stale_root_name, stale_root_name)
            downstream_key: Any
            for downstream_key in graph.downstream_deps.get(current, ()):  # pragma: no branch
                stack.append(downstream_key)
    return causes


def build_stale_root_source_causes(
    *,
    stale_root_reasons: dict[str, PlanReason],
    expected_metadata_jsons: dict[str, str],
    bound_metadata_jsons: dict[str, str],
) -> dict[str, str]:
    """Map stale root models to changed function names when function metadata is the root."""

    result: dict[str, str] = {}
    model_name: str
    for model_name, reason in stale_root_reasons.items():
        if reason != PlanReason.QUERY_CHANGED:
            continue
        expected_hashes: dict[str, str] = _metadata_function_hashes(
            expected_metadata_jsons.get(model_name)
        )
        bound_hashes: dict[str, str] = _metadata_function_hashes(
            bound_metadata_jsons.get(model_name)
        )
        changed_function_names: tuple[str, ...] = tuple(
            sorted(
                function_name
                for function_name, expected_hash in expected_hashes.items()
                if bound_hashes.get(function_name) != expected_hash
            )
        )
        if len(changed_function_names) == 1:
            result[model_name] = changed_function_names[0]
    return result


def build_stale_root_cause_reasons(
    *,
    stale_root_reasons: dict[str, PlanReason],
    stale_root_source_causes: dict[str, str],
) -> dict[str, PlanReason]:
    """Map display cause names to display cause reasons."""

    result: dict[str, PlanReason] = {}
    for root_name, root_reason in stale_root_reasons.items():
        cause_name: str = stale_root_source_causes.get(root_name, root_name)
        cause_reason: PlanReason = root_reason
        if cause_name != root_name and root_reason == PlanReason.QUERY_CHANGED:
            cause_reason = PlanReason.FUNCTION_CHANGED
        result[cause_name] = cause_reason
    return result


def build_default_virtual_selection(
    *,
    stale_model_names: tuple[str, ...],
    graph: ProjectGraph,
) -> tuple[str, ...]:
    """Return stale models plus their downstream model closure."""

    start_keys: tuple[CompiledObjectKey, ...] = tuple(
        key
        for model_name in stale_model_names
        if (key := graph.all_keys.get(model_name)) is not None
    )
    return tuple(
        sorted(
            build_downstream_model_names(
                start_keys=start_keys,
                downstream_deps=graph.downstream_deps,
            )
        )
    )


def resolve_virtual_model_selection(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    default_selection: tuple[str, ...],
    stale_model_names: tuple[str, ...],
    include_stale_upstreams: bool = False,
    work_selection_policy: WorkSelectionPolicy = WorkSelectionPolicy.ALL_SELECTED,
) -> tuple[str, ...]:
    """Resolve and guard the effective virtual model selection."""

    selected_model_names: tuple[str, ...] = (
        _resolve_selected_model_names(graph=graph, select=select, exclude=exclude)
        if select
        else _apply_exclude_to_model_names(
            graph=graph,
            model_names=default_selection,
            exclude=exclude,
        )
    )
    if work_selection_policy == WorkSelectionPolicy.STALE_ONLY:
        default_set: set[str] = set(default_selection)
        selected_model_names = tuple(
            model_name for model_name in selected_model_names if model_name in default_set
        )
    stale_upstream_names: tuple[str, ...] = build_stale_required_upstream_closure(
        graph=graph,
        selected_model_names=selected_model_names,
        stale_model_names=stale_model_names,
    )
    if stale_upstream_names and not include_stale_upstreams:
        stale_list: str = ", ".join(stale_upstream_names)
        raise PlannerInputError(
            f"selected virtual scope is missing stale required upstream models: {stale_list}",
            code="S010",
            help=(
                "Re-run with --include-stale-upstreams to add the minimal required "
                "upstream closure."
            ),
        )
    if include_stale_upstreams:
        selected_model_names = tuple(sorted({*selected_model_names, *stale_upstream_names}))
    return selected_model_names


def build_stale_required_upstream_closure(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    stale_model_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return stale model ancestors required by the selected models."""

    selected: set[str] = set(selected_model_names)
    stale: set[str] = set(stale_model_names)
    start_keys: tuple[CompiledObjectKey, ...] = tuple(
        key
        for model_name in selected_model_names
        if (key := graph.all_keys.get(model_name)) is not None
    )
    upstream_start_keys: list[CompiledObjectKey] = []
    for key in start_keys:
        for upstream_key in graph.upstream_deps.get(key, ()):
            upstream_start_keys.append(upstream_key)
    required: frozenset[str] = build_upstream_model_names(
        start_keys=tuple(upstream_start_keys),
        upstream_deps=graph.upstream_deps,
    )
    return tuple(sorted(model_name for model_name in required if model_name in stale - selected))


def _resolve_selected_model_names(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[str, ...]:
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    return tuple(
        sorted(key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL)
    )


def _apply_exclude_to_model_names(
    *,
    graph: ProjectGraph,
    model_names: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[str, ...]:
    if not model_names or not exclude:
        return model_names
    excluded: set[str] = set(_resolve_selected_model_names(graph=graph, select=exclude, exclude=()))
    return tuple(model_name for model_name in model_names if model_name not in excluded)


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
