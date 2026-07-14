"""Test helpers for warehouse snapshot integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SchemaSeedEntry, SourceEntry


class RecordingDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter that records get_all_columns name filters for assertions."""

    def __init__(self) -> None:
        self.get_all_columns_names: list[tuple[str, ...] | None] = []

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        self.get_all_columns_names.append(names)
        return super().get_all_columns(
            connection=connection,
            database=database,
            schemas=schemas,
            names=names,
        )


@dataclass(frozen=True)
class _IncrementalModelSpec:
    """Spec for building a test incremental model with cursor config."""

    name: str
    schema: str
    cursor: str
    ref_names: tuple[str, ...]


def build_project_with_targets(
    *,
    model_locations: dict[str, str | None] | None = None,
    model_deps: dict[str, tuple[str, ...]] | None = None,
    seed_locations: dict[str, str | None] | None = None,
    incremental_models: tuple[_IncrementalModelSpec, ...] = (),
    source_names: tuple[tuple[str, str, str], ...] = (),
) -> CompiledProject:
    """Build a minimal CompiledProject with explicit target schemas."""

    models: list[CompiledModel] = []
    model_name: str
    target_schema: str | None
    for model_name, target_schema in (model_locations or {}).items():
        deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=dep_name)
            for dep_name in (model_deps or {}).get(model_name, ())
        )
        references: tuple[CompileSqlReference, ...] = tuple(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name=dep_name)
            for dep_name in (model_deps or {}).get(model_name, ())
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
                deps=deps,
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=f"SELECT * FROM {model_name}",
                config=CompileModelConfig(),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=(None, f"{target_schema}.{model_name}")[bool(target_schema)],
                ),
                references=references,
            )
        )

    spec: _IncrementalModelSpec
    for spec in incremental_models:
        references: tuple[CompileSqlReference, ...] = tuple(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name=ref_name)
            for ref_name in spec.ref_names
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=spec.name),
                deps=(),
                name=spec.name,
                relative_path=Path(f"models/{spec.name}.sql"),
                query_sql=f"SELECT * FROM {spec.name}",
                config=CompileModelConfig(
                    values={
                        "materialized": "incremental",
                        "cursor": spec.cursor,
                        "incremental_strategy": "delete_insert",
                    }
                ),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=spec.schema,
                    name=spec.name,
                    qualified_name=f"{spec.schema}.{spec.name}",
                ),
                references=references,
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in (seed_locations or {}).items():
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=seed_name),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=Path(f"seeds/{seed_name}.csv"),
                    relative_path=Path(f"seeds/{seed_name}.csv"),
                ),
                schema_entry=SchemaSeedEntry(name=seed_name, columns=()),
                schema_file=DiscoveredSchemaFile(
                    file_path=Path("seeds/schema.yml"),
                    relative_path=Path("seeds/schema.yml"),
                    contents="",
                    model_entries=(),
                    seed_entries=(),
                ),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=(None, f"{target_schema}.{seed_name}")[bool(target_schema)],
                ),
            )
        )

    sources: list[CompiledSource] = []
    source_spec: tuple[str, str, str]
    for source_spec in source_names:
        sources.append(
            CompiledSource(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SOURCE, name=source_spec[0]
                ),
                deps=(),
                name=source_spec[0],
                source_entry=SourceEntry(
                    name=source_spec[0], schema=source_spec[1], table=source_spec[2]
                ),
                source_file=DiscoveredSourceFile(
                    file_path=Path("sources/sources.yml"),
                    relative_path=Path("sources/sources.yml"),
                    contents="",
                    source_entries=(),
                ),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=tuple(models),
        sources=tuple(sources),
        seeds=tuple(seeds),
    )


def build_deferred_locations_from_map(
    targets: dict[str, str],
) -> dict[str, CompiledRelationLocation]:
    """Build deferred locations from a name -> qualified_name mapping."""

    return {
        name: CompiledRelationLocation(
            database=None,
            schema=(None, qualified.rsplit(".", 1)[0])["." in qualified],
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }
