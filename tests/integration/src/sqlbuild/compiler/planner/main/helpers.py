"""Test helpers for planner orchestration integration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    CompileSqlReference,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.function_fingerprints import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.shared.helpers.hashing import compute_query_hash
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.project import SettingsConfig
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
    FormatPlanIntegrationTestCase,
    SourceCursorInputPlanErrorTestCase,
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
        model_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in dep_names
        )
        function_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name=d)
            for d in test_case.function_deps.get(model_name, ())
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=model_name,
                ),
                deps=(*model_deps, *function_deps),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=query_sql,
                config=CompileModelConfig(values=config_values),
                destination=CompiledRelationDestination(
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
                destination=CompiledRelationDestination(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    functions: list[CompiledFunction] = []
    function_name: str
    for function_name, target_schema in test_case.function_targets.items():
        body_sql: str = test_case.function_bodies.get(function_name, "value = 1")
        language: FunctionLanguage = test_case.function_languages.get(
            function_name, FunctionLanguage.SQL
        )
        functions.append(
            CompiledFunction(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.FUNCTION,
                    name=function_name,
                ),
                deps=(),
                name=function_name,
                relative_path=Path(f"functions/{language.value}/{function_name}.sql"),
                arguments=(FunctionArgument(name="value", type="INTEGER"),),
                returns="INTEGER",
                body_sql=body_sql,
                destination=CompiledRelationDestination(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                fingerprint_destination=CompiledRelationDestination(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                language=language,
                entry_point="main" if language == FunctionLanguage.PYTHON else None,
                replay_on_change=test_case.function_replay_on_changes.get(function_name),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection=test_case.effective_connection,
        effective_vars={},
        settings=SettingsConfig(
            sql_analysis=_settings_bool(
                test_case.effective_connection, "sql_analysis", default=False
            )
        ),
        models=tuple(models),
        seeds=tuple(seeds),
        functions=tuple(functions),
    )


def _settings_bool(settings: dict[str, object], key: str, *, default: bool) -> bool:
    """Read a boolean setting from legacy test-case settings dictionaries."""

    raw_value: object | None = settings.get(key)
    if isinstance(raw_value, bool):
        return raw_value
    return default


def build_project_from_source_cursor_input_test_case(
    test_case: SourceCursorInputPlanErrorTestCase,
) -> CompiledProject:
    """Build a project with one incremental model reading one source."""

    source_entry: SourceEntry = SourceEntry(
        name=test_case.source_name,
        schema=test_case.source_schema,
        table=test_case.source_table,
    )
    source: CompiledSource = CompiledSource(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE,
            name=test_case.source_name,
        ),
        deps=(),
        name=test_case.source_name,
        source_entry=source_entry,
        source_file=DiscoveredSourceFile(
            file_path=Path("sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents="",
            source_entries=(source_entry,),
        ),
    )
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=test_case.model_name,
        ),
        deps=(source.key,),
        name=test_case.model_name,
        relative_path=Path(f"models/{test_case.model_name}.sql"),
        query_sql=f'SELECT * FROM __source("{test_case.source_name}")',
        references=(
            CompileSqlReference(
                ref_kind=SqlReferenceKind.SOURCE,
                ref_name=test_case.source_name,
            ),
        ),
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "cursor": test_case.cursor_column,
                "cursor_inputs": {test_case.source_name: test_case.cursor_input_column},
            }
        ),
        destination=CompiledRelationDestination(
            database=None,
            schema="staging",
            name=test_case.model_name,
            qualified_name=f"staging.{test_case.model_name}",
        ),
    )
    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(model,),
        sources=(source,),
    )


def write_previous_function_fingerprints(
    *,
    test_case: BuildExecutionPlanTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Write previous function definition fingerprints for planner tests."""

    if not test_case.previous_function_bodies:
        return
    previous_case: BuildExecutionPlanTestCase = replace(
        test_case,
        function_bodies={**test_case.function_bodies, **test_case.previous_function_bodies},
    )
    previous_project: CompiledProject = build_project_from_test_case(previous_case)
    function_map: dict[str, CompiledFunction] = {
        function.name: function for function in previous_project.functions
    }
    function_name: str
    for function_name in test_case.previous_function_bodies:
        function: CompiledFunction = function_map[function_name]
        fingerprint_sql: str = build_compiled_function_fingerprint_sql(function)
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=function.destination.database,
            schema=function.destination.schema or "",
            fingerprint=Fingerprint(
                model_name=function.name,
                target_database=function.destination.database,
                target_schema=function.destination.schema,
                target_name=function.destination.name,
                run_id="previous_run",
                query_hash=compute_query_hash(fingerprint_sql),
                schema_fingerprint=compute_query_hash(""),
                query_sql=fingerprint_sql,
                ts=datetime.now(tz=UTC),
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )


def build_project_from_format_test_case(
    test_case: FormatPlanIntegrationTestCase,
) -> CompiledProject:
    """Build a CompiledProject from a format integration test case."""

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
                destination=CompiledRelationDestination(
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
                destination=CompiledRelationDestination(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection=test_case.effective_connection,
        effective_vars={},
        models=tuple(models),
        seeds=tuple(seeds),
    )
