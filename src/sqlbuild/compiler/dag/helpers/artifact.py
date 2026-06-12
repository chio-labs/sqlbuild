"""Static DAG artifact construction helpers."""

from __future__ import annotations

import json
from dataclasses import asdict

from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.models.sql_tests import CompiledSqlTest
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.compiler.dag.models import (
    DagArtifact,
    DagCheck,
    DagColumn,
    DagColumnLineageRef,
    DagEdge,
    DagFunctionArgument,
    DagNode,
    DagTarget,
)
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.models import DiscoveredPythonNode, PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.shared.models import ColumnLineageRef, SqlResourceRef
from sqlbuild.shared.types import SqlResourceRefKind
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry

_DAG_VERSION: int = 1


def build_dag_artifact(
    *, graph: ProjectGraph, project_name: str, python_graph: PythonNodeGraph | None = None
) -> DagArtifact:
    """Build a static DAG artifact from a compiled project graph."""

    nodes: tuple[DagNode, ...] = (
        *(_build_source_node(source) for source in graph.project.sources),
        *(
            _build_loader_node(graph.project, loader, source_by_loader=_source_by_loader(graph))
            for loader in graph.project.loader_functions
            if loader.name not in _source_by_loader(graph)
        ),
        *(_build_seed_node(seed) for seed in graph.project.seeds),
        *(_build_function_node(function) for function in graph.project.functions),
        *(_build_model_node(model) for model in graph.project.models),
        *(_build_python_nodes(python_graph) if python_graph is not None else ()),
    )
    return DagArtifact(
        version=_DAG_VERSION,
        project_name=project_name,
        nodes=nodes,
        edges=_build_edges(graph, python_graph=python_graph),
        checks=_build_checks(graph, python_graph=python_graph),
    )


def format_dag_json(*, artifact: DagArtifact) -> str:
    """Serialize the static DAG artifact to JSON."""

    return json.dumps(_drop_none(asdict(artifact)), indent=2)


def _build_source_node(source: CompiledSource) -> DagNode:
    entry: SourceEntry = source.source_entry
    target: DagTarget = DagTarget(
        database=entry.database,
        schema=entry.schema,
        name=entry.table or entry.name,
        qualified_name=_qualified_name(entry.database, entry.schema, entry.table or entry.name),
    )
    return DagNode(
        id=_node_id(source.key),
        kind=CompiledResourceType.SOURCE.value,
        name=source.name,
        asset_key=_source_asset_key(entry),
        target=target,
        path=str(source.source_file.relative_path),
        description=entry.description,
        meta=entry.meta,
        columns=tuple(_source_column(column) for column in entry.columns),
    )


def _build_loader_node(
    project: CompiledProject,
    loader: DiscoveredLoaderFunction,
    *,
    source_by_loader: dict[str, SourceEntry],
) -> DagNode:
    entry: SourceEntry = source_by_loader.get(loader.name) or _loader_to_source_entry(
        project=project, loader=loader
    )
    target: DagTarget = DagTarget(
        database=entry.database,
        schema=entry.schema,
        name=entry.table or entry.name,
        qualified_name=_qualified_name(entry.database, entry.schema, entry.table or entry.name),
    )
    return DagNode(
        id=_loader_node_id(loader.name),
        kind="loader",
        name=loader.name,
        asset_key=(loader.name,),
        target=target,
        path=str(loader.relative_path),
        meta=entry.meta,
        columns=tuple(_source_column(column) for column in entry.columns),
        loader=loader.name,
    )


def _build_python_nodes(python_graph: PythonNodeGraph) -> tuple[DagNode, ...]:
    return tuple(
        _build_python_node(node)
        for node in python_graph.nodes
        if node.kind != PythonNodeKind.LOADER
    )


def _build_python_node(node: DiscoveredPythonNode) -> DagNode:
    columns: tuple[DagColumn, ...] = ()
    column_lineage: dict[str, tuple[DagColumnLineageRef, ...]] = {}
    materialization_type: str | None = None
    if node.kind == PythonNodeKind.ASSET and node.asset is not None:
        columns = tuple(_source_column(column) for column in node.asset.columns)
        column_lineage = _python_column_lineage(node.asset.column_lineage)
        materialization_type = "python_asset"
    return DagNode(
        id=_python_node_id(node.kind, node.name),
        kind=node.kind.value,
        name=node.name,
        asset_key=(node.kind.value, node.name),
        path=str(node.relative_path),
        description=node.description,
        tags=node.tags,
        group=node.group,
        meta=node.meta or {},
        columns=columns,
        column_lineage=column_lineage,
        materialization_type=materialization_type,
    )


