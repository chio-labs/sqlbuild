"""Static DAG artifact construction helpers."""

from __future__ import annotations

import json
from dataclasses import asdict

from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
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
    DagEdge,
    DagFunctionArgument,
    DagNode,
    DagTarget,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry

_DAG_VERSION: int = 1


def build_dag_artifact(*, graph: ProjectGraph, project_name: str) -> DagArtifact:
    """Build a static DAG artifact from a compiled project graph."""

    nodes: tuple[DagNode, ...] = (
        *(_build_source_node(source) for source in graph.project.sources),
        *(_build_seed_node(seed) for seed in graph.project.seeds),
        *(_build_function_node(function) for function in graph.project.functions),
        *(_build_model_node(model) for model in graph.project.models),
    )
    return DagArtifact(
        version=_DAG_VERSION,
        project_name=project_name,
        nodes=nodes,
        edges=_build_edges(graph),
        checks=_build_checks(graph),
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


def _build_seed_node(seed: CompiledSeed) -> DagNode:
    return DagNode(
        id=_node_id(seed.key),
        kind=CompiledResourceType.SEED.value,
        name=seed.name,
        asset_key=_target_asset_key(seed.target),
        target=_dag_target(seed.target),
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
        asset_key=_target_asset_key(function.target),
        target=_dag_target(function.target),
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
        asset_key=_target_asset_key(model.target),
        target=_dag_target(model.target),
        path=str(model.relative_path),
        description=(model.schema_entry.description if model.schema_entry is not None else None),
        tags=_model_tags(model),
        meta=(model.schema_entry.meta if model.schema_entry is not None else {}),
        columns=_model_columns(model),
        materialization_type=str(model.config.values.get("materialized", "view")),
    )


def _build_edges(graph: ProjectGraph) -> tuple[DagEdge, ...]:
    edges: list[DagEdge] = []
    key: CompiledObjectKey
    dep_keys: tuple[CompiledObjectKey, ...]
    for key, dep_keys in graph.upstream_deps.items():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            edges.append(DagEdge(from_id=_node_id(dep_key), to_id=_node_id(key)))
    return tuple(sorted(edges, key=lambda edge: (edge.from_id, edge.to_id)))


def _build_checks(graph: ProjectGraph) -> tuple[DagCheck, ...]:
    checks: list[DagCheck] = []
    checks.extend(_build_sql_test_check(test) for test in graph.project.sql_tests)
    checks.extend(_build_audit_check(audit) for audit in graph.project.audits)
    checks.extend(_build_scenario_check(scenario) for scenario in graph.project.sql_scenarios)
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


def _dag_target(target: CompiledRelationTarget) -> DagTarget:
    return DagTarget(
        database=target.database,
        schema=target.schema,
        name=target.name,
        qualified_name=target.qualified_name,
        logical_database=target.logical_database,
        logical_schema=target.logical_schema,
    )


def _target_asset_key(target: CompiledRelationTarget) -> tuple[str, ...]:
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
