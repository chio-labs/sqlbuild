"""SQLBuild selection resolution for future `sqb dbt` commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
)
from sqlbuild.integrations.dbt.helpers.graph.core import (
    dbt_model_graph_key,
    expand_combined_downstream,
    expand_combined_upstream,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtInteropSelectionResult,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner


def resolve_dbt_interop_sqlbuild_selection(
    *,
    project: CompiledProject,
    graph: DbtCombinedGraph,
    select: Sequence[str],
    exclude: Sequence[str] = (),
    dbt_anchor_unique_ids_by_term: Mapping[str, Sequence[str]] | None = None,
) -> DbtInteropSelectionResult:
    """Resolve selected SQLBuild models and required dbt nodes from `sqb dbt` selectors."""

    anchors_by_term: Mapping[str, Sequence[str]] = dbt_anchor_unique_ids_by_term or {}
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    selected_sqlbuild: set[str] = set()
    required_dbt: set[str] = set()
    anchor_terms: list[str] = []
    anchor_result: dict[str, tuple[str, ...]] = {}
    path_translations: list[tuple[str, str]] = []

    term: str
    for term in select:
        parsed: _ParsedSelectionTerm = _parse_selection_term(term)
        direct_keys: frozenset[DbtCombinedGraphKey]
        direct_keys, translated_path = _resolve_direct_sqlbuild_keys(
            project=project,
            models_by_name=models_by_name,
            term=parsed.core,
        )
        if translated_path is not None:
            path_translations.append((term, translated_path))
        if direct_keys:
            expanded_keys: set[DbtCombinedGraphKey] = set(direct_keys)
            key: DbtCombinedGraphKey
            if parsed.upstream:
                for key in tuple(direct_keys):
                    expanded_keys.update(expand_combined_upstream(key, graph.upstream_deps))
            if parsed.downstream:
                for key in tuple(direct_keys):
                    expanded_keys.update(expand_combined_downstream(key, graph.downstream_deps))
            _add_expanded_keys(
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
                dbt_model_graph_key(unique_id), graph.downstream_deps
            )
            _add_expanded_keys(
                keys=downstream_keys,
                selected_sqlbuild=selected_sqlbuild,
                required_dbt=required_dbt,
            )

    excluded_sqlbuild: frozenset[str] = _resolve_excluded_sqlbuild_names(
        project=project,
        models_by_name=models_by_name,
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


class _ParsedSelectionTerm:
    def __init__(self, *, core: str, upstream: bool, downstream: bool) -> None:
        self.core = core
        self.upstream = upstream
        self.downstream = downstream


def _parse_selection_term(term: str) -> _ParsedSelectionTerm:
    upstream: bool = term.startswith("+")
    downstream: bool = term.endswith("+")
    core: str = term.removeprefix("+").removesuffix("+")
    return _ParsedSelectionTerm(core=core, upstream=upstream, downstream=downstream)


def _resolve_direct_sqlbuild_keys(
    *, project: CompiledProject, models_by_name: dict[str, CompiledModel], term: str
) -> tuple[frozenset[DbtCombinedGraphKey], str | None]:
    if term in models_by_name:
        return frozenset((sqlbuild_model_graph_key(term),)), None
    if term.startswith("tag:"):
        tag: str = term.removeprefix("tag:")
        return (
            frozenset(
                sqlbuild_model_graph_key(model.name)
                for model in project.models
                if tag in _as_string_tuple(model.config.values.get("tags"))
            ),
            None,
        )
    if term.startswith("path:"):
        raw_path: str = term.removeprefix("path:")
        translated_path: str = _translate_dbt_path_selector(raw_path)
        return (
            frozenset(
                sqlbuild_model_graph_key(model.name)
                for model in project.models
                if _model_path_selector(model) == translated_path
                or _model_path_selector(model).startswith(f"{translated_path}/")
            ),
            f"path:{translated_path}" if translated_path != raw_path else None,
        )
    return frozenset(), None


def _add_expanded_keys(
    *,
    keys: frozenset[DbtCombinedGraphKey],
    selected_sqlbuild: set[str],
    required_dbt: set[str],
) -> None:
    key: DbtCombinedGraphKey
    for key in keys:
        if key.owner == DbtCombinedGraphOwner.SQLBUILD:
            selected_sqlbuild.add(key.name)
        elif key.owner == DbtCombinedGraphOwner.DBT:
            required_dbt.add(key.name)


def _resolve_excluded_sqlbuild_names(
    *, project: CompiledProject, models_by_name: dict[str, CompiledModel], exclude: Sequence[str]
) -> frozenset[str]:
    excluded: set[str] = set()
    term: str
    for term in exclude:
        parsed: _ParsedSelectionTerm = _parse_selection_term(term)
        keys, _translation = _resolve_direct_sqlbuild_keys(
            project=project,
            models_by_name=models_by_name,
            term=parsed.core,
        )
        key: DbtCombinedGraphKey
        for key in keys:
            if key.owner == DbtCombinedGraphOwner.SQLBUILD:
                excluded.add(key.name)
    return frozenset(excluded)


def _translate_dbt_path_selector(raw_path: str) -> str:
    return raw_path.replace("\\", "/")


def _model_path_selector(model: CompiledModel) -> str:
    return model.relative_path.parent.as_posix()


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()
