from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSchemaFile, DiscoveredSeedFile
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaSeedEntry, SettingsConfig


def make_compiled_project(
    *,
    models: tuple[CompiledModel, ...],
    seeds: tuple[CompiledSeed, ...] = (),
    sql_analysis_enabled: bool = True,
) -> CompiledProject:
    return CompiledProject(
        run_id="test-run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(sql_analysis=sql_analysis_enabled),
        models=models,
        seeds=seeds,
    )


def make_compiled_model(
    *,
    name: str,
    query_sql: str,
    inferred_columns: tuple[str, ...] | None,
) -> CompiledModel:
    return CompiledModel(
        key=CompiledObjectKey(CompiledResourceType.MODEL, name),
        deps=(),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        query_sql=query_sql,
        config=CompileModelConfig(),
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=name,
        ),
        inferred_columns=(
            None,
            tuple(InferredColumn(column_name) for column_name in (inferred_columns or ())),
        )[inferred_columns is not None],
    )


def make_compiled_seed(*, name: str, columns: tuple[str, ...]) -> CompiledSeed:
    return CompiledSeed(
        key=CompiledObjectKey(CompiledResourceType.SEED, name),
        deps=(),
        name=name,
        seed_file=DiscoveredSeedFile(
            file_path=Path(f"seeds/{name}.csv"),
            relative_path=Path(f"seeds/{name}.csv"),
        ),
        schema_entry=SchemaSeedEntry(
            name=name,
            columns=tuple(SchemaColumn(column_name) for column_name in columns),
        ),
        schema_file=DiscoveredSchemaFile(
            file_path=Path("seeds/schema.yml"),
            relative_path=Path("seeds/schema.yml"),
            contents="",
            model_entries=(),
            seed_entries=(),
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=name,
        ),
    )


def edge_label(source_name: str, source_column: str, target_name: str, target_column: str) -> str:
    return f"{source_name}.{source_column}->{target_name}.{target_column}"
