"""Test helpers for planner orchestration integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from types import MappingProxyType
from typing import Any, cast

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
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
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner.main.execution.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import (
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
)
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
    for model_name, target_schema in test_case.model_locations.items():
        config_values: dict[str, object] = test_case.model_configs.get(model_name, {})
        query_sql: str = test_case.model_queries.get(model_name, f"SELECT * FROM {model_name}")
        dep_names: tuple[str, ...] = test_case.model_deps.get(model_name, ())
        model_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in dep_names
        )
        function_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.UDF, name=d)
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
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=f"{target_schema}.{model_name}",
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in test_case.seed_locations.items():
        seed_file_path: Path = _ensure_test_seed_file(seed_name)
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name=seed_name,
                ),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=seed_file_path,
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
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    functions: list[CompiledFunction] = []
    function_name: str
    for function_name, target_schema in test_case.function_locations.items():
        body_sql: str = test_case.function_bodies.get(function_name, "value = 1")
        language: FunctionLanguage = test_case.function_languages.get(
            function_name, FunctionLanguage.SQL
        )
        functions.append(
            CompiledFunction(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.UDF,
                    name=function_name,
                ),
                deps=(),
                name=function_name,
                relative_path=Path(f"functions/{language.value}/{function_name}.sql"),
                arguments=(FunctionArgument(name="value", type="INTEGER"),),
                returns="INTEGER",
                body_sql=body_sql,
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                language=language,
                entry_point=(None, "main")[language == FunctionLanguage.PYTHON],
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
    return cast(bool, (default, raw_value)[isinstance(raw_value, bool)])


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
        destination=CompiledRelationLocation(
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


def build_future_cursor_project() -> CompiledProject:
    """Build one timestamp incremental source project for future safety tests."""

    case: SourceCursorInputPlanErrorTestCase = SourceCursorInputPlanErrorTestCase(
        description="future cursor",
        setup_sql=(),
        model_name="events_incremental",
        source_name="raw_events",
        source_schema="raw",
        source_table="events",
        cursor_column="occurred_at",
        cursor_input_column="occurred_at",
        expected_error_fragment="",
    )
    project: CompiledProject = build_project_from_source_cursor_input_test_case(case)
    model: CompiledModel = project.models[0]
    return replace(
        project,
        models=(
            replace(
                model,
                config=replace(
                    model.config,
                    values={
                        **model.config.values,
                        "cursor_type": "timestamp",
                        "cursor_grain": "day",
                        "incremental_strategy": "delete_insert",
                    },
                ),
            ),
        ),
    )


def write_previous_function_fingerprints(
    *,
    test_case: BuildExecutionPlanTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Write previous function definition fingerprints for planner tests."""

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
                node_type=("udf", "table_fn")[bool(function.return_columns)],
                node_name=function.name,
                target_database=function.destination.database,
                target_schema=function.destination.schema,
                target_name=function.destination.name,
                run_id="previous_run",
                definition_hash=compute_query_hash(fingerprint_sql),
                schema_fingerprint=compute_query_hash(""),
                definition=fingerprint_sql,
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
    for model_name, target_schema in test_case.model_locations.items():
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
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=f"{target_schema}.{model_name}",
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in test_case.seed_locations.items():
        seed_file_path: Path = _ensure_test_seed_file(seed_name)
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name=seed_name,
                ),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=seed_file_path,
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


def _ensure_test_seed_file(seed_name: str) -> Path:
    seed_dir: Path = Path(gettempdir()) / "sqlbuild_planner_seed_fixtures"
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_path: Path = seed_dir / f"{seed_name}.csv"
    _SEED_FILE_WRITERS[seed_path.exists()](seed_path)
    return seed_path


def _write_seed_file(seed_path: Path) -> None:
    seed_path.write_text("id,code\n1,US\n", encoding="utf-8")


def _keep_seed_file(seed_path: Path) -> None:
    del seed_path


_SEED_FILE_WRITERS: MappingProxyType[bool, Callable[[Path], None]] = MappingProxyType(
    {False: _write_seed_file, True: _keep_seed_file}
)


def build_execution_plan_from_kwargs(**kwargs: Any) -> PlanOutput:
    """Adapt flat planner kwargs to the grouped build_execution_plan inputs."""

    def grouped(model: type) -> dict[str, Any]:
        names: frozenset[str] = frozenset(field.name for field in fields(model))
        return {name: kwargs.pop(name) for name in names & kwargs.keys()}

    selection: PlannerSelection = PlannerSelection(**grouped(PlannerSelection))
    overrides: PlannerOverrides = PlannerOverrides(**grouped(PlannerOverrides))
    deferral: DeferralInputs = DeferralInputs(**grouped(DeferralInputs))
    policies: PlannerPolicies = PlannerPolicies(**grouped(PlannerPolicies))
    return build_execution_plan(
        selection=selection,
        overrides=overrides,
        deferral=deferral,
        policies=policies,
        **kwargs,
    )
