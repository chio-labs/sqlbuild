"""Test helpers for planner graph tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
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
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def model_key(name: str) -> CompiledObjectKey:
    """Build a model object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name)


def source_key(name: str) -> CompiledObjectKey:
    """Build a source object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)


def seed_key(name: str) -> CompiledObjectKey:
    """Build a seed object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name)


def build_test_project(
    *,
    model_deps: dict[str, tuple[str, ...]] | None = None,
    source_names: tuple[str, ...] = (),
    seed_names: tuple[str, ...] = (),
) -> CompiledProject:
    """Build a minimal CompiledProject for graph tests."""

    source_name_set: set[str] = set(source_names)
    seed_name_set: set[str] = set(seed_names)
    models: list[CompiledModel] = []
    model_name: str
    dep_names: tuple[str, ...]
    for model_name, dep_names in (model_deps or {}).items():
        deps: tuple[CompiledObjectKey, ...] = tuple(
            _resolve_dep_key(d, source_name_set, seed_name_set) for d in dep_names
        )
        models.append(
            CompiledModel(
                key=model_key(model_name),
                deps=deps,
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=f"SELECT * FROM {model_name}",
                config=CompileModelConfig(),
                target=CompiledRelationTarget(
                    database=None, schema=None, name=model_name, qualified_name=None
                ),
            )
        )

    sources: list[CompiledSource] = []
    source_name: str
    for source_name in source_names:
        source_entry: SourceEntry = SourceEntry(
            name=source_name, schema="public", table=source_name
        )
        sources.append(
            CompiledSource(
                key=source_key(source_name),
                deps=(),
                name=source_name,
                source_entry=source_entry,
                source_file=DiscoveredSourceFile(
                    file_path=Path(f"sources/{source_name}.yml"),
                    relative_path=Path(source_name),
                    contents="",
                    source_entries=(source_entry,),
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name in seed_names:
        seeds.append(
            CompiledSeed(
                key=seed_key(seed_name),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=Path(f"seeds/{seed_name}.csv"),
                    relative_path=Path(f"seeds/{seed_name}.csv"),
                ),
                schema_entry=SchemaSeedEntry(name=seed_name, columns=()),
                schema_file=_stub_schema_file(),
                target=CompiledRelationTarget(
                    database=None, schema=None, name=seed_name, qualified_name=None
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


def _resolve_dep_key(name: str, source_names: set[str], seed_names: set[str]) -> CompiledObjectKey:
    """Resolve a dependency name to the correct key type."""

    if name in source_names:
        return source_key(name)
    if name in seed_names:
        return seed_key(name)
    return model_key(name)


def _stub_schema_file() -> DiscoveredSchemaFile:
    """Return a minimal schema file stub for seed construction."""

    return DiscoveredSchemaFile(
        file_path=Path("seeds/schema.yml"),
        relative_path=Path("seeds/schema.yml"),
        contents="",
        model_entries=(),
        seed_entries=(),
    )
