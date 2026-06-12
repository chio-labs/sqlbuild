"""Test helpers for manifest tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ChainStep,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry


def model_key(name: str) -> CompiledObjectKey:
    """Build a model object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name)


def source_key(name: str) -> CompiledObjectKey:
    """Build a source object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)


def run_manifest(**kwargs: Any) -> dict[str, Any]:
    """Build a manifest and return it with Any typing for test convenience."""

    result: dict[str, object] = build_manifest(**kwargs)
    return result  # type: ignore[return-value]


def manifest_nodes(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the nodes dict from a manifest result."""

    return result["nodes"]


def manifest_sources(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the sources dict from a manifest result."""

    return result["sources"]


def manifest_macros(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the macros dict from a manifest result."""

    return result["macros"]


def build_test_model(
    *,
    name: str,
    query_sql: str = "SELECT 1",
    relative_path: str = "models/test.sql",
    database: str | None = None,
    schema: str | None = "public",
    alias: str | None = None,
    qualified_name: str | None = None,
    deps: tuple[CompiledObjectKey, ...] = (),
    config_values: dict[str, object] | None = None,
    description: str | None = None,
    columns: tuple[SchemaColumn, ...] = (),
) -> CompiledModel:
    """Build a minimal CompiledModel for manifest tests."""

    effective_alias: str = alias if alias is not None else name
    effective_qualified: str | None = qualified_name
    if effective_qualified is None and schema is not None:
        effective_qualified = f"{schema}.{effective_alias}"

    schema_entry: SchemaModelEntry | None = None
    if description is not None or columns:
        schema_entry = SchemaModelEntry(
            name=name,
            description=description,
            columns=columns,
        )

    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        deps=deps,
        name=name,
        relative_path=Path(relative_path),
        query_sql=query_sql,
        config=CompileModelConfig(values=config_values or {}),
        destination=CompiledRelationLocation(
            database=database,
            schema=schema,
            name=effective_alias,
            qualified_name=effective_qualified,
        ),
        schema_entry=schema_entry,
    )


def build_test_source(
    *,
    name: str,
    database: str | None = None,
    schema: str = "public",
    table: str | None = None,
    description: str | None = None,
    columns: tuple[SourceColumnEntry, ...] = (),
) -> CompiledSource:
    """Build a minimal CompiledSource for manifest tests."""

    entry: SourceEntry = SourceEntry(
        name=name,
        database=database,
        schema=schema,
        table=table,
        description=description,
        columns=columns,
    )
    return CompiledSource(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name),
        deps=(),
        name=name,
        source_entry=entry,
        source_file=DiscoveredSourceFile(
            file_path=Path(f"sources/{name}.yml"),
            relative_path=Path(f"sources/{name}.yml"),
            contents="",
            source_entries=(entry,),
        ),
    )


def build_test_seed(
    *,
    name: str,
    database: str | None = None,
    schema: str | None = "public",
) -> CompiledSeed:
    """Build a minimal CompiledSeed for manifest tests."""

    return CompiledSeed(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        deps=(),
        name=name,
        seed_file=DiscoveredSeedFile(
            file_path=Path(f"seeds/{name}.csv"),
            relative_path=Path(f"seeds/{name}.csv"),
        ),
        schema_entry=SchemaSeedEntry(name=name, columns=()),
        schema_file=DiscoveredSchemaFile(
            file_path=Path("seeds/schema.yml"),
            relative_path=Path("seeds/schema.yml"),
            contents="",
            model_entries=(),
            seed_entries=(),
        ),
        destination=CompiledRelationLocation(
            database=database,
            schema=schema,
            name=name,
            qualified_name=f"{schema}.{name}" if schema else name,
        ),
    )


def build_test_plan_entry(
    *,
    name: str,
    resolved_sql: str = "SELECT 1 resolved",
    logical_ddl: str = "CREATE TABLE t AS (SELECT 1)",
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for manifest tests."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None, schema="public", name=name, qualified_name=f"public.{name}"
        ),
        fingerprint_query_sql=resolved_sql,
        resolved_sql=resolved_sql,
        logical_ddl=logical_ddl,
    )


def build_test_project(
    *,
    models: tuple[CompiledModel, ...] = (),
    sources: tuple[CompiledSource, ...] = (),
    seeds: tuple[CompiledSeed, ...] = (),
) -> CompiledProject:
    """Build a minimal CompiledProject for manifest tests."""

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=models,
        sources=sources,
        seeds=seeds,
    )


def build_test_audit_plan_entry(
    *,
    name: str,
    resolved_sql: str = "SELECT col FROM tbl WHERE col IS NULL",
    scope_deps: tuple[CompiledObjectKey, ...] = (),
    attached_target_name: str | None = None,
    attached_column_name: str | None = None,
) -> AuditPlanEntry:
    """Build a minimal AuditPlanEntry for manifest tests."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=resolved_sql,
        unresolved_sql=resolved_sql,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.WARN,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        scope_deps=scope_deps,
        attached_target_name=attached_target_name,
        attached_column_name=attached_column_name,
    )


def build_test_sql_test_plan_entry(
    *,
    name: str,
    chain: tuple[ChainStep, ...] = (),
    scope_deps: tuple[CompiledObjectKey, ...] = (),
) -> SqlTestPlanEntry:
    """Build a minimal SqlTestPlanEntry for manifest tests."""

    return SqlTestPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=name),
        name=name,
        chain=chain,
        scope_deps=scope_deps,
    )


def build_test_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    seed_entries: tuple[SeedPlanEntry, ...] = (),
    audit_entries: tuple[AuditPlanEntry, ...] = (),
    test_entries: tuple[SqlTestPlanEntry, ...] = (),
) -> PlanOutput:
    """Build a minimal PlanOutput for manifest tests."""

    return PlanOutput(
        model_entries=model_entries,
        seed_entries=seed_entries,
        audit_entries=audit_entries,
        test_entries=test_entries,
    )
