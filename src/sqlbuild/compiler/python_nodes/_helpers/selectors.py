"""Selector helpers for executable Python DAG nodes."""

from __future__ import annotations

from fnmatch import fnmatchcase

from sqlbuild.compiler.graph.main.transitive_closure_many import transitive_closure_many
from sqlbuild.compiler.planner.constants import PATH_SELECTOR_EXPLICIT_ROOT_ERROR
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selector_parse import parse_project_selector
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind
from sqlbuild.compiler.python_nodes.constants import (
    EMPTY_SELECTOR_FOLDER,
    UNIFIED_PATH_ROOTS,
)
from sqlbuild.compiler.python_nodes.models import DiscoveredPythonNode, PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind

_PYTHON_NODE_KIND_BY_SELECTOR_KIND: dict[SelectorKind, PythonNodeKind] = {
    SelectorKind.TASK: PythonNodeKind.TASK,
    SelectorKind.ASSET: PythonNodeKind.ASSET,
    SelectorKind.LOADER: PythonNodeKind.LOADER,
    SelectorKind.CHECK: PythonNodeKind.CHECK,
}


def resolve_python_node_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    graph: PythonNodeGraph,
) -> frozenset[str]:
    """Resolve raw selectors into Python-node names."""

    if not select:
        return frozenset(graph.nodes_by_name)

    selected: set[str] = set()
    raw_select: str
    for raw_select in select:
        token: str
        for token in raw_select.split():
            selected.update(_resolve_token(token=token, graph=graph))

    excluded: set[str] = set()
    raw_exclude: str
    for raw_exclude in exclude:
        token: str
        for token in raw_exclude.split():
            excluded.update(_resolve_token(token=token, graph=graph))

    return frozenset(selected - excluded)


def _resolve_token(*, token: str, graph: PythonNodeGraph) -> frozenset[str]:
    parts: list[str] = token.split(",")
    if len(parts) == 1:
        return _resolve_single(raw=parts[0], graph=graph)

    sets: list[frozenset[str]] = [_resolve_single(raw=part, graph=graph) for part in parts]
    result: frozenset[str] = sets[0]
    subsequent: frozenset[str]
    for subsequent in sets[1:]:
        result = result & subsequent
    return result


def _resolve_single(*, raw: str, graph: PythonNodeGraph) -> frozenset[str]:
    parsed: ParsedSelector | PathSelector = parse_project_selector(raw)
    if isinstance(parsed, PathSelector):
        raise PlannerInputError(
            f"path-between selector '{raw}' is not supported for Python nodes yet",
            code="S011",
        )

    if parsed.kind == SelectorKind.TAG:
        return _resolve_tag(parsed=parsed, graph=graph)

    if parsed.kind == SelectorKind.PATH:
        return _resolve_path(parsed=parsed, graph=graph)

    node_names: frozenset[str] = _lookup_node_names(parsed=parsed, graph=graph)
    if not node_names:
        raise PlannerInputError(f"unknown Python node selector '{parsed.value}'", code="S007")

    return _expand_selected(names=node_names, parsed=parsed, graph=graph)


def _resolve_path(*, parsed: ParsedSelector, graph: PythonNodeGraph) -> frozenset[str]:
    folder: str = parsed.value.replace("\\", "/").strip("/")
    _validate_python_path_root(folder)
    matched_names: frozenset[str] = frozenset(
        name
        for name, node_folder in graph.path_index.items()
        if _path_matches(indexed_folder=node_folder, selector_folder=folder)
    )
    if not matched_names:
        raise PlannerInputError(f"no Python nodes found under path '{folder}'", code="S009")

    return _expand_selected(names=matched_names, parsed=parsed, graph=graph)


def _path_matches(*, indexed_folder: str, selector_folder: str) -> bool:
    if selector_folder == EMPTY_SELECTOR_FOLDER:
        return True
    return indexed_folder == selector_folder or indexed_folder.startswith(f"{selector_folder}/")


def _validate_python_path_root(folder: str) -> None:
    root: str = folder.split("/", 1)[0]
    if root in UNIFIED_PATH_ROOTS:
        return
    raise PlannerInputError(
        PATH_SELECTOR_EXPLICIT_ROOT_ERROR,
        code="S012",
    )


def _resolve_tag(*, parsed: ParsedSelector, graph: PythonNodeGraph) -> frozenset[str]:
    tagged_names: frozenset[str] = graph.tag_index.get(parsed.value, frozenset())
    if not tagged_names:
        raise PlannerInputError(f"no Python nodes found with tag '{parsed.value}'", code="S008")

    return _expand_selected(names=tagged_names, parsed=parsed, graph=graph)


def _lookup_node_names(*, parsed: ParsedSelector, graph: PythonNodeGraph) -> frozenset[str]:
    if parsed.kind == SelectorKind.NAME:
        if not _is_name_pattern(parsed.value):
            node: DiscoveredPythonNode | None = graph.nodes_by_name.get(parsed.value)
            return frozenset() if node is None else frozenset((node.name,))
        return frozenset(
            node.name
            for name, node in graph.nodes_by_name.items()
            if fnmatchcase(name, parsed.value)
        )

    python_node_kind: PythonNodeKind | None = _PYTHON_NODE_KIND_BY_SELECTOR_KIND.get(parsed.kind)
    if python_node_kind is None:
        raise PlannerInputError(
            f"selector type '{parsed.kind}' does not map to a Python node type",
            code="S010",
        )

    if not _is_name_pattern(parsed.value):
        node = graph.nodes_by_typed_selector.get(f"{python_node_kind.value}:{parsed.value}")
        return frozenset() if node is None else frozenset((node.name,))
    return frozenset(
        node.name
        for node in graph.nodes_by_name.values()
        if node.kind == python_node_kind and fnmatchcase(node.name, parsed.value)
    )


def _is_name_pattern(value: str) -> bool:
    return any(character in value for character in "*?[")


def _expand_selected(
    *, names: frozenset[str], parsed: ParsedSelector, graph: PythonNodeGraph
) -> frozenset[str]:
    result: set[str] = set(names)
    if parsed.upstream:
        result.update(
            transitive_closure_many(starts=names, edges=graph.upstream_deps, include_starts=False)
        )
    if parsed.downstream:
        result.update(
            transitive_closure_many(starts=names, edges=graph.downstream_deps, include_starts=False)
        )
    return frozenset(result)
