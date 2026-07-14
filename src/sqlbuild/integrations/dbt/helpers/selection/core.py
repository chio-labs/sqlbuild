"""SQLBuild selection resolution for future `sqb dbt` commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.graph.main.path_nodes import path_nodes
from sqlbuild.compiler.planner.main.planning.selector_expansion import split_selector_expansion
from sqlbuild.compiler.planner.main.planning.sqlbuild_model_selectors import (
    resolve_sqlbuild_model_selector_names,
)
from sqlbuild.compiler.planner.models import SelectorExpansion
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.graph.core import (
    dbt_model_graph_key,
    expand_combined_downstream,
    expand_combined_upstream,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.selection.constants import DBT_PATH_SELECTOR_SEPARATOR
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtInteropSelectionResult,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner


def resolve_dbt_interop_sqlbuild_selection(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex | None = None,
    graph: DbtCombinedGraph,
    select: Sequence[str],
    exclude: Sequence[str] = (),
    dbt_anchor_unique_ids_by_term: Mapping[str, Sequence[str]] | None = None,
) -> DbtInteropSelectionResult:
    """Resolve selected SQLBuild models and required dbt nodes from `sqb dbt` selectors."""

    anchors_by_term: Mapping[str, Sequence[str]] = dbt_anchor_unique_ids_by_term or {}
    selected_sqlbuild: set[str] = set()
    required_dbt: set[str] = set()
    anchor_terms: list[str] = []
    anchor_result: dict[str, tuple[str, ...]] = {}
    path_translations: list[tuple[str, str]] = []

    term: str
    for term in select:
        parsed: SelectorExpansion = split_selector_expansion(term)
        path_keys: frozenset[DbtCombinedGraphKey] | None = _resolve_path_between_keys(
            project=project,
            manifest=manifest,
            graph=graph,
            parsed=parsed,
            raw_term=term,
        )
        if path_keys is not None:
            expanded_keys: set[DbtCombinedGraphKey] = set(path_keys)
            key: DbtCombinedGraphKey
            if parsed.upstream:
                for key in tuple(path_keys):
                    expanded_keys.update(
                        expand_combined_upstream(key=key, upstream=graph.upstream_deps)
                    )
            if parsed.downstream:
                for key in tuple(path_keys):
                    expanded_keys.update(
                        expand_combined_downstream(key=key, downstream=graph.downstream_deps)
                    )
            selected_sqlbuild, required_dbt = _add_expanded_keys(
                keys=frozenset(expanded_keys),
                selected_sqlbuild=selected_sqlbuild,
                required_dbt=required_dbt,
            )
            continue

        direct_keys: frozenset[DbtCombinedGraphKey]
        direct_keys, translated_path = _resolve_direct_sqlbuild_keys(
            project=project,
            term=parsed.core,
        )
        if translated_path is not None:
            path_translations.append((term, translated_path))
        if direct_keys:
            expanded_keys: set[DbtCombinedGraphKey] = set(direct_keys)
            key: DbtCombinedGraphKey
            if parsed.upstream:
                for key in tuple(direct_keys):
                    expanded_keys.update(
                        expand_combined_upstream(key=key, upstream=graph.upstream_deps)
                    )
            if parsed.downstream:
                for key in tuple(direct_keys):
                    expanded_keys.update(
                        expand_combined_downstream(key=key, downstream=graph.downstream_deps)
                    )
            selected_sqlbuild, required_dbt = _add_expanded_keys(
                keys=frozenset(expanded_keys),
                selected_sqlbuild=selected_sqlbuild,
                required_dbt=required_dbt,
            )
            continue

        if not parsed.downstream:
            continue
        anchor_unique_ids: tuple[str, ...] = tuple(anchors_by_term.get(term, ()))
        anchor_terms.append(term)
        anchor_result[term] = anchor_unique_ids
        for unique_id in anchor_unique_ids:
            downstream_keys: frozenset[DbtCombinedGraphKey] = expand_combined_downstream(
                key=dbt_model_graph_key(unique_id), downstream=graph.downstream_deps
            )
            selected_sqlbuild, required_dbt = _add_expanded_keys(
                keys=downstream_keys,
                selected_sqlbuild=selected_sqlbuild,
                required_dbt=required_dbt,
            )

    excluded_sqlbuild: frozenset[str] = _resolve_excluded_sqlbuild_names(
        project=project,
        exclude=exclude,
    )
    selected_sqlbuild.difference_update(excluded_sqlbuild)
    return DbtInteropSelectionResult(
        sqlbuild_model_names=tuple(sorted(selected_sqlbuild)),
        dbt_required_unique_ids=tuple(sorted(required_dbt)),
        dbt_anchor_terms=tuple(anchor_terms),
        dbt_anchor_unique_ids_by_term=anchor_result,
        path_translations=tuple(path_translations),
    )


def _resolve_path_between_keys(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex | None,
    graph: DbtCombinedGraph,
    parsed: SelectorExpansion,
    raw_term: str,
) -> frozenset[DbtCombinedGraphKey] | None:
    if DBT_PATH_SELECTOR_SEPARATOR not in parsed.core:
        return None
    start_name, end_name = _path_endpoint_names(term=parsed.core, raw_term=raw_term)
    start_key: DbtCombinedGraphKey = _resolve_path_endpoint_key(
        project=project,
        manifest=manifest,
        endpoint=start_name,
        raw_term=raw_term,
    )
    end_key: DbtCombinedGraphKey = _resolve_path_endpoint_key(
        project=project,
        manifest=manifest,
        endpoint=end_name,
        raw_term=raw_term,
    )
    return path_nodes(start=start_key, end=end_key, downstream=graph.downstream_deps) or frozenset()


def _path_endpoint_names(*, term: str, raw_term: str) -> tuple[str, str]:
    start_name, end_name = (part.strip() for part in term.split(DBT_PATH_SELECTOR_SEPARATOR, 1))
    if not start_name or not end_name:
        raise DbtInteropArgumentError(
            f"path selector '{raw_term}' requires names on both sides of '~'",
            code="C237",
        )
    return start_name, end_name


def _resolve_path_endpoint_key(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex | None,
    endpoint: str,
    raw_term: str,
) -> DbtCombinedGraphKey:
    sqlbuild_model_names, _translation = resolve_sqlbuild_model_selector_names(
        project=project,
        term=endpoint,
    )
    if sqlbuild_model_names:
        return sqlbuild_model_graph_key(sqlbuild_model_names[0])
    if manifest is None:
        raise DbtInteropArgumentError(
            f"path selector '{raw_term}' endpoint '{endpoint}' is not a SQLBuild model",
            code="C237",
        )
    dbt_models: tuple[DbtManifestModel, ...] = tuple(
        model for model in manifest.models_by_unique_id.values() if model.name == endpoint
    )
    if len(dbt_models) == 1:
        return dbt_model_graph_key(dbt_models[0].unique_id)
    if len(dbt_models) > 1:
        raise DbtInteropArgumentError(
            f"path selector '{raw_term}' endpoint '{endpoint}' is ambiguous across dbt models",
            code="C237",
        )
    raise DbtInteropArgumentError(
        f"path selector '{raw_term}' endpoint '{endpoint}' is not a known SQLBuild or dbt model",
        code="C237",
    )


def _resolve_direct_sqlbuild_keys(
    *, project: CompiledProject, term: str
) -> tuple[frozenset[DbtCombinedGraphKey], str | None]:
    model_names, translated_path = resolve_sqlbuild_model_selector_names(
        project=project,
        term=term,
    )
    return frozenset(
        sqlbuild_model_graph_key(model_name) for model_name in model_names
    ), translated_path


def _add_expanded_keys(
    *,
    keys: frozenset[DbtCombinedGraphKey],
    selected_sqlbuild: set[str],
    required_dbt: set[str],
) -> tuple[set[str], set[str]]:
    key: DbtCombinedGraphKey
    for key in keys:
        if key.owner == DbtCombinedGraphOwner.SQLBUILD:
            selected_sqlbuild.add(key.name)
        elif key.owner == DbtCombinedGraphOwner.DBT:
            required_dbt.add(key.name)
    return selected_sqlbuild, required_dbt


def _resolve_excluded_sqlbuild_names(
    *, project: CompiledProject, exclude: Sequence[str]
) -> frozenset[str]:
    excluded: set[str] = set()
    term: str
    for term in exclude:
        parsed: SelectorExpansion = split_selector_expansion(term)
        keys, _translation = _resolve_direct_sqlbuild_keys(
            project=project,
            term=parsed.core,
        )
        key: DbtCombinedGraphKey
        for key in keys:
            if key.owner == DbtCombinedGraphOwner.SQLBUILD:
                excluded.add(key.name)
    return frozenset(excluded)