def _build_seed_node(seed: CompiledSeed) -> DagNode:
    return DagNode(
        id=_node_id(seed.key),
        kind=CompiledResourceType.SEED.value,
        name=seed.name,
        asset_key=_target_asset_key(seed.destination),
        target=_dag_target(seed.destination),
        path=str(seed.seed_file.relative_path),
        description=seed.schema_entry.description,
        meta=seed.schema_entry.meta,
        columns=tuple(_schema_column(column) for column in seed.schema_entry.columns),
    )


def _build_function_node(function: CompiledFunction) -> DagNode:
    return DagNode(
        id=_node_id(function.key),
        kind=CompiledResourceType.FUNCTION.value,
        name=function.name,
        asset_key=_target_asset_key(function.destination),
        target=_dag_target(function.destination),
        path=str(function.relative_path),
        language=function.language.value,
        return_kind="table" if function.return_columns else "scalar",
        returns=function.returns,
        columns=tuple(
            DagColumn(name=column.name, type=column.type) for column in function.return_columns
        ),
        arguments=tuple(
            DagFunctionArgument(name=argument.name, type=argument.type)
            for argument in function.arguments
        ),
    )


def _build_model_node(model: CompiledModel) -> DagNode:
    return DagNode(
        id=_node_id(model.key),
        kind=CompiledResourceType.MODEL.value,
        name=model.name,
        asset_key=_target_asset_key(model.destination),
        target=_dag_target(model.destination),
        path=str(model.relative_path),
        description=(model.schema_entry.description if model.schema_entry is not None else None),
        tags=_model_tags(model),
        meta=(model.schema_entry.meta if model.schema_entry is not None else {}),
        columns=_model_columns(model),
        materialization_type=str(model.config.values.get("materialized", "view")),
    )


def _build_edges(
    graph: ProjectGraph, *, python_graph: PythonNodeGraph | None = None
) -> tuple[DagEdge, ...]:
    edges: list[DagEdge] = []
    key: CompiledObjectKey
    dep_keys: tuple[CompiledObjectKey, ...]
    for key, dep_keys in graph.upstream_deps.items():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            edges.append(DagEdge(from_id=_node_id(dep_key), to_id=_node_id(key)))
    edges.extend(_build_loader_edges(graph))
    if python_graph is not None:
        edges.extend(_build_python_edges(python_graph))
    return tuple(sorted(edges, key=lambda edge: (edge.from_id, edge.to_id)))


def _build_loader_edges(graph: ProjectGraph) -> tuple[DagEdge, ...]:
    source_by_loader: dict[str, SourceEntry] = _source_by_loader(graph)
    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in graph.project.loader_functions
    }
    edges: list[DagEdge] = []
    loader: DiscoveredLoaderFunction
    for loader in graph.project.loader_functions:
        for dependency in loader.depends_on:
            dependency_name: str | None = loader_name_by_function.get(dependency)
            if dependency_name is None:
                continue
            edges.append(
                DagEdge(
                    from_id=_loader_or_source_node_id(
                        loader_name=dependency_name, source_by_loader=source_by_loader
                    ),
                    to_id=_loader_or_source_node_id(
                        loader_name=loader.name, source_by_loader=source_by_loader
                    ),
                )
            )
    return tuple(edges)


def _loader_or_source_node_id(*, loader_name: str, source_by_loader: dict[str, SourceEntry]) -> str:
    source_entry: SourceEntry | None = source_by_loader.get(loader_name)
    if source_entry is not None:
        return _node_id(CompiledObjectKey(CompiledResourceType.SOURCE, source_entry.name))
    return _loader_node_id(loader_name)


def _build_python_edges(python_graph: PythonNodeGraph) -> tuple[DagEdge, ...]:
    edges: list[DagEdge] = []
    for edge in python_graph.dependency_edges:
        upstream_node: DiscoveredPythonNode = python_graph.nodes_by_name[edge.upstream_name]
        downstream_node: DiscoveredPythonNode = python_graph.nodes_by_name[edge.downstream_name]
        edges.append(
            DagEdge(
                from_id=_python_node_id(upstream_node.kind, upstream_node.name),
                to_id=_python_node_id(downstream_node.kind, downstream_node.name),
            )
        )
    for node in python_graph.nodes:
        for sql_dep in node.sql_deps:
            edges.append(
                DagEdge(
                    from_id=_sql_ref_node_id(sql_dep),
                    to_id=_python_node_id(node.kind, node.name),
                )
            )
    return tuple(edges)


