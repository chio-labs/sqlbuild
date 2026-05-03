"""Test helpers for planner orchestration integration tests."""

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
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
)


def build_project_from_test_case(
    test_case: BuildExecutionPlanTestCase,
) -> CompiledProject:
    """Build a CompiledProject from an integration test case."""

    models: list[CompiledModel] = []
    model_name: str
    target_schema: str
    for model_name, target_schema in test_case.model_targets.items():
        config_values: dict[str, object] = test_case.model_configs.get(model_name, {})
        query_sql: str = test_case.model_queries.get(model_name, f"SELECT * FROM {model_name}")
        dep_names: tuple[str, ...] = test_case.model_deps.get(model_name, ())
        deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in dep_names
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=model_name,
                ),
                deps=deps,
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=query_sql,
                config=CompileModelConfig(values=config_values),
                target=CompiledRelationTarget(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=f"{target_schema}.{model_name}",
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in test_case.seed_targets.items():
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name=seed_name,
                ),
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
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_environment_name=None,
        effective_connection=test_case.effective_connection,
        effective_vars={},
        models=tuple(models),
        seeds=tuple(seeds),
    )
