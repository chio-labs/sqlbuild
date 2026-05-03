"""Test helpers for warehouse snapshot integration tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSchemaFile, DiscoveredSeedFile
from sqlbuild.spec.models.schema import SchemaSeedEntry


def build_project_with_targets(
    *,
    model_targets: dict[str, str | None] | None = None,
    seed_targets: dict[str, str | None] | None = None,
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

    return CompiledProject(
        run_id="test_run",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        models=tuple(models),
        sources=(),
        seeds=tuple(seeds),
    )