def _build_checks(
    graph: ProjectGraph, *, python_graph: PythonNodeGraph | None = None
) -> tuple[DagCheck, ...]:
    checks: list[DagCheck] = []
    checks.extend(_build_sql_test_check(test) for test in graph.project.sql_tests)
    checks.extend(_build_audit_check(audit) for audit in graph.project.audits)
    checks.extend(_build_scenario_check(scenario) for scenario in graph.project.sql_scenarios)
    if python_graph is not None:
        checks.extend(
            _build_python_check(node, python_graph=python_graph)
            for node in python_graph.nodes
            if node.kind == PythonNodeKind.CHECK
        )
    return tuple(sorted(checks, key=lambda check: (check.kind, check.name)))


def _build_sql_test_check(test: CompiledSqlTest) -> DagCheck:
    return DagCheck(
        id=_node_id(test.key),
        kind="sql_test",
        name=test.name,
        checked_asset_ids=tuple(_node_id(key) for key in test.scope_deps),
        path=str(test.test_file.relative_path),
        mode=test.mode.value,
    )


def _build_audit_check(audit: CompiledAudit) -> DagCheck:
    checked_asset_ids: tuple[str, ...] = tuple(_node_id(key) for key in audit.scope_deps)
    if audit.attached_target_kind is not None and audit.attached_target_name is not None:
        resource_type: CompiledResourceType = (
            CompiledResourceType.SOURCE
            if audit.attached_target_kind == AttachedAuditTargetKind.SOURCE
            else CompiledResourceType.MODEL
        )
        checked_asset_ids = (
            _node_id(CompiledObjectKey(resource_type, audit.attached_target_name)),
        )
    return DagCheck(
        id=_audit_check_id(audit),
        kind="audit",
        name=audit.name,
        checked_asset_ids=checked_asset_ids,
        path=str(audit.audit_file.relative_path),
        severity=audit.severity,
        attachment_kind=(
            audit.attached_target_kind.value if audit.attached_target_kind is not None else None
        ),
        attached_target_name=audit.attached_target_name,
        attached_column_name=audit.attached_column_name,
    )


def _audit_check_id(audit: CompiledAudit) -> str:
    parts: tuple[str | None, ...] = (
        _node_id(audit.key),
        audit.attached_target_kind.value if audit.attached_target_kind is not None else None,
        audit.attached_target_name,
        audit.attached_column_name,
    )
    return ":".join(part for part in parts if part)


def _build_scenario_check(scenario: CompiledSqlScenario) -> DagCheck:
    target_keys: tuple[CompiledObjectKey, ...] = tuple(
        CompiledObjectKey(CompiledResourceType.MODEL, name)
        for name in scenario.expected_model_names
    )
    graph_asset_ids: tuple[str, ...] = tuple(
        _node_id(CompiledObjectKey(CompiledResourceType.MODEL, cte.name))
        for cte in scenario.authored_ctes
    )
    return DagCheck(
        id=_node_id(scenario.key),
        kind="scenario",
        name=scenario.name,
        checked_asset_ids=tuple(_node_id(key) for key in target_keys),
        path=str(scenario.scenario_file.relative_path),
        assertion_names=scenario.assertion_names,
        expected_model_names=scenario.expected_model_names,
        graph_asset_ids=graph_asset_ids,
        fixture_refs=(
            *scenario.source_fixture_names,
            *scenario.ref_fixture_names,
            *scenario.seed_fixture_names,
            *scenario.dbt_ref_fixture_names,
        ),
    )


def _build_python_check(node: DiscoveredPythonNode, *, python_graph: PythonNodeGraph) -> DagCheck:
    checked_asset_ids: tuple[str, ...] = tuple(
        _python_node_id(python_graph.nodes_by_name[edge.upstream_name].kind, edge.upstream_name)
        for edge in python_graph.dependency_edges
        if edge.downstream_name == node.name
    )
    return DagCheck(
        id=_python_node_id(node.kind, node.name),
        kind="python_check",
        name=node.name,
        checked_asset_ids=checked_asset_ids,
        path=str(node.relative_path),
        description=node.description,
        severity=(node.check.severity.value if node.check is not None else None),
        tags=node.tags,
        group=node.group,
        meta=node.meta or {},
    )


def _dag_target(target: CompiledRelationLocation) -> DagTarget:
    return DagTarget(
        database=target.database,
        schema=target.schema,
        name=target.name,
        qualified_name=target.qualified_name,
        logical_database=target.logical_database,
        logical_schema=target.logical_schema,
    )


