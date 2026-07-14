"""Unified selector helpers for SQL resources and executable Python nodes."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.constants import PATH_SELECTOR_EXPLICIT_ROOT_ERROR
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.build_resources import expand_build_resource_selection
from sqlbuild.compiler.planner.main.planning.selection import resolve_project_selectors
from sqlbuild.compiler.planner.main.planning.selector_parse import parse_project_selector
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind
from sqlbuild.compiler.python_nodes.constants import (
    PYTHON_NODE_PATH_ROOTS,
    SQL_MODEL_PATH_ROOT,
    TAG_NOT_FOUND_ERROR_CODE,
)
from sqlbuild.compiler.python_nodes.helpers.selectors import resolve_python_node_selectors
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.python_nodes.types import SqlResourceRefKind

_PYTHON_SELECTOR_KINDS: frozenset[SelectorKind] = frozenset(
    {
        SelectorKind.TASK,
        SelectorKind.ASSET,
        SelectorKind.LOADER,
        SelectorKind.CHECK,
    }
)
_SQL_SELECTOR_KINDS: frozenset[SelectorKind] = frozenset(
    {
        SelectorKind.SEED,
        SelectorKind.SOURCE,
        SelectorKind.PATH,
    }
)
_ALLOWED_SQL_MODEL_DEP_RESOURCE_TYPES: frozenset[CompiledResourceType] = frozenset(
    {
        CompiledResourceType.MODEL,
        CompiledResourceType.SOURCE,
        CompiledResourceType.SEED,
        CompiledResourceType.UDF,
        CompiledResourceType.TABLE_FN,
        CompiledResourceType.DBT_REF,
    }
)


@dataclass(frozen=True)
class _SelectionAtom:
    kind: str
    value: CompiledObjectKey | str


def resolve_python_sql_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
    validate_dependencies: bool = True,
) -> PythonSqlSelection:
    """Resolve selectors across compiled SQL resources and executable Python nodes."""

    validate_python_sql_boundaries(project_graph=project_graph, python_graph=python_graph)

    selected: set[_SelectionAtom]
    if select:
        selected = _resolve_selector_groups(
            raw_groups=select,
            project_graph=project_graph,
            python_graph=python_graph,
        )
    else:
        selected = {
            *(_sql_atom(key) for key in project_graph.all_keys.values()),
            *(_python_atom(name) for name in python_graph.nodes_by_name),
        }

    excluded: set[_SelectionAtom] = _resolve_selector_groups(
        raw_groups=exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )
    selected -= excluded
    selected.update(
        _required_sql_resource_atoms(selected_atoms=selected, project_graph=project_graph)
    )
    if validate_dependencies:
        _validate_selected_dependencies(
            selected_atoms=selected, project_graph=project_graph, python_graph=python_graph
        )
    return _build_selection(selected)


def validate_python_sql_selection_dependencies(
    *,
    selection: PythonSqlSelection,
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> None:
    """Validate that a resolved SQL/Python selection contains required Python deps."""

    _validate_selected_dependencies(
        selected_atoms={
            *(_sql_atom(key) for key in selection.sql_keys),
            *(_python_atom(name) for name in selection.python_node_names),
        },
        project_graph=project_graph,
        python_graph=python_graph,
    )


def validate_python_sql_boundaries(
    *, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> None:
    """Validate SQL/Python graph boundary rules before unified selection/execution."""

    _validate_sql_model_dependencies(project_graph=project_graph)
    _validate_python_sql_refs(project_graph=project_graph, python_graph=python_graph)
    _validate_loader_upstream_python_is_pre_sql(python_graph=python_graph)
    terminal_loader_by_name: dict[str, str] = _terminal_loader_by_name(project_graph=project_graph)
    node: DiscoveredPythonNode
    for node in python_graph.nodes:
        dependency_name: str
        for dependency_name in python_graph.upstream_deps.get(node.name, ()):
            source_name: str | None = terminal_loader_by_name.get(dependency_name)
            if source_name is None:
                continue
            if node.kind == PythonNodeKind.CHECK:
                raise PlannerInputError(
                    f"Check '{node.name}' depends on terminal loader '{dependency_name}'; "
                    f"use source audits for source '{source_name}' instead"
                )
            if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
                raise PlannerInputError(
                    f"Python node '{node.name}' depends on terminal loader '{dependency_name}'; "
                    f"depend on source '{source_name}' instead"
                )


def _validate_loader_upstream_python_is_pre_sql(*, python_graph: PythonNodeGraph) -> None:
    node: DiscoveredPythonNode
    for node in python_graph.nodes:
        if node.kind != PythonNodeKind.LOADER:
            continue
        upstream_name: str
        for upstream_name in _upstream_python_closure(
            node_name=node.name, python_graph=python_graph
        ):
            upstream_node: DiscoveredPythonNode = python_graph.nodes_by_name[upstream_name]
            if upstream_node.kind not in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
                continue
            if upstream_node.sql_deps:
                raise PlannerInputError(
                    f"Loader '{node.name}' depends on Python node '{upstream_node.name}' "
                    "which depends on SQL; Python-to-SQL writes must flow through a "
                    "pre-SQL task/asset -> loader -> source path"
                )


def _validate_python_sql_refs(
    *, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> None:
    node: DiscoveredPythonNode
    for node in python_graph.nodes:
        for sql_ref in node.sql_deps:
            sql_key: CompiledObjectKey | None = project_graph.all_keys.get(sql_ref.name)
            if sql_key is None:
                raise PlannerInputError(
                    f"Python node '{node.name}' depends on unknown SQL resource '{sql_ref.name}'"
                )
            if (
                sql_ref.kind == SqlResourceRefKind.MODEL
                and sql_key.resource_type != CompiledResourceType.MODEL
            ):
                raise PlannerInputError(
                    f"Python node '{node.name}' declares model('{sql_ref.name}') but "
                    f"'{sql_ref.name}' is a {sql_key.resource_type}"
                )
            if (
                sql_ref.kind == SqlResourceRefKind.SOURCE
                and sql_key.resource_type != CompiledResourceType.SOURCE
            ):
                raise PlannerInputError(
                    f"Python node '{node.name}' declares source('{sql_ref.name}') but "
                    f"'{sql_ref.name}' is a {sql_key.resource_type}"
                )


def _upstream_python_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)


def _validate_sql_model_dependencies(*, project_graph: ProjectGraph) -> None:
    source_names: frozenset[str] = frozenset(
        source.name for source in project_graph.project.sources
    )
    model_key: CompiledObjectKey
    for model_key, dependency_keys in project_graph.upstream_deps.items():
        if model_key.resource_type != CompiledResourceType.MODEL:
            continue
        dependency_key: CompiledObjectKey
        for dependency_key in dependency_keys:
            if dependency_key.resource_type not in _ALLOWED_SQL_MODEL_DEP_RESOURCE_TYPES:
                raise PlannerInputError(
                    f"SQL model '{model_key.name}' depends on non-SQL resource "
                    f"'{dependency_key.resource_type}:{dependency_key.name}'; SQL model "
                    "dependencies must stay SQL-only"
                )
            if (
                dependency_key.resource_type == CompiledResourceType.SOURCE
                and dependency_key.name not in source_names
            ):
                raise PlannerInputError(
                    f"SQL model '{model_key.name}' depends on intermediate loader "
                    f"'{dependency_key.name}'; depend on a source populated by a terminal "
                    "loader instead"
                )


def _resolve_selector_groups(
    *,
    raw_groups: tuple[str, ...],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> set[_SelectionAtom]:
    resolved: set[_SelectionAtom] = set()
    raw_group: str
    for raw_group in raw_groups:
        token: str
        for token in raw_group.split():
            resolved.update(
                _resolve_token(
                    token=token,
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
    return resolved


def _resolve_token(
    *, token: str, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> frozenset[_SelectionAtom]:
    parts: list[str] = token.split(",")
    if len(parts) == 1:
        return _resolve_single(raw=parts[0], project_graph=project_graph, python_graph=python_graph)

    resolved_parts: list[frozenset[_SelectionAtom]] = [
        _resolve_single(raw=part, project_graph=project_graph, python_graph=python_graph)
        for part in parts
    ]
    result: frozenset[_SelectionAtom] = resolved_parts[0]
    subsequent: frozenset[_SelectionAtom]
    for subsequent in resolved_parts[1:]:
        result = result & subsequent
    return result


def _resolve_single(
    *, raw: str, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> frozenset[_SelectionAtom]:
    parsed: ParsedSelector | PathSelector = parse_project_selector(raw)
    atoms: frozenset[_SelectionAtom]
    if isinstance(parsed, PathSelector):
        atoms = _resolve_sql(raw=raw, project_graph=project_graph)
        if parsed.upstream:
            atoms = atoms | frozenset(
                _required_terminal_loader_atoms(
                    selected_atoms=set(atoms),
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
        return atoms
    if parsed.kind == SelectorKind.PATH:
        atoms = _resolve_path(raw=raw, project_graph=project_graph, python_graph=python_graph)
        if parsed.upstream:
            atoms = atoms | frozenset(
                _required_terminal_loader_atoms(
                    selected_atoms=set(atoms),
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
        return atoms
    if parsed.kind in _SQL_SELECTOR_KINDS:
        atoms = _resolve_sql(raw=raw, project_graph=project_graph)
        if parsed.upstream:
            atoms = atoms | frozenset(
                _required_terminal_loader_atoms(
                    selected_atoms=set(atoms),
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
        return atoms
    if parsed.kind in _PYTHON_SELECTOR_KINDS:
        if parsed.kind == SelectorKind.LOADER and parsed.value in _terminal_loader_by_name(
            project_graph=project_graph
        ):
            raise PlannerInputError(
                f"'{parsed.value}' is a managed source; select it as source:{parsed.value}",
                code="S007",
            )
        return _resolve_python(raw=raw, python_graph=python_graph)
    if parsed.kind == SelectorKind.TAG:
        atoms = _resolve_tag(raw=raw, project_graph=project_graph, python_graph=python_graph)
        if parsed.upstream:
            atoms = atoms | frozenset(
                _required_terminal_loader_atoms(
                    selected_atoms=set(atoms),
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
        return atoms
    if parsed.kind == SelectorKind.NAME:
        atoms = _resolve_name(
            raw=raw, parsed=parsed, project_graph=project_graph, python_graph=python_graph
        )
        if parsed.upstream:
            atoms = atoms | frozenset(
                _required_terminal_loader_atoms(
                    selected_atoms=set(atoms),
                    project_graph=project_graph,
                    python_graph=python_graph,
                )
            )
        return atoms
    raise PlannerInputError(f"unsupported selector '{raw}'")


def _resolve_sql(*, raw: str, project_graph: ProjectGraph) -> frozenset[_SelectionAtom]:
    return frozenset(
        _sql_atom(key)
        for key in resolve_project_selectors(
            select=(raw,),
            exclude=(),
            all_keys=project_graph.all_keys,
            upstream_deps=project_graph.upstream_deps,
            downstream_deps=project_graph.downstream_deps,
            tag_index=project_graph.tag_index,
            path_index=project_graph.path_index,
        )
    )


def _resolve_python(*, raw: str, python_graph: PythonNodeGraph) -> frozenset[_SelectionAtom]:
    return frozenset(
        _python_atom(name)
        for name in resolve_python_node_selectors(select=(raw,), exclude=(), graph=python_graph)
    )


def _resolve_tag(
    *, raw: str, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> frozenset[_SelectionAtom]:
    atoms: set[_SelectionAtom] = set()
    try:
        atoms.update(_resolve_sql(raw=raw, project_graph=project_graph))
    except PlannerInputError as error:
        if error.code != TAG_NOT_FOUND_ERROR_CODE:
            raise
    try:
        atoms.update(_resolve_python(raw=raw, python_graph=python_graph))
    except PlannerInputError as error:
        if error.code != TAG_NOT_FOUND_ERROR_CODE:
            raise
    if not atoms:
        parsed: ParsedSelector | PathSelector = parse_project_selector(raw)
        tag_value: str = parsed.value if isinstance(parsed, ParsedSelector) else raw
        raise PlannerInputError(f"no SQL resources or Python nodes found with tag '{tag_value}'")
    return frozenset(atoms)


def _resolve_path(
    *, raw: str, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> frozenset[_SelectionAtom]:
    parsed: ParsedSelector | PathSelector = parse_project_selector(raw)
    if not isinstance(parsed, ParsedSelector):
        raise PlannerInputError(f"unsupported path selector '{raw}'")
    folder: str = parsed.value.replace("\\", "/").strip("/")
    root: str = folder.split("/", 1)[0]
    if root == SQL_MODEL_PATH_ROOT:
        return _resolve_sql(raw=raw, project_graph=project_graph)
    if root in PYTHON_NODE_PATH_ROOTS:
        return _resolve_python(raw=raw, python_graph=python_graph)
    raise PlannerInputError(
        PATH_SELECTOR_EXPLICIT_ROOT_ERROR,
        code="S012",
    )


def _resolve_name(
    *,
    raw: str,
    parsed: ParsedSelector,
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> frozenset[_SelectionAtom]:
    sql_key: CompiledObjectKey | None = project_graph.all_keys.get(parsed.value)
    python_exists: bool = parsed.value in python_graph.nodes_by_name
    terminal_loader_names: frozenset[str] = frozenset(
        _terminal_loader_by_name(project_graph=project_graph)
    )
    if sql_key is not None and parsed.value in terminal_loader_names:
        return _resolve_sql(raw=raw, project_graph=project_graph)
    if sql_key is not None and python_exists:
        raise PlannerInputError(
            f"selector name '{parsed.value}' matches both a SQL resource and a Python node; "
            "resource names must be globally unique"
        )
    if sql_key is not None:
        return _resolve_sql(raw=raw, project_graph=project_graph)
    if python_exists:
        return _resolve_python(raw=raw, python_graph=python_graph)
    raise PlannerInputError(f"unknown selector name '{parsed.value}'", code="S007")


def _build_selection(atoms: set[_SelectionAtom]) -> PythonSqlSelection:
    return PythonSqlSelection(
        sql_keys=frozenset(
            atom.value for atom in atoms if isinstance(atom.value, CompiledObjectKey)
        ),
        python_node_names=frozenset(atom.value for atom in atoms if isinstance(atom.value, str)),
    )


def _required_sql_resource_atoms(
    *, selected_atoms: set[_SelectionAtom], project_graph: ProjectGraph
) -> set[_SelectionAtom]:
    selected_sql_keys: frozenset[CompiledObjectKey] = frozenset(
        atom.value for atom in selected_atoms if isinstance(atom.value, CompiledObjectKey)
    )
    return {
        _sql_atom(key)
        for key in expand_build_resource_selection(
            selected_keys=selected_sql_keys,
            upstream=project_graph.upstream_deps,
            downstream=project_graph.downstream_deps,
            include_upstream_functions=True,
            include_upstream_seeds=False,
            include_downstream_functions=False,
        )
    }


def _required_terminal_loader_atoms(
    *,
    selected_atoms: set[_SelectionAtom],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> set[_SelectionAtom]:
    source_loader_by_name: dict[str, str] = _source_loader_by_name(project_graph=project_graph)
    required: set[_SelectionAtom] = set()
    atom: _SelectionAtom
    for atom in selected_atoms:
        if not isinstance(atom.value, CompiledObjectKey):
            continue
        if atom.value.resource_type != CompiledResourceType.SOURCE:
            continue
        loader_name: str | None = source_loader_by_name.get(atom.value.name)
        if loader_name is None:
            continue
        if loader_name == atom.value.name:
            if loader_name in python_graph.nodes_by_name:
                required.add(_python_atom(loader_name))
                required.update(
                    _python_atom(name)
                    for name in _python_upstream_closure(
                        node_name=loader_name,
                        python_graph=python_graph,
                    )
                )
            continue
        if loader_name in python_graph.nodes_by_name:
            required.add(_python_atom(loader_name))
            required.update(
                _python_atom(name)
                for name in _python_upstream_closure(
                    node_name=loader_name,
                    python_graph=python_graph,
                )
            )
    return required


def _validate_selected_dependencies(
    *,
    selected_atoms: set[_SelectionAtom],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> None:
    selected_python_names: frozenset[str] = frozenset(
        atom.value for atom in selected_atoms if isinstance(atom.value, str)
    )
    source_loader_by_name: dict[str, str] = _source_loader_by_name(project_graph=project_graph)
    atom: _SelectionAtom
    for atom in selected_atoms:
        if not isinstance(atom.value, CompiledObjectKey):
            continue
        if atom.value.resource_type != CompiledResourceType.SOURCE:
            continue
        loader_name: str | None = source_loader_by_name.get(atom.value.name)
        if loader_name is None or loader_name == atom.value.name:
            continue
        if loader_name in selected_python_names:
            continue
        raise PlannerInputError(
            f"Source '{atom.value.name}' requires loader '{loader_name}', but that loader was "
            "not selected; select it directly or use upstream expansion"
        )
    node_name: str
    for node_name in selected_python_names:
        upstream_name: str
        for upstream_name in python_graph.upstream_deps.get(node_name, ()):
            if upstream_name in selected_python_names:
                continue
            raise PlannerInputError(
                f"Python node '{node_name}' depends on unselected Python node "
                f"'{upstream_name}'; select it directly or use upstream expansion"
            )


def _python_upstream_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)


def _source_loader_by_name(*, project_graph: ProjectGraph) -> dict[str, str]:
    return {
        source.name: source.source_entry.loader
        for source in project_graph.project.sources
        if source.source_entry.loader is not None
    }


def _terminal_loader_by_name(*, project_graph: ProjectGraph) -> dict[str, str]:
    return {
        loader_name: source_name
        for source_name, loader_name in _source_loader_by_name(project_graph=project_graph).items()
    }


def _sql_atom(key: CompiledObjectKey) -> _SelectionAtom:
    return _SelectionAtom(kind="sql", value=key)


def _python_atom(name: str) -> _SelectionAtom:
    return _SelectionAtom(kind="python", value=name)
