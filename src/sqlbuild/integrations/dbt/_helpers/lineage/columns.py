"""Compiled-SQL column lineage helpers for mixed dbt/SQLBuild projects."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSource,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSourceFile
from sqlbuild.compiler.lineage.main.columns import build_project_column_lineage
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.integrations.dbt._helpers.graph.core import (
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt._helpers.lineage.selection import resolve_dbt_lineage_target
from sqlbuild.integrations.dbt._helpers.manifest.core import resolve_dbt_manifest_model
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.models import (
    DbtColumnLineageTrace,
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
    DbtManifestSource,
    DbtSourceSchemaInspectionResult,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphResourceType, DbtLineageDirection
from sqlbuild.spec.contracts.models import SourceColumnEntry, SourceEntry

_DBT_LINEAGE_COLUMN_SEPARATOR: str = ":"


@dataclass(frozen=True)
class _ColumnCandidateSelection:
    keys: frozenset[DbtCombinedGraphKey]
    model_names: frozenset[str]
    truncated: bool


@dataclass(frozen=True)
class _SourceSchemaColumnRequest:
    unique_id: str
    label: str
    database: str | None
    schema: str | None
    name: str


def dbt_column_lineage_selected_keys(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    target: str,
    direction: DbtLineageDirection,
    depth: int | None,
) -> frozenset[DbtCombinedGraphKey]:
    """Return the graph keys a column lineage target would analyze, or empty."""

    if _DBT_LINEAGE_COLUMN_SEPARATOR not in target or direction == DbtLineageDirection.BOTH:
        return frozenset()
    raw_resource, column_name = target.rsplit(_DBT_LINEAGE_COLUMN_SEPARATOR, 1)
    if not raw_resource or not column_name:
        return frozenset()
    resource_key: DbtCombinedGraphKey = resolve_dbt_lineage_target(
        project=project,
        manifest=manifest,
        target=raw_resource,
    )
    return _column_candidate_selection(
        graph=graph,
        key=resource_key,
        direction=direction,
        depth=depth,
    ).keys


def select_dbt_column_lineage_target(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    target: str,
    direction: DbtLineageDirection,
    depth: int | None,
    source_schemas: DbtSourceSchemaInspectionResult,
) -> DbtColumnLineageTrace | None:
    """Select column lineage when target uses resource:column syntax."""

    if _DBT_LINEAGE_COLUMN_SEPARATOR not in target:
        return None
    if direction == DbtLineageDirection.BOTH:
        raise DbtInteropArgumentError(
            "dbt column lineage supports --direction upstream or downstream, not both",
            code="C336",
        )
    raw_resource, column_name = target.rsplit(_DBT_LINEAGE_COLUMN_SEPARATOR, 1)
    if not raw_resource or not column_name:
        return None
    resource_key: DbtCombinedGraphKey = resolve_dbt_lineage_target(
        project=project,
        manifest=manifest,
        target=raw_resource,
    )
    analysis_resource_name: str = _analysis_resource_name(resource_key)
    candidate_selection: _ColumnCandidateSelection = _column_candidate_selection(
        graph=graph,
        key=resource_key,
        direction=direction,
        depth=depth,
    )
    analysis_project: CompiledProject = build_dbt_column_lineage_analysis_project(
        project=project,
        manifest=manifest,
        selected_keys=candidate_selection.keys,
        source_columns_by_unique_id=source_schemas.columns_by_unique_id,
    )
    column_lineage: ProjectColumnLineage | None = (
        _build_project_column_lineage_with_propagated_schema(
            project=analysis_project,
            model_names=candidate_selection.model_names,
        )
    )
    if column_lineage is None:
        raise DbtInteropArgumentError(
            "dbt column lineage requires SQL analysis to be enabled and available",
            code="C337",
            help="enable SQL analysis or install SQLBuild with Polyglot support",
        )
    target_column: QualifiedLineageColumn = QualifiedLineageColumn(
        resource_type=_analysis_resource_type(resource_key),
        resource_name=analysis_resource_name,
        column_name=column_name,
    )
    return DbtColumnLineageTrace(
        target=target_column,
        trace=_trace_column_with_depth(
            column_lineage=column_lineage,
            resource_name=analysis_resource_name,
            column_name=column_name,
            direction=direction,
            max_depth=depth,
        ),
        direction=direction,
        max_depth=depth,
        analyzed_model_count=len(candidate_selection.model_names),
        truncated=candidate_selection.truncated,
        warnings=source_schemas.warnings,
    )


def _build_project_column_lineage_with_propagated_schema(
    *,
    project: CompiledProject,
    model_names: frozenset[str],
) -> ProjectColumnLineage | None:
    current_project: CompiledProject = project
    lineage: ProjectColumnLineage | None = None
    for _iteration in range(3):
        lineage = build_project_column_lineage(project=current_project, model_names=model_names)
        if lineage is None:
            return None
        inferred_by_model: dict[str, tuple[InferredColumn, ...]] = {}
        for model_name, model_lineage in lineage.models.items():
            if not model_lineage.columns:
                continue
            inferred_columns: list[InferredColumn] = []
            for column in model_lineage.columns:
                inferred_columns.append(InferredColumn(name=column.output_column))
            inferred_by_model[model_name] = tuple(inferred_columns)
        next_models: tuple[CompiledModel, ...] = tuple(
            _with_propagated_columns(model=model, columns=inferred_by_model.get(model.name))
            for model in current_project.models
        )
        next_project: CompiledProject = CompiledProject(
            run_id=current_project.run_id,
            effective_target_name=current_project.effective_target_name,
            effective_connection=current_project.effective_connection,
            effective_vars=current_project.effective_vars,
            effective_target_database=current_project.effective_target_database,
            effective_target_schema=current_project.effective_target_schema,
            settings=current_project.settings,
            scenario=current_project.scenario,
            models=next_models,
            sources=current_project.sources,
        )
        if next_project.models == current_project.models:
            return lineage
        current_project = next_project
    return lineage


def _with_propagated_columns(
    *, model: CompiledModel, columns: tuple[InferredColumn, ...] | None
) -> CompiledModel:
    if columns is None or model.inferred_columns == columns:
        return model
    return CompiledModel(
        key=model.key,
        deps=model.deps,
        name=model.name,
        relative_path=model.relative_path,
        query_sql=model.query_sql,
        config=model.config,
        destination=model.destination,
        references=model.references,
        schema_entry=model.schema_entry,
        inferred_columns=columns,
        authored_sql=model.authored_sql,
        output_column_locations=model.output_column_locations,
        macro_deps=model.macro_deps,
    )


def inspect_dbt_source_schemas(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    manifest: DbtManifestIndex,
    selected_keys: frozenset[DbtCombinedGraphKey],
) -> DbtSourceSchemaInspectionResult:
    """Best-effort source/seed schema inspection for selected dbt lineage keys."""

    columns_by_unique_id: dict[str, tuple[SourceColumnEntry, ...]] = {}
    warnings: list[str] = []
    if not selected_keys:
        return DbtSourceSchemaInspectionResult(
            columns_by_unique_id=columns_by_unique_id,
            warnings=(),
        )
    connection: Any | None = None
    try:
        connection = adapter.connect(connection_config)
        requests: tuple[_SourceSchemaColumnRequest, ...] = _source_schema_column_requests(
            manifest=manifest,
            selected_keys=selected_keys,
        )
        inspected_columns: dict[str, tuple[ColumnInfo, ...]] = _inspect_columns_by_unique_id(
            adapter=adapter,
            connection=connection,
            requests=requests,
        )
        request: _SourceSchemaColumnRequest
        for request in requests:
            columns: tuple[ColumnInfo, ...] | None = inspected_columns.get(request.unique_id)
            if columns is None:
                warnings.append(
                    f"Could not inspect {request.label} {request.unique_id}; SELECT * lineage "
                    "from this relation may be incomplete: relation was not returned by batched "
                    "column lookup"
                )
                continue
            columns_by_unique_id[request.unique_id] = tuple(
                SourceColumnEntry(name=column.name, type=column.type) for column in columns
            )
    finally:
        if connection is not None:
            adapter.close(connection)
    return DbtSourceSchemaInspectionResult(
        columns_by_unique_id=columns_by_unique_id,
        warnings=tuple(warnings),
    )


def _source_schema_column_requests(
    *, manifest: DbtManifestIndex, selected_keys: frozenset[DbtCombinedGraphKey]
) -> tuple[_SourceSchemaColumnRequest, ...]:
    requests: list[_SourceSchemaColumnRequest] = []
    source: DbtManifestSource
    for source in manifest.sources_by_unique_id.values():
        if dbt_source_graph_key(source.unique_id) not in selected_keys:
            continue
        requests.append(
            _SourceSchemaColumnRequest(
                unique_id=source.unique_id,
                label="source",
                database=_manifest_relation_database(
                    database=source.database,
                    relation_name=source.relation_name,
                ),
                schema=_manifest_relation_schema(
                    schema=source.schema,
                    relation_name=source.relation_name,
                ),
                name=_manifest_relation_name(
                    explicit_name=source.identifier,
                    fallback_name=source.name,
                    relation_name=source.relation_name,
                ),
            )
        )
    seed: DbtManifestSeed
    for seed in manifest.seeds_by_unique_id.values():
        if dbt_source_graph_key(seed.unique_id) not in selected_keys:
            continue
        requests.append(
            _SourceSchemaColumnRequest(
                unique_id=seed.unique_id,
                label="seed",
                database=_manifest_relation_database(
                    database=seed.database,
                    relation_name=seed.relation_name,
                ),
                schema=_manifest_relation_schema(
                    schema=seed.schema,
                    relation_name=seed.relation_name,
                ),
                name=_manifest_relation_name(
                    explicit_name=seed.alias,
                    fallback_name=seed.name,
                    relation_name=seed.relation_name,
                ),
            )
        )
    return tuple(requests)


def _inspect_columns_by_unique_id(
    *,
    adapter: BaseAdapter,
    connection: Any,
    requests: tuple[_SourceSchemaColumnRequest, ...],
) -> dict[str, tuple[ColumnInfo, ...]]:
    requests_by_location: dict[tuple[str | None, str | None], list[_SourceSchemaColumnRequest]] = (
        defaultdict(list)
    )
    request: _SourceSchemaColumnRequest
    for request in requests:
        requests_by_location[(request.database, request.schema)].append(request)
    result: dict[str, tuple[ColumnInfo, ...]] = {}
    database_schema: tuple[str | None, str | None]
    location_requests: list[_SourceSchemaColumnRequest]
    for database_schema, location_requests in requests_by_location.items():
        database, schema = database_schema
        names: tuple[str, ...] = tuple(sorted({request.name for request in location_requests}))
        columns_by_name: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
            connection=connection,
            database=database,
            schemas=(schema,) if schema is not None else None,
            names=names,
        )
        for request in location_requests:
            columns: tuple[ColumnInfo, ...] | None = _columns_for_table_name(
                columns_by_name=columns_by_name,
                name=request.name,
            )
            if columns is not None:
                result[request.unique_id] = columns
    return result


def _columns_for_table_name(
    *, columns_by_name: dict[str, tuple[ColumnInfo, ...]], name: str
) -> tuple[ColumnInfo, ...] | None:
    if name in columns_by_name:
        return columns_by_name[name]
    lower_name: str = name.lower()
    if lower_name in columns_by_name:
        return columns_by_name[lower_name]
    upper_name: str = name.upper()
    if upper_name in columns_by_name:
        return columns_by_name[upper_name]
    return None


def _manifest_relation_database(*, database: str | None, relation_name: str) -> str | None:
    if database is not None:
        return database
    relation_parts: tuple[str, ...] = _relation_parts(relation_name)
    database_schema_relation_part_count: int = 3
    if len(relation_parts) >= database_schema_relation_part_count:
        return relation_parts[-3]
    return None


def _manifest_relation_schema(*, schema: str | None, relation_name: str) -> str | None:
    if schema is not None:
        return schema
    relation_parts: tuple[str, ...] = _relation_parts(relation_name)
    schema_relation_part_count: int = 2
    if len(relation_parts) >= schema_relation_part_count:
        return relation_parts[-2]
    return None


def _manifest_relation_name(
    *, explicit_name: str | None, fallback_name: str, relation_name: str
) -> str:
    if explicit_name is not None:
        return explicit_name
    relation_parts: tuple[str, ...] = _relation_parts(relation_name)
    return relation_parts[-1] if relation_parts else fallback_name


def _relation_parts(relation_name: str) -> tuple[str, ...]:
    return tuple(part.strip().strip('"') for part in relation_name.split(".") if part.strip())


def build_dbt_column_lineage_analysis_project(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_keys: frozenset[DbtCombinedGraphKey],
    source_columns_by_unique_id: dict[str, tuple[SourceColumnEntry, ...]],
) -> CompiledProject:
    """Build a temporary project whose SQL references use SQLBuild analyzable refs."""

    models: list[CompiledModel] = []
    sources: list[CompiledSource] = []
    dbt_model: DbtManifestModel
    for dbt_model in manifest.models_by_unique_id.values():
        key: DbtCombinedGraphKey = dbt_model_graph_key(dbt_model.unique_id)
        if key not in selected_keys:
            continue
        models.append(_dbt_model(model=dbt_model, manifest=manifest))
    sqlbuild_model: CompiledModel
    for sqlbuild_model in project.models:
        key = sqlbuild_model_graph_key(sqlbuild_model.name)
        if key not in selected_keys:
            continue
        models.append(_sqlbuild_model(model=sqlbuild_model, manifest=manifest))
    dbt_source: DbtManifestSource
    for dbt_source in manifest.sources_by_unique_id.values():
        key = dbt_source_graph_key(dbt_source.unique_id)
        if key not in selected_keys:
            continue
        sources.append(
            _dbt_source(
                source=dbt_source,
                columns=source_columns_by_unique_id.get(dbt_source.unique_id, ()),
            )
        )
    dbt_seed: DbtManifestSeed
    for dbt_seed in manifest.seeds_by_unique_id.values():
        key = dbt_source_graph_key(dbt_seed.unique_id)
        if key not in selected_keys:
            continue
        sources.append(
            _dbt_seed_source(
                seed=dbt_seed,
                columns=source_columns_by_unique_id.get(dbt_seed.unique_id, ()),
            )
        )
    return CompiledProject(
        run_id=project.run_id,
        effective_target_name=project.effective_target_name,
        effective_connection=project.effective_connection,
        effective_vars=project.effective_vars,
        effective_target_database=project.effective_target_database,
        effective_target_schema=project.effective_target_schema,
        settings=project.settings,
        scenario=project.scenario,
        models=tuple(models),
        sources=tuple(sources),
    )


def _column_candidate_selection(
    *,
    graph: DbtCombinedGraph,
    key: DbtCombinedGraphKey,
    direction: DbtLineageDirection,
    depth: int | None,
) -> _ColumnCandidateSelection:
    deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]] = (
        graph.downstream_deps
        if direction == DbtLineageDirection.DOWNSTREAM
        else graph.upstream_deps
    )
    selected: set[DbtCombinedGraphKey] = {key}
    selected.update(_walk_bounded(anchors=(key,), deps=deps, max_depth=depth))
    extended: set[DbtCombinedGraphKey] = set(selected)
    if depth is not None:
        extended = {key}
        extended.update(_walk_bounded(anchors=(key,), deps=deps, max_depth=depth + 1))
    return _ColumnCandidateSelection(
        keys=frozenset(selected),
        model_names=frozenset(
            _analysis_resource_name(selected_key)
            for selected_key in selected
            if selected_key.resource_type == DbtCombinedGraphResourceType.MODEL
        ),
        truncated=depth is not None and extended != selected,
    )


def _dbt_model(*, model: DbtManifestModel, manifest: DbtManifestIndex) -> CompiledModel:
    query_sql: str = _rewrite_dbt_compiled_sql(
        sql=_dbt_model_compiled_sql(model), manifest=manifest
    )
    relative_path: Path = Path(
        str(model.payload.get("original_file_path") or f"dbt/{model.unique_id}.sql")
    )
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model.unique_id),
        deps=(),
        name=model.unique_id,
        relative_path=relative_path,
        query_sql=query_sql,
        config=CompileModelConfig(),
        destination=CompiledRelationLocation(
            database=model.database,
            schema=model.schema,
            name=model.alias or model.name,
            qualified_name=model.relation_name,
            logical_schema=None,
            logical_database=None,
        ),
        authored_sql=query_sql,
    )


def _sqlbuild_model(*, model: CompiledModel, manifest: DbtManifestIndex) -> CompiledModel:
    query_sql: str = _rewrite_sqlbuild_dbt_refs(sql=model.query_sql, manifest=manifest)
    return CompiledModel(
        key=model.key,
        deps=model.deps,
        name=model.name,
        relative_path=model.relative_path,
        query_sql=query_sql,
        config=model.config,
        destination=model.destination,
        references=model.references,
        schema_entry=model.schema_entry,
        inferred_columns=model.inferred_columns,
        authored_sql=query_sql,
        output_column_locations=model.output_column_locations,
        macro_deps=model.macro_deps,
    )


def _dbt_source(
    *, source: DbtManifestSource, columns: tuple[SourceColumnEntry, ...]
) -> CompiledSource:
    entry: SourceEntry = SourceEntry(
        name=source.unique_id,
        database=source.database,
        schema=source.schema,
        table=source.identifier or source.name,
        columns=columns,
    )
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("/dbt") / f"{source.unique_id}.yml",
        relative_path=Path(str(source.payload.get("original_file_path") or "dbt/sources.yml")),
        contents="",
        source_entries=(entry,),
    )
    return CompiledSource(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=source.unique_id),
        deps=(),
        name=source.unique_id,
        source_entry=entry,
        source_file=source_file,
    )


def _dbt_seed_source(
    *, seed: DbtManifestSeed, columns: tuple[SourceColumnEntry, ...]
) -> CompiledSource:
    entry: SourceEntry = SourceEntry(
        name=seed.unique_id,
        database=seed.database,
        schema=seed.schema,
        table=seed.alias or seed.name,
        columns=columns,
    )
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("/dbt") / f"{seed.unique_id}.yml",
        relative_path=Path(str(seed.payload.get("original_file_path") or "dbt/seeds.yml")),
        contents="",
        source_entries=(entry,),
    )
    return CompiledSource(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=seed.unique_id),
        deps=(),
        name=seed.unique_id,
        source_entry=entry,
        source_file=source_file,
    )


def _rewrite_sqlbuild_dbt_refs(*, sql: str, manifest: DbtManifestIndex) -> str:
    pattern: re.Pattern[str] = re.compile(
        r"__dbt_ref\(\s*(['\"])(?P<first>[^'\"]+)\1"
        r"(?:\s*,\s*(['\"])(?P<second>[^'\"]+)\3)?\s*\)"
    )

    def replace_match(match: re.Match[str]) -> str:
        first: str = match.group("first")
        second: str | None = match.group("second")
        dbt_model: DbtManifestModel = resolve_dbt_manifest_model(
            manifest=manifest,
            package_name=first if second is not None else None,
            name=second or first,
        )
        return SqlReferenceKind.REF.example_call(dbt_model.unique_id, quote='"')

    return pattern.sub(replace_match, sql)


def _dbt_model_compiled_sql(model: DbtManifestModel) -> str:
    compiled_code: object | None = model.payload.get("compiled_code")
    if isinstance(compiled_code, str) and compiled_code:
        return compiled_code
    compiled_sql: object | None = model.payload.get("compiled_sql")
    if isinstance(compiled_sql, str) and compiled_sql:
        return compiled_sql
    return model.query_sql


def _rewrite_dbt_compiled_sql(*, sql: str, manifest: DbtManifestIndex) -> str:
    rewritten: str = sql
    replacements: dict[str, str] = {}
    relation_names: tuple[str, ...] = (
        tuple(model.relation_name for model in manifest.models_by_unique_id.values())
        + tuple(source.relation_name for source in manifest.sources_by_unique_id.values())
        + tuple(seed.relation_name for seed in manifest.seeds_by_unique_id.values())
    )
    relation_table_counts: dict[str, int] = {}
    relation_name: str
    for relation_name in relation_names:
        table_name: str = _relation_table_name(relation_name)
        relation_table_counts[table_name] = relation_table_counts.get(table_name, 0) + 1
    model: DbtManifestModel
    for model in manifest.models_by_unique_id.values():
        replacements.update(
            _relation_replacements(
                relation_name=model.relation_name,
                resource_name=model.unique_id,
                kind="ref",
                include_table_only=relation_table_counts[_relation_table_name(model.relation_name)]
                == 1,
            )
        )
    source: DbtManifestSource
    for source in manifest.sources_by_unique_id.values():
        replacements.update(
            _relation_replacements(
                relation_name=source.relation_name,
                resource_name=source.unique_id,
                kind="source",
                include_table_only=relation_table_counts[_relation_table_name(source.relation_name)]
                == 1,
            )
        )
    seed: DbtManifestSeed
    for seed in manifest.seeds_by_unique_id.values():
        replacements.update(
            _relation_replacements(
                relation_name=seed.relation_name,
                resource_name=seed.unique_id,
                kind="source",
                include_table_only=relation_table_counts[_relation_table_name(seed.relation_name)]
                == 1,
            )
        )
    for relation_name, reference_call in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        rewritten = _replace_relation_in_from_or_join(
            sql=rewritten, relation_name=relation_name, replacement=reference_call
        )
    return rewritten


def _relation_replacements(
    *,
    relation_name: str,
    resource_name: str,
    kind: str,
    include_table_only: bool,
) -> dict[str, str]:
    reference_kind: SqlReferenceKind = (
        SqlReferenceKind.REF if kind == SqlReferenceKind.REF else SqlReferenceKind.SOURCE
    )
    reference_call: str = reference_kind.example_call(resource_name, quote='"')
    stripped_parts: tuple[str, ...] = tuple(
        part.strip().strip('"').strip("'") for part in relation_name.split(".") if part.strip()
    )
    quoted: str = ".".join(f'"{part}"' for part in stripped_parts)
    unquoted: str = ".".join(stripped_parts)
    schema_relation_part_count: int = 2
    schema_qualified: str | None = (
        ".".join(stripped_parts[-2:]) if len(stripped_parts) >= schema_relation_part_count else None
    )
    quoted_schema_qualified: str | None = (
        ".".join(f'"{part}"' for part in stripped_parts[-2:])
        if len(stripped_parts) >= schema_relation_part_count
        else None
    )
    replacements: dict[str, str] = {
        relation_name: reference_call,
        quoted: reference_call,
        unquoted: reference_call,
        **({schema_qualified: reference_call} if schema_qualified is not None else {}),
        **(
            {quoted_schema_qualified: reference_call} if quoted_schema_qualified is not None else {}
        ),
    }
    if include_table_only:
        replacements[stripped_parts[-1] if stripped_parts else relation_name] = reference_call
    return replacements


def _relation_table_name(relation_name: str) -> str:
    stripped_parts: tuple[str, ...] = tuple(
        part.strip().strip('"').strip("'") for part in relation_name.split(".") if part.strip()
    )
    return stripped_parts[-1] if stripped_parts else relation_name


def _replace_relation_in_from_or_join(*, sql: str, relation_name: str, replacement: str) -> str:
    escaped_relation: str = re.escape(relation_name)
    pattern: re.Pattern[str] = re.compile(
        rf"(?P<prefix>\b(?:from|join)\s+){escaped_relation}(?P<suffix>\b|\s|$)",
        flags=re.IGNORECASE,
    )
    return pattern.sub(
        lambda match: f"{match.group('prefix')}{replacement}{match.group('suffix')}", sql
    )


def _trace_column_with_depth(
    *,
    column_lineage: ProjectColumnLineage,
    resource_name: str,
    column_name: str,
    direction: DbtLineageDirection,
    max_depth: int | None,
) -> tuple[ColumnLineageEdge, ...]:
    if max_depth == 0:
        return ()
    result: list[ColumnLineageEdge] = []
    stack: list[tuple[str, str, int]] = [(resource_name, column_name, 0)]
    visited: set[tuple[str, str]] = set()
    while stack:
        current_resource, current_column, current_depth = stack.pop()
        if (current_resource, current_column) in visited:
            continue
        visited.add((current_resource, current_column))
        if max_depth is not None and current_depth >= max_depth:
            continue
        if direction == DbtLineageDirection.DOWNSTREAM:
            for edge in column_lineage.column_consumers(
                resource_name=current_resource,
                column_name=current_column,
            ):
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


def _walk_bounded(
    *,
    anchors: tuple[DbtCombinedGraphKey, ...],
    deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
    max_depth: int | None,
) -> frozenset[DbtCombinedGraphKey]:
    if max_depth is None:
        visited: set[DbtCombinedGraphKey] = set()
        stack: list[DbtCombinedGraphKey] = list(anchors)
        while stack:
            current: DbtCombinedGraphKey = stack.pop()
            for neighbor in deps.get(current, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        return frozenset(visited)
    if max_depth == 0:
        return frozenset()
    visited = set()
    queue: list[tuple[DbtCombinedGraphKey, int]] = [(anchor, 0) for anchor in anchors]
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


def _analysis_resource_name(key: DbtCombinedGraphKey) -> str:
    return key.name


def _analysis_resource_type(key: DbtCombinedGraphKey) -> CompiledResourceType:
    if key.resource_type == DbtCombinedGraphResourceType.SOURCE:
        return CompiledResourceType.SOURCE
    return CompiledResourceType.MODEL