def _target_asset_key(target: CompiledRelationLocation) -> tuple[str, ...]:
    return tuple(
        part
        for part in (
            target.logical_database or target.database,
            target.logical_schema or target.schema,
            target.name,
        )
        if part
    )


def _source_asset_key(entry: SourceEntry) -> tuple[str, ...]:
    parts: tuple[str | None, ...] = (entry.database, entry.schema, entry.table or entry.name)
    return tuple(part for part in parts if part) or (entry.name,)


def _node_id(key: CompiledObjectKey) -> str:
    return f"{key.resource_type}:{key.name}"


def _loader_node_id(loader_name: str) -> str:
    return f"loader:{loader_name}"


def _python_node_id(kind: PythonNodeKind, node_name: str) -> str:
    if kind == PythonNodeKind.LOADER:
        return _loader_node_id(node_name)
    return f"{kind.value}:{node_name}"


def _sql_ref_node_id(ref: SqlResourceRef) -> str:
    resource_type: CompiledResourceType = (
        CompiledResourceType.MODEL
        if ref.kind == SqlResourceRefKind.MODEL
        else CompiledResourceType.SOURCE
    )
    return _node_id(CompiledObjectKey(resource_type, ref.name))


def _source_by_loader(graph: ProjectGraph) -> dict[str, SourceEntry]:
    return {
        source.source_entry.loader: source.source_entry
        for source in graph.project.sources
        if source.source_entry.loader is not None
    }


def _loader_to_source_entry(
    *, project: CompiledProject, loader: DiscoveredLoaderFunction
) -> SourceEntry:
    database: str | None = project.effective_target_database
    schema: str | None = project.effective_target_schema
    table: str = f"__loader__{loader.name}"
    if loader.destination is not None:
        parts: tuple[str, ...] = tuple(part for part in loader.destination.split(".") if part)
        if len(parts) == 1:
            table = parts[0]
        elif len(parts) == 2:
            schema, table = parts
        elif len(parts) == 3:
            database, schema, table = parts
        else:
            table = loader.destination
    return SourceEntry(
        name=loader.name,
        database=database,
        schema=schema,
        table=table,
        loader=loader.name,
        write_strategy=loader.write_strategy,
        cursor_column=loader.cursor_column,
        unique_key=loader.unique_key,
        contract=loader.contract,
        meta={"sqlbuild_loader_node": True},
        columns=loader.columns,
    )


def _schema_column(column: SchemaColumn) -> DagColumn:
    return DagColumn(
        name=column.name,
        type=column.type,
        nullable=column.nullable,
        description=column.description,
        meta=column.meta,
    )


def _source_column(column: SourceColumnEntry) -> DagColumn:
    return DagColumn(
        name=column.name,
        type=column.type,
        nullable=column.nullable,
        description=column.description,
        meta=column.meta,
    )


def _model_columns(model: CompiledModel) -> tuple[DagColumn, ...]:
    if model.schema_entry is not None and model.schema_entry.columns:
        return tuple(_schema_column(column) for column in model.schema_entry.columns)
    if model.inferred_columns is not None:
        return tuple(
            DagColumn(name=column.name, type=column.type) for column in model.inferred_columns
        )
    return ()


def _model_tags(model: CompiledModel) -> tuple[str, ...]:
    schema_tags: tuple[str, ...] = ()
    if model.schema_entry is not None:
        schema_tags = model.schema_entry.tags
    config_tags: object = model.config.values.get("tags", ())
    if isinstance(config_tags, (list, tuple)):
        return tuple(dict.fromkeys((*schema_tags, *(str(tag) for tag in config_tags))))
    return schema_tags


def _python_column_lineage(
    lineage: dict[str, tuple[ColumnLineageRef, ...]] | None,
) -> dict[str, tuple[DagColumnLineageRef, ...]]:
    if lineage is None:
        return {}
    return {
        column: tuple(DagColumnLineageRef(node=ref.node, column=ref.column) for ref in refs)
        for column, refs in lineage.items()
    }


def _qualified_name(database: str | None, schema: str | None, name: str) -> str:
    return ".".join(part for part in (database, schema, name) if part)


def _drop_none(value: object) -> object:
    if isinstance(value, dict):
        result: dict[object, object] = {}
        for key, item in value.items():
            if item is None:
                continue
            cleaned: object = _drop_none(item)
            if _is_empty_optional_field(key=key, value=cleaned):
                continue
            result[key] = cleaned
        return result
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, tuple):
        return [_drop_none(item) for item in value]
    return value


def _is_empty_optional_field(*, key: object, value: object) -> bool:
    if key in {"nodes", "edges", "checks"}:
        return False
    return value in ({}, [])
