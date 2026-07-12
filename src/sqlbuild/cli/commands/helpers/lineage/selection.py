"""Lineage graph selection helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlbuild.cli.commands.helpers.lineage.constants import RICH_LINEAGE_STATUS_MODEL_THRESHOLD
from sqlbuild.cli.commands.helpers.lineage.models import (
    ColumnLineageTrace,
    LineageGraph,
    LineageNode,
    LineageSelectionAnchors,
    ParsedLineagePathSelector,
    ParsedLineageSelector,
)
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.main.columns import build_project_column_lineage
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.shared.main.maybe_status import maybe_status


@dataclass(frozen=True)
class _ColumnLineageCandidateSelection:
    model_names: frozenset[str]
    truncated: bool


def parse_depth(raw_depth: str) -> int | None:
    """Parse a lineage depth value, returning None for unlimited traversal."""

    if raw_depth == "all":
        return None
    try:
        depth: int = int(raw_depth)
    except ValueError:
        raise CliUserError("--depth must be a non-negative integer or 'all'", code="C304") from None
    if depth < 0:
        raise CliUserError("--depth must be a non-negative integer or 'all'", code="C304")
    return depth


def select_target_lineage(
    *,
    graph: ProjectGraph,
    target: str,
    direction: str,
    depth: int | None,
) -> LineageGraph:
    """Select lineage around one positional target."""

    key: CompiledObjectKey | None = graph.all_keys.get(target)
    if key is None:
        raise CliUserError(f"unknown lineage target '{target}'", code="C305")

    selected: set[CompiledObjectKey] = {key}
    if direction in {"upstream", "both"}:
        selected.update(_walk_bounded(anchors=(key,), deps=graph.upstream_deps, max_depth=depth))
    if direction in {"downstream", "both"}:
        selected.update(_walk_bounded(anchors=(key,), deps=graph.downstream_deps, max_depth=depth))
    return build_lineage_graph(
        project=graph.project,
        upstream_deps=graph.upstream_deps,
        selected_keys=frozenset(selected),
        focus_keys=(key,),
        direction=direction,
    )


def select_column_target_lineage(
    *,
    graph: ProjectGraph,
    target: str,
    direction: str,
    depth: int | None,
    mode: ColumnLineageMode = ColumnLineageMode.RICH,
) -> ColumnLineageTrace | None:
    """Select column-level lineage when target uses model.column syntax."""

    if "." not in target:
        return None
    resource_name: str
    column_name: str
    resource_name, column_name = target.rsplit(".", 1)
    key: CompiledObjectKey | None = graph.all_keys.get(resource_name)
    if key is None or key.resource_type != CompiledResourceType.MODEL:
        return None
    if direction == "both":
        raise CliUserError(
            "column lineage supports --direction upstream or downstream, not both",
            code="C306",
        )

    candidate_selection: _ColumnLineageCandidateSelection = _column_lineage_candidate_selection(
        graph=graph,
        key=key,
        direction=direction,
        depth=depth,
    )
    with maybe_status(
        message=f"Analyzing column lineage for {len(candidate_selection.model_names)} models...",
        enabled=(
            mode == ColumnLineageMode.RICH
            and len(candidate_selection.model_names) >= RICH_LINEAGE_STATUS_MODEL_THRESHOLD
        ),
    ):
        column_lineage: ProjectColumnLineage | None = build_project_column_lineage(
            project=graph.project,
            mode=mode,
            model_names=candidate_selection.model_names,
        )
    if column_lineage is None:
        raise CliUserError(
            "column lineage requires SQL analysis to be enabled and available",
            code="C307",
            help="enable SQL analysis or install SQLBuild with Polyglot support",
        )

    target_column: QualifiedLineageColumn = QualifiedLineageColumn(
        resource_type=key.resource_type,
        resource_name=key.name,
        column_name=column_name,
    )
    trace: tuple[ColumnLineageEdge, ...] = _trace_column_with_depth(
        column_lineage=column_lineage,
        resource_name=key.name,
        column_name=column_name,
        direction=direction,
        max_depth=depth,
    )
    return ColumnLineageTrace(
        target=target_column,
        trace=trace,
        direction=direction,
        mode=mode,
        max_depth=depth,
        analyzed_model_count=len(candidate_selection.model_names),
        truncated=candidate_selection.truncated,
    )


def _column_lineage_candidate_selection(
    *,
    graph: ProjectGraph,
    key: CompiledObjectKey,
    direction: str,
    depth: int | None,
) -> _ColumnLineageCandidateSelection:
    selected: set[CompiledObjectKey] = {key}
    deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        graph.downstream_deps if direction == "downstream" else graph.upstream_deps
    )
    selected.update(_walk_bounded(anchors=(key,), deps=deps, max_depth=depth))
    model_names: frozenset[str] = frozenset(
        selected_key.name
        for selected_key in selected
        if selected_key.resource_type == CompiledResourceType.MODEL
    )
    if depth is None:
        return _ColumnLineageCandidateSelection(model_names=model_names, truncated=False)
    extended: set[CompiledObjectKey] = {key}
    extended.update(_walk_bounded(anchors=(key,), deps=deps, max_depth=depth + 1))
    return _ColumnLineageCandidateSelection(
        model_names=model_names,
        truncated=extended != selected,
    )


def _trace_column_with_depth(
    *,
    column_lineage: ProjectColumnLineage,
    resource_name: str,
    column_name: str,
    direction: str,
    max_depth: int | None,
) -> tuple[ColumnLineageEdge, ...]:
    if max_depth == 0:
        return ()
    result: list[ColumnLineageEdge] = []
    stack: list[tuple[str, str, int]] = [(resource_name, column_name, 0)]
    visited: set[tuple[str, str]] = set()
    while stack:
        current_resource: str
        current_column: str
        current_depth: int
        current_resource, current_column, current_depth = stack.pop()
        if (current_resource, current_column) in visited:
            continue
        visited.add((current_resource, current_column))
        if max_depth is not None and current_depth >= max_depth:
            continue
        if direction == "downstream":
            edges: tuple[ColumnLineageEdge, ...] = column_lineage.column_consumers(
                resource_name=current_resource,
                column_name=current_column,
            )
            for edge in edges:
                result.append(edge)
                stack.append(
                    (edge.target.resource_name, edge.target.column_name, current_depth + 1)
                )
        else:
            for edge in column_lineage.edges_targeting(current_resource):
                if edge.target.column_name != current_column:
                    continue
                result.append(edge)
                stack.append(
                    (edge.source.resource_name, edge.source.column_name, current_depth + 1)
                )
    return tuple(result)


def select_selector_lineage(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    depth: int | None,
) -> LineageGraph:
    """Select lineage using existing selector semantics."""

    selected_keys: frozenset[CompiledObjectKey] = _resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream=graph.upstream_deps,
        downstream=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    anchors: LineageSelectionAnchors = _resolve_selector_anchors(
        select=select,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
        require_clear_anchors=depth is not None,
    )
    if depth is not None:
        selected_keys = _trim_selected_keys(
            selected_keys=selected_keys,
            anchors=anchors,
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            max_depth=depth,
        )
    focus_keys: tuple[CompiledObjectKey, ...] = tuple(
        sorted(anchors.upstream | anchors.downstream, key=_sort_key)
    )
    return build_lineage_graph(
        project=graph.project,
        upstream_deps=graph.upstream_deps,
        selected_keys=selected_keys,
        focus_keys=focus_keys,
        direction=None,
    )


def build_lineage_graph(
    *,
    project: CompiledProject,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
    focus_keys: tuple[CompiledObjectKey, ...] = (),
    direction: str | None = None,
) -> LineageGraph:
    """Build display nodes and selected edges."""

    nodes: tuple[LineageNode, ...] = tuple(
        _build_node(project=project, key=key) for key in sorted(selected_keys, key=_sort_key)
    )
    selected_edges: list[tuple[CompiledObjectKey, CompiledObjectKey]] = []
    for downstream_key in sorted(selected_keys, key=_sort_key):
        for upstream_key in upstream_deps.get(downstream_key, ()):
            if upstream_key in selected_keys:
                selected_edges.append((upstream_key, downstream_key))
    return LineageGraph(
        nodes=nodes,
        edges=tuple(selected_edges),
        focus_keys=focus_keys,
        direction=direction,
    )


def _resolve_selector_anchors(
    *,
    select: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
    require_clear_anchors: bool,
) -> LineageSelectionAnchors:
    upstream_anchors: set[CompiledObjectKey] = set()
    downstream_anchors: set[CompiledObjectKey] = set()
    retained: set[CompiledObjectKey] = set()

    for raw_select in select:
        for token in raw_select.split():
            if "," in token and require_clear_anchors:
                raise CliUserError(
                    "--depth cannot be combined with comma-intersection selectors",
                    code="C308",
                )
            parts: list[str] = token.split(",")
            for part in parts:
                parsed: ParsedLineageSelector | ParsedLineagePathSelector = _parse_selector(part)
                if isinstance(parsed, ParsedLineagePathSelector):
                    start_key: CompiledObjectKey = _lookup_name(
                        name=parsed.start_name, all_keys=all_keys
                    )
                    end_key: CompiledObjectKey = _lookup_name(
                        name=parsed.end_name, all_keys=all_keys
                    )
                    retained.update(
                        _find_path_keys(start=start_key, end=end_key, downstream=downstream_deps)
                    )
                    upstream_anchors.add(start_key)
                    downstream_anchors.add(end_key)
                    continue
                if parsed.kind in {"tag", "path"}:
                    if require_clear_anchors:
                        raise CliUserError(
                            "--depth requires name, source, seed, or path-between selectors",
                            code="C309",
                        )
                    matched: frozenset[CompiledObjectKey]
                    if parsed.kind == "tag":
                        matched = tag_index.get(parsed.value, frozenset())
                    else:
                        matched = _match_path(folder=parsed.value, path_index=path_index)
                    upstream_anchors.update(matched)
                    downstream_anchors.update(matched)
                    continue
                key: CompiledObjectKey = _lookup_parsed_selector(parsed=parsed, all_keys=all_keys)
                if parsed.upstream:
                    upstream_anchors.add(key)
                if parsed.downstream:
                    downstream_anchors.add(key)
                if not parsed.upstream and not parsed.downstream:
                    retained.add(key)
    return LineageSelectionAnchors(
        upstream=frozenset(upstream_anchors),
        downstream=frozenset(downstream_anchors),
        retained=frozenset(retained),
    )


def _trim_selected_keys(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    anchors: LineageSelectionAnchors,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    max_depth: int,
) -> frozenset[CompiledObjectKey]:
    retained: set[CompiledObjectKey] = set(anchors.retained)
    retained.update(anchors.upstream)
    retained.update(anchors.downstream)
    retained.update(
        _walk_bounded(anchors=anchors.upstream, deps=upstream_deps, max_depth=max_depth)
    )
    retained.update(
        _walk_bounded(anchors=anchors.downstream, deps=downstream_deps, max_depth=max_depth)
    )
    return frozenset(selected_keys & retained)


def _walk_bounded(
    *,
    anchors: Iterable[CompiledObjectKey],
    deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    max_depth: int | None,
) -> frozenset[CompiledObjectKey]:
    if max_depth is None:
        result: set[CompiledObjectKey] = set()
        for anchor in anchors:
            result.update(_walk_all(key=anchor, deps=deps))
        return frozenset(result)
    if max_depth == 0:
        return frozenset()
    visited: set[CompiledObjectKey] = set()
    queue: list[tuple[CompiledObjectKey, int]] = [(anchor, 0) for anchor in anchors]
    while queue:
        current, current_depth = queue.pop(0)
        if current_depth >= max_depth:
            continue
        for neighbor in deps.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, current_depth + 1))
    return frozenset(visited)


def _walk_all(
    *,
    key: CompiledObjectKey,
    deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        for neighbor in deps.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)


def _lookup_name(*, name: str, all_keys: dict[str, CompiledObjectKey]) -> CompiledObjectKey:
    key: CompiledObjectKey | None = all_keys.get(name)
    if key is None:
        raise CliUserError(f"unknown lineage target '{name}'", code="C305")
    return key


def _resolve_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    selected: set[CompiledObjectKey] = set()
    for raw_select in select:
        for token in raw_select.split():
            selected.update(
                _resolve_token(
                    token=token,
                    all_keys=all_keys,
                    upstream=upstream,
                    downstream=downstream,
                    tag_index=tag_index,
                    path_index=path_index,
                )
            )
    excluded: set[CompiledObjectKey] = set()
    for raw_exclude in exclude:
        for token in raw_exclude.split():
            excluded.update(
                _resolve_token(
                    token=token,
                    all_keys=all_keys,
                    upstream=upstream,
                    downstream=downstream,
                    tag_index=tag_index,
                    path_index=path_index,
                )
            )
    scoped: set[CompiledObjectKey] = selected - excluded
    for key in tuple(scoped):
        for upstream_key in _walk_all(key=key, deps=upstream):
            if upstream_key.resource_type in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                scoped.add(upstream_key)
    return frozenset(scoped)


def _resolve_token(
    *,
    token: str,
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    parts: list[str] = token.split(",")
    resolved_parts: list[frozenset[CompiledObjectKey]] = [
        _resolve_single(
            raw=part,
            all_keys=all_keys,
            upstream=upstream,
            downstream=downstream,
            tag_index=tag_index,
            path_index=path_index,
        )
        for part in parts
    ]
    result: frozenset[CompiledObjectKey] = resolved_parts[0]
    for subsequent in resolved_parts[1:]:
        result = result & subsequent
    return result


def _resolve_single(
    *,
    raw: str,
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    parsed: ParsedLineageSelector | ParsedLineagePathSelector = _parse_selector(raw)
    if isinstance(parsed, ParsedLineagePathSelector):
        start_key: CompiledObjectKey = _lookup_name(name=parsed.start_name, all_keys=all_keys)
        end_key: CompiledObjectKey = _lookup_name(name=parsed.end_name, all_keys=all_keys)
        result: set[CompiledObjectKey] = set(
            _find_path_keys(start=start_key, end=end_key, downstream=downstream)
        )
        if parsed.upstream:
            result.update(_walk_all(key=start_key, deps=upstream))
        if parsed.downstream:
            result.update(_walk_all(key=end_key, deps=downstream))
        return frozenset(result)
    if parsed.kind == "tag":
        matched_keys: frozenset[CompiledObjectKey] = tag_index.get(parsed.value, frozenset())
        if not matched_keys:
            raise CliUserError(f"no models found with tag '{parsed.value}'", code="C310")
        return _apply_selector_expansion(
            matched_keys=matched_keys, parsed=parsed, upstream=upstream, downstream=downstream
        )
    if parsed.kind == "path":
        matched_keys = _match_path(folder=parsed.value, path_index=path_index)
        if not matched_keys:
            raise CliUserError(f"no models found under path '{parsed.value}'", code="C311")
        return _apply_selector_expansion(
            matched_keys=matched_keys, parsed=parsed, upstream=upstream, downstream=downstream
        )
    key: CompiledObjectKey = _lookup_parsed_selector(parsed=parsed, all_keys=all_keys)
    return _apply_selector_expansion(
        matched_keys=frozenset({key}), parsed=parsed, upstream=upstream, downstream=downstream
    )


def _apply_selector_expansion(
    *,
    matched_keys: frozenset[CompiledObjectKey],
    parsed: ParsedLineageSelector,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    result: set[CompiledObjectKey] = set(matched_keys)
    for key in matched_keys:
        if parsed.upstream:
            result.update(_walk_all(key=key, deps=upstream))
        if parsed.downstream:
            result.update(_walk_all(key=key, deps=downstream))
    return frozenset(result)


def _parse_selector(raw: str) -> ParsedLineageSelector | ParsedLineagePathSelector:
    stripped: str = raw.strip()
    if not stripped:
        raise CliUserError("empty selector", code="C312")
    upstream: bool = stripped.startswith("+")
    downstream: bool = stripped.endswith("+")
    core: str = stripped.lstrip("+").rstrip("+")
    if "~" in core:
        start_name, end_name = (part.strip() for part in core.split("~", 1))
        if not start_name or not end_name:
            raise CliUserError(
                f"path selector '{stripped}' requires names on both sides of '~'",
                code="C313",
            )
        return ParsedLineagePathSelector(
            start_name=start_name,
            end_name=end_name,
            upstream=upstream,
            downstream=downstream,
        )
    if not core:
        raise CliUserError(
            f"selector '{stripped}' has no name after removing '+' markers",
            code="C314",
        )
    if ":" in core:
        prefix, value = core.split(":", 1)
        if prefix not in {"seed", "source", "tag", "path"}:
            raise CliUserError(f"unknown selector type '{prefix}' in '{stripped}'", code="C315")
        if not value:
            raise CliUserError(f"selector '{stripped}' has empty value after ':'", code="C316")
        return ParsedLineageSelector(
            kind=prefix,
            value=value,
            upstream=upstream,
            downstream=downstream,
        )
    if "/" in core:
        return ParsedLineageSelector(
            kind="path",
            value=core.strip("/"),
            upstream=upstream,
            downstream=downstream,
        )
    return ParsedLineageSelector(
        kind="name",
        value=core,
        upstream=upstream,
        downstream=downstream,
    )


def _lookup_parsed_selector(
    *,
    parsed: ParsedLineageSelector,
    all_keys: dict[str, CompiledObjectKey],
) -> CompiledObjectKey:
    key: CompiledObjectKey | None = all_keys.get(parsed.value)
    if key is None:
        raise CliUserError(f"unknown lineage target '{parsed.value}'", code="C305")
    if parsed.kind == "source" and key.resource_type != CompiledResourceType.SOURCE:
        raise CliUserError(f"unknown lineage source '{parsed.value}'", code="C317")
    if parsed.kind == "seed" and key.resource_type != CompiledResourceType.SEED:
        raise CliUserError(f"unknown lineage seed '{parsed.value}'", code="C318")
    return key


def _find_path_keys(
    *,
    start: CompiledObjectKey,
    end: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    reachable_from_start: frozenset[CompiledObjectKey] = _walk_all(key=start, deps=downstream)
    if end not in reachable_from_start:
        raise CliUserError(
            f"'{end.resource_type}:{end.name}' is not downstream of "
            f"'{start.resource_type}:{start.name}'",
            code="C319",
        )
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    for key, dep_keys in downstream.items():
        for dep_key in dep_keys:
            upstream.setdefault(dep_key, []).append(key)
    upstream_from_end: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [end]
    while stack:
        current: CompiledObjectKey = stack.pop()
        if current in upstream_from_end:
            continue
        upstream_from_end.add(current)
        for parent in upstream.get(current, ()):
            if parent in reachable_from_start or parent == start:
                stack.append(parent)
    return frozenset(reachable_from_start & upstream_from_end | {start, end})


def _match_path(
    *,
    folder: str,
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    prefix: str = folder + "/"
    return frozenset(
        key
        for key, model_folder in path_index.items()
        if model_folder == folder or model_folder.startswith(prefix)
    )


def _build_node(*, project: CompiledProject, key: CompiledObjectKey) -> LineageNode:
    for model in project.models:
        if model.key == key:
            return LineageNode(
                key=key,
                relative_path=str(model.relative_path),
                qualified_name=model.destination.qualified_name,
            )
    for seed in project.seeds:
        if seed.key == key:
            return LineageNode(
                key=key,
                relative_path=str(seed.seed_file.relative_path),
                qualified_name=seed.destination.qualified_name,
            )
    for source in project.sources:
        if source.key == key:
            return LineageNode(
                key=key,
                relative_path=str(source.source_file.relative_path),
                qualified_name=_source_relation_name(source.source_entry),
            )
    return LineageNode(key=key)


def _source_relation_name(source: object) -> str | None:
    database: str | None = getattr(source, "database", None)
    schema: str | None = getattr(source, "schema", None)
    table: str | None = getattr(source, "table", None)
    if table is None:
        return None
    if database is not None and schema is not None:
        return f"{database}.{schema}.{table}"
    if schema is not None:
        return f"{schema}.{table}"
    return table


def _sort_key(key: CompiledObjectKey) -> tuple[str, str]:
    return (str(key.resource_type), key.name)
