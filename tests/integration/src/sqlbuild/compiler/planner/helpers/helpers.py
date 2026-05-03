"""Test helpers for warehouse snapshot integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlReferenceKind
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class _IncrementalModelSpec:
    """Spec for building a test incremental model with cursor config."""

    name: str
    schema: str
    cursor: str
    ref_names: tuple[str, ...]


def build_project_with_targets(
    *,
    model_targets: dict[str, str | None] | None = None,
    seed_targets: dict[str, str | None] | None = None,
    incremental_models: tuple[_IncrementalModelSpec, ...] = (),
    source_names: tuple[tuple[str, str, str], ...] = (),
) -> CompiledProject:
    """Build a minimal CompiledProject with explicit target schemas."""

    models: list[CompiledModel] = []
    model_name: str
    target_schema: str | None
    for model_name, target_schema in (model_targets or {}).items():
        models.append(
            CompiledModel(
                key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
                deps=(),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=f"SELECT * FROM {model_name}",
                config=CompileModelConfig(),
                target=CompiledRelationTarget(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=(f"{target_schema}.{model_name}" if target_schema else None),
                ),
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
                target=CompiledRelationTarget(
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
    for seed_name, target_schema in (seed_targets or {}).items():
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
                target=CompiledRelationTarget(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=(f"{target_schema}.{seed_name}" if target_schema else None),
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
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        models=tuple(models),
        sources=tuple(sources),
        seeds=tuple(seeds),
    )


def build_deferred_targets_from_map(
    targets: dict[str, str],
) -> dict[str, CompiledRelationTarget]:
    """Build deferred targets from a name -> qualified_name mapping."""

    return {
        name: CompiledRelationTarget(
            database=None,
            schema=qualified.rsplit(".", 1)[0] if "." in qualified else None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }
